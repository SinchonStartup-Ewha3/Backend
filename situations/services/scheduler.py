import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from home.services.weather import (
    get_current_weather,
    get_hourly_weather,
)
from premium.models import PremiumProfile
from situations.services.liner_client import generate_notification_copy
from situations.models import (
    NotificationLog,
    NotificationSchedule,
)
from situations.services.delivery import deliver_notification
from situations.services.recommendations import (
    build_exercise_message,
    build_laundry_message,
    build_outing_message,
)

logger = logging.getLogger(__name__)


def _parse_weather_time(weather: dict) -> datetime:
    """기상청 예보의 ISO 시간 문자열을 datetime으로 변환합니다."""

    return datetime.fromisoformat(weather["time"])


def _closest_weather(
    hourly_weather: list[dict],
    target_time: datetime,
) -> dict | None:
    """외출 시각과 가장 가까운 시간별 예보를 찾습니다."""

    if not hourly_weather:
        return None

    return min(
        hourly_weather,
        key=lambda weather: abs(
            (
                _parse_weather_time(weather) - target_time
            ).total_seconds()
        ),
    )


def _nearby_weather(
    hourly_weather: list[dict],
    target_time: datetime,
    hours: int = 3,
) -> list[dict]:
    """외출 전후 일정 시간 내 예보만 추립니다."""

    maximum_seconds = hours * 60 * 60

    return [
        weather
        for weather in hourly_weather
        if abs(
            (
                _parse_weather_time(weather) - target_time
            ).total_seconds()
        )
        <= maximum_seconds
    ]


def _make_aware_outing_time(
    target_date,
    outing_time,
) -> datetime:
    """날짜와 외출 시각을 Asia/Seoul 기준 datetime으로 합칩니다."""

    naive_datetime = datetime.combine(
        target_date,
        outing_time,
    )

    return timezone.make_aware(
        naive_datetime,
        timezone.get_current_timezone(),
    )


def send_due_outing_notifications(
    now: datetime | None = None,
) -> dict:
    """
    현재 발송 시각에 해당하는 외출 일정을 찾아 알림을 처리합니다.

    새벽 외출 일정은 알림 시간이 전날일 수 있으므로
    오늘과 내일의 외출 일정을 모두 검사합니다.
    """

    now = timezone.localtime(now or timezone.now())

    window = timedelta(
        minutes=settings.WEATHER_NOTIFICATION_WINDOW_MINUTES
    )

    schedules = (
        NotificationSchedule.objects
        .filter(is_enabled=True)
        .select_related(
            "user",
            "user__premium_profile",
            "region",
        )
    )

    result = {
        "checked": 0,
        "due": 0,
        "processed": 0,
        "errors": 0,
    }

 
    weather_cache: dict[tuple[int, int], tuple[dict, list[dict]]] = {}

    for schedule in schedules:
        result["checked"] += 1

        try:
            profile = schedule.user.premium_profile
        except PremiumProfile.DoesNotExist:

            continue


        candidate_dates = [
            now.date(),
            now.date() + timedelta(days=1),
        ]

        for outing_date in candidate_dates:
            # Python weekday: 월요일 0 ~ 일요일 6
            if outing_date.weekday() not in schedule.weekdays:
                continue

            outing_datetime = _make_aware_outing_time(
                outing_date,
                schedule.outing_time,
            )

            notification_datetime = (
                outing_datetime
                - timedelta(minutes=schedule.lead_minutes)
            )


            if not (
                notification_datetime
                <= now
                < notification_datetime + window
            ):
                continue

            result["due"] += 1

            try:
                region = schedule.region
                region_key = (
                    region.grid_nx,
                    region.grid_ny,
                )

                if region_key not in weather_cache:
                    current_weather = get_current_weather(
                        region.grid_nx,
                        region.grid_ny,
                        now=now,
                    )
                    hourly_weather = get_hourly_weather(
                        region.grid_nx,
                        region.grid_ny,
                        hours=36,
                        now=now,
                    )

                    weather_cache[region_key] = (
                        current_weather,
                        hourly_weather,
                    )

                current_weather, hourly_weather = weather_cache[region_key]

                target_weather = _closest_weather(
                    hourly_weather,
                    outing_datetime,
                )

                if target_weather is None:
                    logger.warning(
                        "외출 시각의 예보를 찾지 못했습니다: schedule=%s",
                        schedule.pk,
                    )
                    result["errors"] += 1
                    continue


                outing_weather = {
                    **current_weather,
                    **target_weather,
                }

                nearby_forecast = _nearby_weather(
                    hourly_weather,
                    outing_datetime,
                )

                title, message = build_outing_message(
                    profile=profile,
                    schedule_name=schedule.name,
                    current_weather=outing_weather,
                    hourly_weather=nearby_forecast,
                )

                title, message = generate_notification_copy(
                    notification_type="OUTING_WEATHER",
                    weather_context={
                        "scheduleName": schedule.name,
                        "regionName": region.region_name,
                        "outingTime": outing_datetime.isoformat(),
                        "coldSensitivity": profile.cold_sensitivity,
                        "weather": outing_weather,
                        "nearbyForecast": nearby_forecast[:6],
                    },
                    fallback_title=title,
                    fallback_body=message,
                )


                dedupe_key = (
                    f"outing:{schedule.pk}:{outing_date.isoformat()}"
                )

                deliver_notification(
                    user=schedule.user,
                    schedule=schedule,
                    notification_type=(
                        NotificationLog.NotificationType.OUTING_WEATHER
                    ),
                    target_date=outing_date,
                    dedupe_key=dedupe_key,
                    title=title,
                    message=message,
                    url=settings.FRONTEND_BASE_URL,
                )

                result["processed"] += 1

            except Exception:
                result["errors"] += 1
                logger.exception(
                    "외출 알림 처리 중 오류: schedule=%s",
                    schedule.pk,
                )

    return result


