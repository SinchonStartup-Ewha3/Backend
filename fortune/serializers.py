from django.utils import timezone
from rest_framework import serializers

from .models import (
    FortuneProduct,
    FortuneProfile,
    FortunePurchase,
    FortuneRefundRequest,
    FortuneResult,
)
from .services.calender import convert_to_solar_date
from .services.access import usable_purchase_status_q
from .services.generator import WEATHER_LABELS
from .services.saju import LuckLevel

class FortuneProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = FortuneProfile
        fields = [
            "calendar_type",
            "birth_date",
            "birth_time",
            "birth_time_unknown",
            "converted_solar_date",
        ]
        read_only_fields = ["converted_solar_date"]

    def validate_birth_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError(
                "생년월일은 오늘 이후일 수 없습니다."
            )
        return value

    def validate(self, attrs):
        calendar_type = attrs.get(
            "calendar_type",
            getattr(self.instance, "calendar_type", None),
        )
        birth_date = attrs.get(
            "birth_date",
            getattr(self.instance, "birth_date", None),
        )
        birth_time = attrs.get(
            "birth_time",
            getattr(self.instance, "birth_time", None),
        )
        birth_time_unknown = attrs.get(
            "birth_time_unknown",
            getattr(self.instance, "birth_time_unknown", False),
        )

        if birth_time_unknown:
            attrs["birth_time"] = None
        elif birth_time is None:
            raise serializers.ValidationError({
                "birth_time": "태어난 시간을 입력하거나 모름을 선택해주세요."
            })

        if calendar_type is None or birth_date is None:
            raise serializers.ValidationError(
                "달력 유형과 생년월일이 필요합니다."
            )

        # 양력은 그대로 사용하고 음력은 양력으로 변환해 저장합니다.
        attrs["converted_solar_date"] = convert_to_solar_date(
            calendar_type=calendar_type,
            birth_date=birth_date,
        )

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user

        return FortuneProfile.objects.create(
            user=user,
            **validated_data,
        )


class FortuneProductSerializer(serializers.ModelSerializer):
    duration_label = serializers.CharField(
        source="get_duration_days_display",
        read_only=True,
    )

    class Meta:
        model = FortuneProduct
        fields = [
            "id",
            "product_code",
            "title",
            "description",
            "price",
            "duration_days",
            "duration_label",
        ]


class FortunePurchaseCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()

    def validate_product_id(self, value):
        if not FortuneProduct.objects.filter(
            id=value,
            is_active=True,
        ).exists():
            raise serializers.ValidationError(
                "판매 중인 상품이 아닙니다."
            )

        return value

    def validate(self, attrs):
        user = self.context["request"].user
        today = timezone.localdate()

        if not FortuneProfile.objects.filter(user=user).exists():
            raise serializers.ValidationError(
                "생년월일 정보를 먼저 입력해주세요."
            )

        if FortuneRefundRequest.objects.filter(
            user=user,
            status__in=[
                FortuneRefundRequest.Status.REQUESTED,
                FortuneRefundRequest.Status.PROCESSING,
            ],
        ).exists():
            raise serializers.ValidationError(
                "운세 이용권 환불 요청을 처리 중입니다."
            )

        # 이미 사용 중인 유료 운세 상품이 있으면 중복 구매하지 못하게 합니다.
        if (
            FortunePurchase.objects.filter(
                user=user,
                active_until__gte=today,
            )
            .filter(usable_purchase_status_q(today))
            .exists()
        ):
            raise serializers.ValidationError(
                "현재 이용 중인 운세 상품이 있습니다."
            )

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        profile = user.fortune_profile

        product = FortuneProduct.objects.get(
            id=validated_data["product_id"],
            is_active=True,
        )

        # 프로필이 나중에 수정되어도 구매 당시 계산 기준은 유지합니다.
        return FortunePurchase.objects.create(
            user=user,
            product=product,
            product_title=product.title,
            duration_days=product.duration_days,
            amount=product.price,
            calendar_type=profile.calendar_type,
            birth_date=profile.birth_date,
            converted_solar_date=profile.converted_solar_date,
            birth_time=profile.birth_time,
            birth_time_unknown=profile.birth_time_unknown,
        )


