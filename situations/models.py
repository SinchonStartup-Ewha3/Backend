from django.conf import settings
from django.db import models


class NotificationSchedule(models.Model):
    """사용자가 반복해서 외출하는 시간과 지역을 저장한다."""

    class Purpose(models.TextChoices):
        ACADEMY = "ACADEMY", "학원"
        COMMUTE = "COMMUTE", "출근"
        SCHOOL = "SCHOOL", "등교"
        PART_TIME = "PART_TIME", "알바"
        EXERCISE = "EXERCISE", "운동"
        CUSTOM = "CUSTOM", "직접 입력"

    class LeadMinutes(models.IntegerChoices):
        TEN_MINUTES = 10, "10분 전"
        THIRTY_MINUTES = 30, "30분 전"
        ONE_HOUR = 60, "1시간 전"
        TWO_HOURS = 120, "2시간 전"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_schedules",
    )

    name = models.CharField(max_length=30)
    purpose = models.CharField(
        max_length=20,
        choices=Purpose.choices,
        default=Purpose.CUSTOM,
    )


    weekdays = models.JSONField(default=list)

    outing_time = models.TimeField()

    region = models.ForeignKey(
        "core.Region",
        on_delete=models.PROTECT,
        related_name="notification_schedules",
    )

    lead_minutes = models.PositiveSmallIntegerField(
        choices=LeadMinutes.choices,
        default=LeadMinutes.TWO_HOURS,
    )

    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["outing_time", "pk"]
        indexes = [
            models.Index(fields=["user", "is_enabled"]),
        ]

    def __str__(self):
        return f"{self.user.nickname} - {self.name}"