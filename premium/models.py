from django.conf import settings
from django.db import models


class PremiumProfile(models.Model):
    """프리미엄 맞춤 알림에 필요한 사용자 성향을 저장한다."""

    class ColdSensitivity(models.TextChoices):
        VERY_SENSITIVE = "VERY_SENSITIVE", "추위를 많이 타요"
        NORMAL = "NORMAL", "보통이에요"
        HEAT_SENSITIVE = "HEAT_SENSITIVE", "더위를 더 잘 느껴요"
        UNKNOWN = "UNKNOWN", "잘 모르겠어요"

    class ExercisePreference(models.TextChoices):
        MORNING = "MORNING", "아침에 자주 해요"
        EVENING = "EVENING", "저녁에 자주 해요"
        GOOD_WEATHER_ONLY = "GOOD_WEATHER_ONLY", "날씨가 좋을 때만 해요"
        NO_NOTIFICATION = "NO_NOTIFICATION", "운동 알림은 필요 없어요"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="premium_profile",
    )

    cold_sensitivity = models.CharField(
        max_length=30,
        choices=ColdSensitivity.choices,
        default=ColdSensitivity.UNKNOWN,
    )

    exercise_preference = models.CharField(
        max_length=30,
        choices=ExercisePreference.choices,
        default=ExercisePreference.NO_NOTIFICATION,
    )

    
    laundry_rain_alert = models.BooleanField(default=False)
    laundry_humidity_alert = models.BooleanField(default=False)
    laundry_indoor_tip = models.BooleanField(default=False)

    survey_completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.nickname}의 프리미엄 설정"