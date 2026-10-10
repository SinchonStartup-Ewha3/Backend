from premium.models import PremiumProfile
from home.services.life_info import get_first_rain_hour, get_outfit

PRECIPITATION_CONDITIONS = {
    "RAIN",
    "SLEET",
    "SNOW",
    "SHOWER",
}


def personalized_temperature(
    temperature: float,
    cold_sensitivity: str,
) -> float:
    """
    사용자의 추위·더위 민감도에 따라 옷차림 판단용 체감온도를 보정합니다.

    추위를 많이 타는 사용자는 실제보다 춥게,
    더위를 많이 타는 사용자는 실제보다 덥게 판단합니다.
    """

    if cold_sensitivity == PremiumProfile.ColdSensitivity.VERY_SENSITIVE:
        return temperature - 2

    if cold_sensitivity == PremiumProfile.ColdSensitivity.HEAT_SENSITIVE:
        return temperature + 2

    return temperature

# 옷차림 구간은 홈(life_info.py)과 같은 기준을 쓰고, 알림 문장만 여기서 정합니다.
OUTFIT_MESSAGES = {
    "SLEEVELESS": "민소매나 반팔, 반바지처럼 시원한 옷이 좋아요.",
    "SHORT_SLEEVE": "반팔이나 얇은 셔츠가 적당해요.",
    "LIGHT_LAYER": "얇은 긴팔이나 가벼운 셔츠를 추천해요.",
    "KNIT": "니트나 맨투맨처럼 도톰한 옷이 좋아요.",
    "CARDIGAN": "가디건이나 재킷을 챙겨주세요.",
    "TRENCH": "트렌치코트나 도톰한 재킷을 추천해요.",
    "COAT": "코트나 따뜻한 니트를 입어주세요.",
    "PADDED": "패딩과 목도리처럼 보온성이 높은 옷을 챙겨주세요.",
}

def recommend_outfit(
    temperature: float,
    cold_sensitivity: str,
) -> str:
    """보정된 체감온도에 홈과 같은 옷차림 기준을 적용합니다."""

    adjusted = personalized_temperature(
        temperature,
        cold_sensitivity,
    )
    code, _ = get_outfit(adjusted)
    return OUTFIT_MESSAGES[code]


def will_rain(hourly_weather: list[dict]) -> bool:
    """홈과 같은 기준(앞으로 12시간, 강수확률 60% 이상)으로 비 예보를 확인합니다."""

    return get_first_rain_hour(hourly_weather) is not None


def is_good_exercise_weather(
    current_weather: dict,
    hourly_weather: list[dict],
) -> bool:
    """야외 운동에 무리가 적은 날씨인지 간단한 규칙으로 판정합니다."""

    temperature = current_weather.get("feelsLike")

    if temperature is None:
        temperature = current_weather.get("temperature")

    if temperature is None:
        return False

    if temperature < 5 or temperature > 28:
        return False

    if will_rain(hourly_weather):
        return False

    if (current_weather.get("windSpeed") or 0) >= 8:
        return False

    return True


def build_outing_message(
    *,
    profile: PremiumProfile,
    schedule_name: str,
    current_weather: dict,
    hourly_weather: list[dict],
) -> tuple[str, str]:
    """외출 일정과 사용자 성향을 반영한 알림 문구를 만듭니다."""

    temperature = current_weather.get("feelsLike")

    if temperature is None:
        temperature = current_weather.get("temperature")

    if temperature is None:
        outfit = "외출 전에 현재 기온을 다시 확인해 주세요."
        temperature_text = ""
    else:
        outfit = recommend_outfit(
            temperature,
            profile.cold_sensitivity,
        )
        temperature_text = f"체감온도는 {temperature:.1f}℃예요. "

    rain_text = ""

    if will_rain(hourly_weather):
        rain_text = " 비 예보가 있으니 우산도 챙겨주세요."

    title = f"{schedule_name} 외출 준비할 시간이에요"
    message = f"{temperature_text}{outfit}{rain_text}".strip()

    return title, message


def build_exercise_message(
    *,
    profile: PremiumProfile,
    current_weather: dict,
    hourly_weather: list[dict],
) -> tuple[str, str] | None:
    """운동 알림을 원한 사용자에게 보낼 문구를 만듭니다."""

    if (
        profile.exercise_preference
        == PremiumProfile.ExercisePreference.NO_NOTIFICATION
    ):
        return None

    good_weather = is_good_exercise_weather(
        current_weather,
        hourly_weather,
    )

    # 날씨가 좋을 때만 알림을 원하는 사용자는
    # 조건이 좋지 않으면 알림을 생성하지 않습니다.
    if (
        profile.exercise_preference
        == PremiumProfile.ExercisePreference.GOOD_WEATHER_ONLY
        and not good_weather
    ):
        return None

    if good_weather:
        return (
            "오늘은 운동하기 좋은 날씨예요",
            "비 예보가 적고 기온도 적당해요. 가볍게 운동해 볼까요?",
        )

    return (
        "운동 전 날씨를 확인해 주세요",
        "기온이나 비·바람을 확인하고 실내 운동도 고려해 보세요.",
    )


def build_laundry_message(
    *,
    profile: PremiumProfile,
    current_weather: dict,
    hourly_weather: list[dict],
) -> tuple[str, str] | None:
    """설문에서 선택한 빨래 조건에 맞을 때만 문구를 만듭니다."""

    if profile.laundry_rain_alert and will_rain(hourly_weather):
        return (
            "비가 오기 전에 빨래를 확인해 주세요",
            "비 예보가 있어요. 실외 빨래는 미리 걷어두는 것이 좋아요.",
        )

    humidity = current_weather.get("humidity")

    if (
        profile.laundry_humidity_alert
        and humidity is not None
        and humidity >= 70
    ):
        return (
            "오늘은 습도가 높아요",
            f"현재 습도는 {humidity:.0f}%예요. 빨래 건조 시간을 넉넉히 잡아주세요.",
        )

    if profile.laundry_indoor_tip:
        return (
            "오늘의 실내 건조 팁",
            "빨래 사이를 넓게 두고 선풍기나 제습기를 함께 사용해 보세요.",
        )

    return None