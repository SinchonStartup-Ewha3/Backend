import math
from datetime import datetime

from core.constants import WeatherCondition
from . import kma_client as kma

PTY_TO_CONDITION = {
    "1": WeatherCondition.RAIN,
    "2": WeatherCondition.SLEET,
    "3": WeatherCondition.SNOW,
    "4": WeatherCondition.SHOWER,
    "5": WeatherCondition.RAIN,    # 빗방울
    "6": WeatherCondition.SLEET,   # 빗방울눈날림
    "7": WeatherCondition.SNOW,    # 눈날림
}
SKY_TO_CONDITION = {
    "1": WeatherCondition.CLEAR,
    "3": WeatherCondition.PARTLY_CLOUDY,
    "4": WeatherCondition.CLOUDY,
}


def to_condition(sky: str | None, pty: str | None) -> WeatherCondition:
    """강수가 있으면 강수형태 우선, 없으면 하늘상태"""
    if pty and pty != "0":
        return PTY_TO_CONDITION.get(pty, WeatherCondition.RAIN)
    return SKY_TO_CONDITION.get(sky, WeatherCondition.CLEAR)


def is_night(hour: int) -> bool:
    return hour >= 18 or hour < 6


def feels_like(temp: float, humidity: float | None, wind_ms: float | None, month: int) -> float:
    """기상청 체감온도 공식: 여름(5~9월)은 습도, 겨울은 바람 반영"""
    if 5 <= month <= 9 and humidity is not None:
        rh = humidity
        tw = (temp * math.atan(0.151977 * math.sqrt(rh + 8.313659))
              + math.atan(temp + rh) - math.atan(rh - 1.67633)
              + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh) - 4.686035)
        value = (-0.2442 + 0.55399 * tw + 0.45535 * temp
                 - 0.0022 * tw ** 2 + 0.00278 * tw * temp + 3.0)
        return round(value, 1)

    if wind_ms is not None:
        v = wind_ms * 3.6  # m/s → km/h
        if temp <= 10 and v >= 4.8:
            value = 13.12 + 0.6215 * temp - 11.37 * v ** 0.16 + 0.3965 * v ** 0.16 * temp
            return round(value, 1)
    return round(temp, 1)


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(date: str, time: str) -> datetime:
    return datetime.strptime(date + time, "%Y%m%d%H%M").replace(tzinfo=kma.KST)


def _group_forecast(items: list[dict]) -> dict[datetime, dict[str, str]]:
    """기상청 단기예보는 category별로 한 줄씩 오므로 시각별로 묶는다"""
    grouped: dict[datetime, dict[str, str]] = {}
    for item in items:
        dt = _parse_dt(item["fcstDate"], item["fcstTime"])
        grouped.setdefault(dt, {})[item["category"]] = item["fcstValue"]
    return grouped


def _daily_min_max(nx: int, ny: int, now: datetime) -> tuple[float | None, float | None]:
    items = kma.fetch_items("getVilageFcst", *kma.daily_minmax_base(now), nx, ny)
    today = now.strftime("%Y%m%d")
    tmn = next((i["fcstValue"] for i in items if i["category"] == "TMN" and i["fcstDate"] == today), None)
    tmx = next((i["fcstValue"] for i in items if i["category"] == "TMX" and i["fcstDate"] == today), None)
    return _to_float(tmn), _to_float(tmx)


def get_current_weather(nx: int, ny: int, now: datetime | None = None) -> dict:
    now = now or kma.now_kst()

    ncst_date, ncst_time = kma.ultra_srt_ncst_base(now)
    ncst = {
        i["category"]: i["obsrValue"]
        for i in kma.fetch_items("getUltraSrtNcst", ncst_date, ncst_time, nx, ny)
    }
    forecast = _group_forecast(
        kma.fetch_items("getVilageFcst", *kma.vilage_fcst_base(now), nx, ny)
    )

    # 실황에는 하늘상태가 없어서 가장 가까운 예보 시각의 SKY를 쓴다
    nearest = min(forecast, key=lambda dt: abs((dt - now).total_seconds()), default=None)
    sky = forecast[nearest].get("SKY") if nearest else None

    temp = _to_float(ncst.get("T1H"))
    humidity = _to_float(ncst.get("REH"))
    wind = _to_float(ncst.get("WSD"))
    condition = to_condition(sky, ncst.get("PTY"))
    min_temp, max_temp = _daily_min_max(nx, ny, now)

    return {
        "observedAt": _parse_dt(ncst_date, ncst_time).isoformat(),
        "temperature": temp,
        "feelsLike": feels_like(temp, humidity, wind, now.month) if temp is not None else None,
        "minTemperature": min_temp,
        "maxTemperature": max_temp,
        "humidity": humidity,
        "windSpeed": wind,
        "precipitation": _to_float(ncst.get("RN1")),
        "condition": condition.value,
        "conditionLabel": condition.label,
        "isNight": is_night(now.hour),
    }


def get_hourly_weather(nx: int, ny: int, hours: int = 24, now: datetime | None = None) -> list[dict]:
    now = now or kma.now_kst()
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    forecast = _group_forecast(
        kma.fetch_items("getVilageFcst", *kma.vilage_fcst_base(now), nx, ny)
    )

    result = []
    for dt in sorted(forecast):
        if dt < current_hour:
            continue
        values = forecast[dt]
        condition = to_condition(values.get("SKY"), values.get("PTY"))

        # 시간별 예보의 기온·습도·풍속을 숫자로 변환합니다.
        temperature = _to_float(values.get("TMP"))
        humidity = _to_float(values.get("REH"))
        wind_speed = _to_float(values.get("WSD"))

        # 해당 예보 시각을 기준으로 체감온도를 계산합니다.
        apparent_temperature = (
            feels_like(
                temperature,
                humidity,
                wind_speed,
                dt.month,
            )
            if temperature is not None
            else None
        )

        result.append({
            "time": dt.isoformat(),
            "hour": dt.hour,
            "temperature": temperature,
            "feelsLike": apparent_temperature,
            "humidity": humidity,
            "windSpeed": wind_speed,
            "condition": condition.value,
            "conditionLabel": condition.label,
            "precipitationProbability": _to_float(values.get("POP")),
            "isNight": is_night(dt.hour),
        })
        if len(result) >= hours:
            break
    return result