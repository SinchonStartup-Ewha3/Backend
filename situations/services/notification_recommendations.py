from premium.models import PremiumProfile
from situations.services.recommendations import (
    is_good_exercise_weather,
    recommend_outfit,
    will_rain,
)


def build_outerwear_message(
    *,
    profile: PremiumProfile,
    current_weather: dict,
) -> tuple[str, str] | None:
    """현재 체감온도와 추위 민감도에 맞는 일일 겉옷 알림을 만듭니다."""

    temperature = current_weather.get("feelsLike")

    if temperature is None:
        temperature = current_weather.get("temperature")

    if temperature is None:
        return None

    outfit = recommend_outfit(
        temperature,
        profile.cold_sensitivity,
    )

    return (
        "오늘 외출 옷차림을 확인해 주세요",
        f"체감온도는 {temperature:.1f}℃예요. {outfit}",
    )


def build_umbrella_message(
    *,
    schedule_name: str,
    hourly_weather: list[dict],
) -> tuple[str, str] | None:
    """외출 일정 주변에 비가 예상될 때 우산 알림을 만듭니다."""

    if not will_rain(hourly_weather):
        return None

    return (
        f"{schedule_name} 가기 전 우산을 챙겨주세요",
        "비 예보가 있으니 우산을 챙겨주세요.",
    )


def build_exercise_message(
    *,
    profile: PremiumProfile,
    current_weather: dict,
    hourly_weather: list[dict],
) -> tuple[str, str] | None:
    """운동 시간 선호와 날씨에 맞는 운동 알림을 만듭니다."""

    good_weather = is_good_exercise_weather(
        current_weather,
        hourly_weather,
    )

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
    """선택한 조건을 한 건의 빨래 알림으로 합쳐서 만듭니다."""

    humidity = current_weather.get("humidity")
    rain_expected = will_rain(hourly_weather)
    high_humidity = humidity is not None and humidity >= 70
    message_parts = []

    if profile.laundry_rain_alert and rain_expected:
        message_parts.append(
            "비 예보가 있어 실외 빨래는 미리 걷어두는 것이 좋아요."
        )

    if profile.laundry_humidity_alert and high_humidity:
        message_parts.append(
            f"현재 습도는 {humidity:.0f}%라 건조 시간을 넉넉히 잡아주세요."
        )

    if profile.laundry_indoor_tip:
        message_parts.append(
            "빨래 사이를 넓게 두고 선풍기나 제습기를 함께 사용해 보세요."
        )

    if message_parts:
        if profile.laundry_rain_alert and rain_expected:
            title = "비가 오기 전에 빨래를 확인해 주세요"
        elif profile.laundry_humidity_alert and high_humidity:
            title = "오늘은 습도가 높아요"
        else:
            title = "오늘의 실내 건조 팁"

        return title, " ".join(message_parts)

    selected_specific_condition = any([
        profile.laundry_rain_alert,
        profile.laundry_humidity_alert,
        profile.laundry_indoor_tip,
    ])

    if selected_specific_condition:
        return None

    if rain_expected:
        return (
            "오늘은 실외 빨래를 피해주세요",
            "비 예보가 있어요. 실내 건조나 다른 날 세탁을 추천해요.",
        )

    if high_humidity:
        return (
            "오늘은 빨래가 늦게 마를 수 있어요",
            f"현재 습도는 {humidity:.0f}%예요. 건조 시간을 넉넉히 잡아주세요.",
        )

    if humidity is None:
        return (
            "오늘은 빨래하기 괜찮아요",
            "비 소식은 적어요. 빨래 전 시간대별 날씨도 확인해 주세요.",
        )

    return (
        "오늘은 빨래하기 좋아요",
        f"비 소식이 적고 현재 습도는 {humidity:.0f}%예요.",
    )