def _is_due_hour(
    now: datetime,
    hour: int,
    window: timedelta,
) -> bool:
    """현재 시각이 지정한 발송 시간의 허용 구간인지 확인합니다."""

    notification_time = now.replace(
        hour=hour,
        minute=0,
        second=0,
        microsecond=0,
    )

    return notification_time <= now < notification_time + window


def _exercise_notification_hour(profile: PremiumProfile) -> int | None:
    """운동 설문 응답에 따라 알림 발송 시간을 반환합니다."""

    preference = profile.exercise_preference

    if preference == PremiumProfile.ExercisePreference.MORNING:
        return settings.EXERCISE_MORNING_NOTIFICATION_HOUR

    if preference == PremiumProfile.ExercisePreference.EVENING:
        return settings.EXERCISE_EVENING_NOTIFICATION_HOUR

    if preference == PremiumProfile.ExercisePreference.GOOD_WEATHER_ONLY:
        return settings.EXERCISE_GOOD_WEATHER_NOTIFICATION_HOUR

    return None


def send_daily_preference_notifications(
    now: datetime | None = None,
) -> dict:
    """
    사용자의 설문 결과에 따라 운동·빨래 알림을 처리합니다.

    사용자 기본 지역의 날씨를 사용하며,
    설문을 완료하지 않았거나 지역이 없으면 제외합니다.
    """

    now = timezone.localtime(now or timezone.now())

    window = timedelta(
        minutes=settings.WEATHER_NOTIFICATION_WINDOW_MINUTES
    )

    profiles = (
        PremiumProfile.objects
        .filter(
            survey_completed_at__isnull=False,
            user__region__isnull=False,
        )
        .select_related(
            "user",
            "user__region",
        )
    )

    result = {
        "checked": 0,
        "exercise_processed": 0,
        "laundry_processed": 0,
        "skipped": 0,
        "errors": 0,
    }


    weather_cache: dict[tuple[int, int], tuple[dict, list[dict]]] = {}

    for profile in profiles:
        result["checked"] += 1

        exercise_hour = _exercise_notification_hour(profile)

        exercise_due = (
            exercise_hour is not None
            and _is_due_hour(now, exercise_hour, window)
        )

        laundry_selected = any([
            profile.laundry_rain_alert,
            profile.laundry_humidity_alert,
            profile.laundry_indoor_tip,
        ])

        laundry_due = (
            laundry_selected
            and _is_due_hour(
                now,
                settings.LAUNDRY_NOTIFICATION_HOUR,
                window,
            )
        )


        if not exercise_due and not laundry_due:
            continue

        try:
            region = profile.user.region
            region_key = (
                region.grid_nx,
                region.grid_ny,
            )

            if region_key not in weather_cache:
                current_weather = get_current_weather(
                    region.grid_nx,
                    region.grid_ny,
                    now=now,
                )
                hourly_weather = get_hourly_weather(
                    region.grid_nx,
                    region.grid_ny,
                    hours=24,
                    now=now,
                )

                weather_cache[region_key] = (
                    current_weather,
                    hourly_weather,
                )

            current_weather, hourly_weather = weather_cache[region_key]

            if exercise_due:
                exercise_message = build_exercise_message(
                    profile=profile,
                    current_weather=current_weather,
                    hourly_weather=hourly_weather,
                )

                if exercise_message is None:
                    result["skipped"] += 1
                else:
                    title, message = exercise_message
                    title, message = generate_notification_copy(
                        notification_type="EXERCISE",
                        weather_context={
                            "regionName": region.region_name,
                            "exercisePreference": profile.exercise_preference,
                            "weather": current_weather,
                            "hourlyForecast": hourly_weather[:12],
                        },
                        fallback_title=title,
                        fallback_body=message,
                    )

                    deliver_notification(
                        user=profile.user,
                        notification_type=(
                            NotificationLog.NotificationType.EXERCISE
                        ),
                        target_date=now.date(),
                        dedupe_key=(
                            f"exercise:{profile.user_id}:"
                            f"{now.date().isoformat()}"
                        ),
                        title=title,
                        message=message,
                        url=settings.FRONTEND_BASE_URL,
                    )

                    result["exercise_processed"] += 1

            if laundry_due:
                laundry_message = build_laundry_message(
                    profile=profile,
                    current_weather=current_weather,
                    hourly_weather=hourly_weather,
                )

                if laundry_message is None:
                    result["skipped"] += 1
                else:
                    title, message = laundry_message

                    title, message = generate_notification_copy(
                        notification_type="LAUNDRY",
                        weather_context={
                            "regionName": region.region_name,
                            "laundryRainAlert": profile.laundry_rain_alert,
                            "laundryHumidityAlert": profile.laundry_humidity_alert,
                            "laundryIndoorTip": profile.laundry_indoor_tip,
                            "weather": current_weather,
                            "hourlyForecast": hourly_weather[:12],
                        },
                        fallback_title=title,
                        fallback_body=message,
                    )
                    deliver_notification(
                        user=profile.user,
                        notification_type=(
                            NotificationLog.NotificationType.LAUNDRY
                        ),
                        target_date=now.date(),
                        dedupe_key=(
                            f"laundry:{profile.user_id}:"
                            f"{now.date().isoformat()}"
                        ),
                        title=title,
                        message=message,
                        url=settings.FRONTEND_BASE_URL,
                    )

                    result["laundry_processed"] += 1

        except Exception:
            result["errors"] += 1

            logger.exception(
                "일일 맞춤 알림 처리 중 오류: user=%s",
                profile.user_id,
            )

    return result