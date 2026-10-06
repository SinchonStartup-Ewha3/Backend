from datetime import date

from korean_lunar_calendar import KoreanLunarCalendar
from rest_framework.exceptions import ValidationError

from fortune.models import FortuneProfile


def convert_to_solar_date(calendar_type, birth_date):
    if calendar_type == FortuneProfile.CalendarType.SOLAR:
        return birth_date

    if calendar_type in (
        FortuneProfile.CalendarType.LUNAR_NORMAL,
        FortuneProfile.CalendarType.LUNAR_LEAP,
    ):
        calendar = KoreanLunarCalendar()
        is_leap_month = calendar_type == FortuneProfile.CalendarType.LUNAR_LEAP
        is_valid = calendar.setLunarDate(
            birth_date.year,
            birth_date.month,
            birth_date.day,
            is_leap_month,
        )
        if not is_valid:
            label = "음력 윤달" if is_leap_month else "음력 평달"
            raise ValidationError(
                f"유효하지 않은 {label} 생년월일입니다."
            )
        return date(
            calendar.solarYear,
            calendar.solarMonth,
            calendar.solarDay,
        )

    raise ValidationError("지원하지 않는 달력 유형입니다.")
