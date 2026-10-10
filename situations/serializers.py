from rest_framework import serializers

from core.models import Region
from .models import NotificationSchedule


class NotificationScheduleSerializer(serializers.ModelSerializer):
    scheduleId = serializers.IntegerField(source="pk", read_only=True)

    outingTime = serializers.TimeField(
        source="outing_time",
        format="%H:%M",
    )

    regionCode = serializers.SlugRelatedField(
        source="region",
        slug_field="region_code",
        queryset=Region.objects.all(),
    )

    regionName = serializers.CharField(
        source="region.region_name",
        read_only=True,
    )

    leadMinutes = serializers.ChoiceField(
        source="lead_minutes",
        choices=NotificationSchedule.LeadMinutes.choices,
    )

    isEnabled = serializers.BooleanField(source="is_enabled")

    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        allow_empty=False,
    )

    class Meta:
        model = NotificationSchedule
        fields = [
            "scheduleId",
            "name",
            "purpose",
            "weekdays",
            "outingTime",
            "regionCode",
            "regionName",
            "leadMinutes",
            "isEnabled",
        ]

    def validate_weekdays(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError("요일을 중복 선택할 수 없습니다.")

        
        return sorted(values)
    
class WaterIntakeCreateSerializer(serializers.Serializer):
    time = serializers.TimeField(input_formats=["%H:%M"])
    amountMl = serializers.IntegerField(
        min_value=10,
        max_value=1000,
        error_messages={
            "min_value": "10ml 이상 입력해주세요.",
            "max_value": "한 번에 1000ml까지 기록할 수 있어요.",
        },
    )

    def validate_time(self, value):
        if value.minute not in (0, 30):
            raise serializers.ValidationError("30분 단위로 입력해주세요.")
        return value