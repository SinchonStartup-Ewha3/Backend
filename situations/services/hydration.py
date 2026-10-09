from datetime import date

from django.utils import timezone

BASE_ML = 1500
HOT_DAY_EXTRA_ML = 500
HOT_DAY_TEMP = 30        # 최고기온이 이 이상이면 권장량 추가
VERY_DRY, DRY, HUMID = 30, 40, 80


def _humidity(weather: dict | None) -> int | None:
    if not weather or weather.get("humidity") is None:
        return None
    return round(weather["humidity"])


def _is_hot(weather: dict | None) -> bool:
    max_temp = (weather or {}).get("maxTemperature")
    return max_temp is not None and max_temp >= HOT_DAY_TEMP


def recommended_ml(weather: dict | None) -> int:
    return BASE_ML + (HOT_DAY_EXTRA_ML if _is_hot(weather) else 0)


def intake_message(weather: dict | None) -> str:
    humidity = _humidity(weather)
    if _is_hot(weather):
        return (f"오늘은 최고 {round(weather['maxTemperature'])}도까지 올라가는 더운 날이에요. "
                "땀으로 빠져나간 수분을 평소보다 자주 보충해 주세요.")
    if humidity is None:
        return "목이 마르기 전에 하루 동안 조금씩 자주 마셔주세요."
    if humidity <= VERY_DRY:
        return (f"오늘의 습도는 {humidity}%로, 매우 건조한 날씨예요. 건조한 날에는 몸에서 수분이 "
                "더 쉽게 빠져 나가기 때문에 수분 섭취에 더 세심한 주의가 필요해요.")
    if humidity <= DRY:
        return f"오늘의 습도는 {humidity}%로, 조금 건조한 날씨예요. 목이 마르기 전에 조금씩 자주 마셔주세요."
    if humidity >= HUMID:
        return (f"오늘의 습도는 {humidity}%로, 습한 날씨예요. "
                "갈증을 덜 느낄 수 있지만 수분 섭취는 꾸준히 해주세요.")
    return f"오늘의 습도는 {humidity}%로, 적당한 날씨예요. 하루 동안 조금씩 나눠 마셔주세요."


def skin_tip(weather: dict | None) -> str:
    humidity = _humidity(weather)
    if humidity is None:
        return "세안 후에는 바로 보습제를 발라 피부 수분을 지켜주세요."
    if humidity <= DRY:
        return (f"오늘의 습도는 {humidity}%로, 건조한 날씨예요. 두꺼운 수분 크림을 바르거나, "
                "펩타이드 등의 성분이 함유된 기초 제품을 선택해보세요.")
    if humidity >= HUMID:
        return "습한 날에는 무거운 크림보다 가벼운 젤 타입 보습제가 좋아요. 유분 관리도 함께 신경 써주세요."
    return "세안 후 가벼운 로션으로 수분을 채워주세요. 외출 전 미스트를 챙기면 더 좋아요."


def build_hydration_summary(records, weather: dict | None, today: date) -> dict:
    hourly = [0] * 24
    for record in records:
        hourly[timezone.localtime(record.drank_at).hour] += record.amount_ml

    current = sum(hourly)
    recommended = recommended_ml(weather)
    return {
        "date": today.isoformat(),
        "recommendedMl": recommended,
        "currentMl": current,
        "percent": min(100, round(current / recommended * 100)),
        "humidity": _humidity(weather),
        "message": intake_message(weather),
        "skinTip": skin_tip(weather),
        "hourly": [{"hour": hour, "amountMl": amount} for hour, amount in enumerate(hourly)],
        "records": [
            {
                "recordId": record.pk,
                "time": timezone.localtime(record.drank_at).strftime("%H:%M"),
                "amountMl": record.amount_ml,
            }
            for record in records
        ],
    }