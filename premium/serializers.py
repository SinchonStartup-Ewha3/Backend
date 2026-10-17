from django.utils import timezone
from rest_framework import serializers

from .models import (
    NotificationPreference,
    PremiumProfile,
    PremiumRefundRequest,
)


class PremiumProfileSerializer(serializers.ModelSerializer):
    class LaundryPreference:
        RAIN_BEFORE = "RAIN_BEFORE"
        HIGH_HUMIDITY = "HIGH_HUMIDITY"
        INDOOR_DRYING_TIP = "INDOOR_DRYING_TIP"
        DAILY_SUMMARY = "DAILY_SUMMARY"

        CHOICES = [
            (RAIN_BEFORE, "비 오기 전에 알려주세요"),
            (HIGH_HUMIDITY, "습도가 높을 때 알려주세요"),
            (INDOOR_DRYING_TIP, "실내 건조 팁도 받고 싶어요"),
            (DAILY_SUMMARY, "매일 빨래 날씨를 알려주세요"),
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
    isCompleted = serializers.SerializerMethodField()

    class Meta:
        model = PremiumProfile
        fields = [
            "coldSensitivity",
            "exercisePreference",
            "laundryPreferences",
            "isCompleted",
            "surveyCompletedAt",
        ]

    def get_isCompleted(self, obj):
        return obj.survey_completed_at is not None

    def validate_laundryPreferences(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError("같은 항목을 중복 선택할 수 없습니다.")

        if self.LaundryPreference.DAILY_SUMMARY in values and len(values) > 1:
            raise serializers.ValidationError(
                "'매일 빨래 날씨를 알려주세요'는 다른 항목과 함께 선택할 수 없습니다."
            )

        return values

    def update(self, instance, validated_data):
        has_laundry_preferences = "laundryPreferences" in validated_data
        preferences = validated_data.pop("laundryPreferences", None)

        if has_laundry_preferences:
            instance.laundry_rain_alert = (
                self.LaundryPreference.RAIN_BEFORE in preferences
            )
            instance.laundry_humidity_alert = (
                self.LaundryPreference.HIGH_HUMIDITY in preferences
            )
            instance.laundry_indoor_tip = (
                self.LaundryPreference.INDOOR_DRYING_TIP in preferences
            )

        for field, value in validated_data.items():
            setattr(instance, field, value)

        submitted_all_categories = (
            "cold_sensitivity" in validated_data
            and "exercise_preference" in validated_data
            and has_laundry_preferences
        )
        if instance.survey_completed_at is None and submitted_all_categories:
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
            preferences.append(self.LaundryPreference.DAILY_SUMMARY)

        data["laundryPreferences"] = preferences
        return data


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    outerwearEnabled = serializers.BooleanField(source="outerwear_enabled")
    exerciseEnabled = serializers.BooleanField(source="exercise_enabled")
    laundryEnabled = serializers.BooleanField(source="laundry_enabled")

    class Meta:
        model = NotificationPreference
        fields = [
            "outerwearEnabled",
            "exerciseEnabled",
            "laundryEnabled",
        ]


class PremiumRefundRequestSerializer(serializers.ModelSerializer):
    refundRequestId = serializers.IntegerField(source="pk", read_only=True)
    purchaseId = serializers.IntegerField(source="purchase_id", read_only=True)
    reason = serializers.CharField(
        max_length=500,
        allow_blank=False,
        trim_whitespace=True,
        error_messages={
            "required": "환불 사유를 입력해주세요.",
            "blank": "환불 사유를 입력해주세요.",
        },
    )
    requestedAmount = serializers.IntegerField(
        source="requested_amount",
        read_only=True,
    )
    currencyCode = serializers.CharField(
        source="currency_code",
        read_only=True,
    )
    remainingSeconds = serializers.IntegerField(
        source="remaining_seconds",
        read_only=True,
    )
    paddleAdjustmentId = serializers.CharField(
        source="paddle_adjustment_id",
        read_only=True,
    )
    requestedAt = serializers.DateTimeField(source="created_at", read_only=True)
    completedAt = serializers.DateTimeField(source="completed_at", read_only=True)
    rejectionReason = serializers.CharField(
        source="rejection_reason",
        read_only=True,
    )

    class Meta:
        model = PremiumRefundRequest
        fields = [
            "refundRequestId",
            "purchaseId",
            "reason",
            "requestedAmount",
            "currencyCode",
            "remainingSeconds",
            "paddleAdjustmentId",
            "status",
            "rejectionReason",
            "requestedAt",
            "completedAt",
        ]
        read_only_fields = ["status"]
