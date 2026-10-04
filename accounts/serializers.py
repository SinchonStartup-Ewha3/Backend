from rest_framework import serializers

from core.geo import find_nearest_region
from core.models import Region
from core.serializers import RegionSerializer
from .models import SocialAccount, User


class SocialLoginSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=SocialAccount.Provider.choices)
    access_token = serializers.CharField()


class MeSerializer(serializers.ModelSerializer):
    userId = serializers.IntegerField(source="pk", read_only=True)
    profileImage = serializers.URLField(source="profile_image", read_only=True)
    locationMode = serializers.CharField(source="location_mode", read_only=True)
    region = RegionSerializer(read_only=True)
    isNicknameSet = serializers.SerializerMethodField()
    isOnboarded = serializers.BooleanField(source="is_onboarded", read_only=True)

    class Meta:
        model = User
        fields = [
            "userId", "nickname", "profileImage", "locationMode",
            "region", "isNicknameSet", "isOnboarded",
        ]

    def get_isNicknameSet(self, obj):
        return not obj.has_temp_nickname


class LocationUpdateSerializer(serializers.Serializer):
    locationMode = serializers.ChoiceField(choices=User.LocationMode.choices)
    lat = serializers.FloatField(required=False, min_value=-90, max_value=90)
    lng = serializers.FloatField(required=False, min_value=-180, max_value=180)
    regionCode = serializers.CharField(required=False)

    def validate(self, attrs):
        if attrs["locationMode"] == User.LocationMode.GPS:
            if attrs.get("lat") is None or attrs.get("lng") is None:
                raise serializers.ValidationError(
                    {"location": "현재 위치 설정에는 위도와 경도가 필요합니다."}
                )
            region = find_nearest_region(attrs["lat"], attrs["lng"])
            if region is None:
                raise serializers.ValidationError(
                    {"location": "국내 지역에서만 위치를 설정할 수 있습니다."}
                )
        else:
            code = attrs.get("regionCode")
            if not code:
                raise serializers.ValidationError({"regionCode": "지역을 선택해주세요."})
            region = Region.objects.filter(pk=code).first()
            if region is None:
                raise serializers.ValidationError({"regionCode": "존재하지 않는 지역입니다."})

        attrs["region"] = region
        return attrs


class NicknameUpdateSerializer(serializers.Serializer):
    nickname = serializers.CharField(
        max_length=10,
        error_messages={
            "blank": "닉네임을 입력해주세요.",
            "max_length": "닉네임은 10자 이하로 입력해주세요.",
        },
    )

    def validate_nickname(self, value):
        user = self.context["request"].user
        if User.objects.filter(nickname=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("이미 사용 중인 닉네임입니다.")
        return value