class FortunePayAppCheckoutSerializer(FortunePurchaseCreateSerializer):
    recvphone = serializers.RegexField(
        regex=r"^01[016789]\d{7,8}$",
        max_length=11,
        error_messages={
            "invalid": "휴대전화 번호는 하이픈 없이 입력해주세요.",
        },
    )

    def create(self, validated_data):
        validated_data.pop("recvphone")
        return super().create(validated_data)


class FortunePurchaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = FortunePurchase
        fields = [
            "id",
            "product_title",
            "duration_days",
            "amount",
            "payment_status",
            "active_from",
            "active_until",
            "purchased_at",
            "created_at",
        ]


class FortuneRefundRequestCreateSerializer(serializers.Serializer):
    purchaseId = serializers.IntegerField()
    reason = serializers.CharField(
        max_length=500,
        allow_blank=False,
        trim_whitespace=True,
        error_messages={
            "required": "환불 사유를 입력해주세요.",
            "blank": "환불 사유를 입력해주세요.",
        },
    )


class FortuneRefundRequestSerializer(serializers.ModelSerializer):
    refundRequestId = serializers.IntegerField(source="pk", read_only=True)
    purchaseId = serializers.IntegerField(source="purchase_id", read_only=True)
    paymentMethod = serializers.SerializerMethodField()
    requestedAmount = serializers.IntegerField(
        source="requested_amount",
        read_only=True,
    )
    currencyCode = serializers.CharField(
        source="currency_code",
        read_only=True,
    )
    unusedDays = serializers.IntegerField(source="unused_days", read_only=True)
    requestedOn = serializers.DateField(source="requested_on", read_only=True)
    stopFrom = serializers.DateField(source="stop_from", read_only=True)
    requestedAt = serializers.DateTimeField(source="created_at", read_only=True)
    completedAt = serializers.DateTimeField(source="completed_at", read_only=True)
    rejectedAt = serializers.DateTimeField(source="rejected_at", read_only=True)
    rejectionReason = serializers.CharField(
        source="rejection_reason",
        read_only=True,
    )

    class Meta:
        model = FortuneRefundRequest
        fields = [
            "refundRequestId",
            "purchaseId",
            "paymentMethod",
            "reason",
            "requestedAmount",
            "currencyCode",
            "unusedDays",
            "requestedOn",
            "stopFrom",
            "status",
            "rejectionReason",
            "requestedAt",
            "completedAt",
            "rejectedAt",
        ]
        read_only_fields = ["reason", "status"]

    def get_paymentMethod(self, obj):
        return "PAYAPP"


class FortuneResultSerializer(serializers.ModelSerializer):
    detail_text = serializers.SerializerMethodField()
    detail_locked = serializers.SerializerMethodField()
    luck_label = serializers.SerializerMethodField()
    weather_label = serializers.SerializerMethodField()

    def get_luck_label(self, obj):
        return LuckLevel(obj.luck_level).label

    def get_weather_label(self, obj):
        return WEATHER_LABELS.get(obj.weather_condition)

    def _can_view_detail(self):
        return bool(
            self.context.get("can_view_detail", False)
        )

    def get_detail_text(self, obj):
        if not self._can_view_detail():
            return None

        return obj.detail_text

    def get_detail_locked(self, obj):
        return not self._can_view_detail()

    class Meta:
        model = FortuneResult
        fields = [
            "id",
            "target_date",
            "title",
            "character",
            "luck_level",
            "luck_label",
            "summary",
            "weather_condition",
            "weather_label",
            "image_url",
            "lucky_color",
            "lucky_item",
            "lucky_place",
            "detail_text",
            "detail_locked",
        ]

class FortuneCouponRedeemSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=30)
