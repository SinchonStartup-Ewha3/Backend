from rest_framework import serializers

from .models import (
    FortuneProduct,
    FortuneProfile,
    FortunePurchase,
    FortuneResult,
)


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

    def validate(self, attrs):
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

        if not FortuneProfile.objects.filter(user=user).exists():
            raise serializers.ValidationError(
                "생년월일 정보를 먼저 입력해주세요."
            )

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        product = FortuneProduct.objects.get(
            id=validated_data["product_id"],
            is_active=True,
        )

        return FortunePurchase.objects.create(
            user=user,
            product=product,
            product_title=product.title,
            duration_days=product.duration_days,
            amount=product.price,
        )


class FortunePurchaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = FortunePurchase
        fields = [
            "id",
            "product_title",
            "duration_days",
            "amount",
            "payment_status",
            "result_status",
            "active_from",
            "active_until",
            "purchased_at",
            "created_at",
        ]


class FortuneResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = FortuneResult
        fields = [
            "id",
            "target_date",
            "title",
            "image_url",
            "lucky_color",
            "lucky_item",
            "lucky_place",
            "detail_text",
        ]