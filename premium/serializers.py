from django.utils import timezone
from rest_framework import serializers

from .models import PremiumProfile


class PremiumProfileSerializer(serializers.ModelSerializer):

    class LaundryPreference:
        RAIN_BEFORE = "RAIN_BEFORE"
        HIGH_HUMIDITY = "HIGH_HUMIDITY"
        INDOOR_DRYING_TIP = "INDOOR_DRYING_TIP"
        NONE = "NONE"

        CHOICES = [
            (RAIN_BEFORE, "비 오기 전에 알려주세요"),
            (HIGH_HUMIDITY, "습도가 높을 때 알려주세요"),
            (INDOOR_DRYING_TIP, "실내 건조 팁도 받고 싶어요"),
            (NONE, "빨래 알림은 필요 없어요"),
        ]

    coldSensitivity = serializers.ChoiceField(
        source="cold_sensitivity",
        choices=PremiumProfile.ColdSensitivity.choices,
    )

    exercisePreference = serializers.ChoiceField(
        source="exercise_preference",
        choices=PremiumProfile.ExercisePreference.choices,
    )

    
    laundryPreferences = serializers.ListField(
        child=serializers.ChoiceField(
            choices=LaundryPreference.CHOICES,
        ),
        allow_empty=False,
        write_only=True,
    )

    surveyCompletedAt = serializers.DateTimeField(
        source="survey_completed_at",
        read_only=True,
    )

    class Meta:
        model = PremiumProfile
        fields = [
            "coldSensitivity",
            "exercisePreference",
            "laundryPreferences",
            "surveyCompletedAt",
        ]

    def validate_laundryPreferences(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError("같은 항목을 중복 선택할 수 없습니다.")

        if self.LaundryPreference.NONE in values and len(values) > 1:
            raise serializers.ValidationError(
                "'빨래 알림은 필요 없어요'는 다른 항목과 함께 선택할 수 없습니다."
            )

        return values

    def update(self, instance, validated_data):
        preferences = validated_data.pop("laundryPreferences")

    
        instance.laundry_rain_alert = (
            self.LaundryPreference.RAIN_BEFORE in preferences
        )
        instance.laundry_humidity_alert = (
            self.LaundryPreference.HIGH_HUMIDITY in preferences
        )
        instance.laundry_indoor_tip = (
            self.LaundryPreference.INDOOR_DRYING_TIP in preferences
        )

        instance.cold_sensitivity = validated_data["cold_sensitivity"]
        instance.exercise_preference = validated_data["exercise_preference"]

        
        instance.survey_completed_at = timezone.now()
        instance.save()

        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        preferences = []

        if instance.laundry_rain_alert:
            preferences.append(self.LaundryPreference.RAIN_BEFORE)

        if instance.laundry_humidity_alert:
            preferences.append(self.LaundryPreference.HIGH_HUMIDITY)

        if instance.laundry_indoor_tip:
            preferences.append(self.LaundryPreference.INDOOR_DRYING_TIP)

        if not preferences:
            preferences.append(self.LaundryPreference.NONE)

        data["laundryPreferences"] = preferences
        return data
