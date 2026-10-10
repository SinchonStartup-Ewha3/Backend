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


class NotificationLog(models.Model):
    """
    발송을 시도한 알림을 기록합니다.

    dedupe_key를 고유값으로 두어 같은 사용자에게 같은 알림이
    여러 번 발송되는 것을 방지합니다.
    """

    class NotificationType(models.TextChoices):
        OUTING_WEATHER = "OUTING_WEATHER", "외출 날씨"
        EXERCISE = "EXERCISE", "운동"
        LAUNDRY = "LAUNDRY", "빨래"
        FORTUNE = "FORTUNE", "운세"

    class Status(models.TextChoices):
        PENDING = "PENDING", "발송 대기"
        SENT = "SENT", "발송 완료"
        FAILED = "FAILED", "발송 실패"
        SKIPPED = "SKIPPED", "발송 제외"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_logs",
    )


    schedule = models.ForeignKey(
        NotificationSchedule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notification_logs",
    )

    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
    )


    target_date = models.DateField()


    dedupe_key = models.CharField(max_length=150, unique=True)

    title = models.CharField(max_length=100)
    body = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )


    provider_message_id = models.CharField(
        max_length=100,
        blank=True,
    )

    error_message = models.TextField(blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "notification_type", "target_date"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user_id} - {self.notification_type} - {self.status}"

class WaterIntake(models.Model):
    """사용자가 기록한 물 섭취량"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="water_intakes",
    )
    drank_at = models.DateTimeField()
    amount_ml = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["drank_at", "pk"]
        indexes = [models.Index(fields=["user", "drank_at"])]

    def __str__(self):
        return f"{self.user_id} - {self.drank_at:%m/%d %H:%M} {self.amount_ml}ml"