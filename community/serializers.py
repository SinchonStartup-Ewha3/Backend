from django.utils import timezone
from rest_framework import serializers

from core.geo import find_nearest_region
from core.serializers import RegionSerializer

from .models import Post


class PostSerializer(serializers.ModelSerializer):
    postId = serializers.IntegerField(source="pk", read_only=True)

   
    locationMode = serializers.ChoiceField(
        choices=[
            ("SAVED", "저장된 지역"),
            ("CURRENT", "현재 위치"),
        ],
        write_only=True,
        required=False,
        default="SAVED",
    )


    lat = serializers.FloatField(
        write_only=True,
        required=False,
        min_value=-90,
        max_value=90,
    )

    lng = serializers.FloatField(
        write_only=True,
        required=False,
        min_value=-180,
        max_value=180,
    )


    region = RegionSerializer(read_only=True)

    tag = serializers.ChoiceField(
        choices=Post.Tag.choices,
        required=True,
        allow_blank=False,
        error_messages={
            "required": "태그를 선택해주세요.",
            "blank": "태그를 선택해주세요.",
            "invalid_choice": "가디건, 패딩, 코트 중 하나를 선택해주세요.",
        },
    )
    tagLabel = serializers.CharField(source="get_tag_display", read_only=True)


    image = serializers.ImageField(
        required=False,
        allow_null=True,
        write_only=True,
    )
    imageUrl = serializers.SerializerMethodField()


    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    modifiedAt = serializers.DateTimeField(source="modified_at", read_only=True)
    createdAtDisplay = serializers.SerializerMethodField()


    likeCount = serializers.SerializerMethodField()
    isLiked = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "postId",
            "content",
            "tag",
            "tagLabel",
            "image",
            "imageUrl",
            "region",
            "locationMode",
            "lat",
            "lng",
            "createdAt",
            "createdAtDisplay",
            "modifiedAt",
            "likeCount",
            "isLiked",
        ]
        read_only_fields = [
            "postId",
            "tagLabel",
            "imageUrl",
            "region",
            "createdAt",
            "createdAtDisplay",
            "modifiedAt",
            "likeCount",
            "isLiked",
        ]

    def get_imageUrl(self, obj):
        if not obj.image:
            return None

        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.image.url)

        return obj.image.url

    def get_createdAtDisplay(self, obj):
        """작성 후 24시간까지 상대시간, 이후에는 한국식 일시를 반환한다."""
        now = timezone.now()
        seconds = max(int((now - obj.created_at).total_seconds()), 0)

        if seconds < 60:
            return "방금 전"
        if seconds < 60 * 60:
            return f"{seconds // 60}분 전"
        if seconds < 60 * 60 * 24:
            return f"{seconds // (60 * 60)}시간 전"

        created_at = timezone.localtime(obj.created_at)
        local_now = timezone.localtime(now)

        if created_at.year == local_now.year:
            return f"{created_at.month}월 {created_at.day}일 {created_at:%H:%M}"

        return (
            f"{created_at.year}년 {created_at.month}월 "
            f"{created_at.day}일 {created_at:%H:%M}"
        )

    def get_likeCount(self, obj):
        if hasattr(obj, "like_count"):
            return obj.like_count
        return obj.likes.count()

    def get_isLiked(self, obj):
        if hasattr(obj, "is_liked"):
            return obj.is_liked

        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        return obj.likes.filter(user=request.user).exists()

    def validate_content(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("게시글 내용을 입력해주세요.")

        return value

    def validate_image(self, image):
        if image is None:
            return image

        max_size = 5 * 1024 * 1024
        if image.size > max_size:
            raise serializers.ValidationError("이미지 크기는 5MB 이하여야 합니다.")

        allowed_content_types = {
            "image/jpeg",
            "image/png",
            "image/webp",
        }
        if image.content_type not in allowed_content_types:
            raise serializers.ValidationError(
                "JPG, PNG, WEBP 이미지만 등록할 수 있습니다."
            )

        return image

    def validate(self, attrs):
        """
        현재 위치를 선택한 신규 게시글에는
        위도와 경도가 모두 필요합니다.
        """

        attrs = super().validate(attrs)

        if self.instance is not None:
            return attrs

        location_mode = attrs.get("locationMode", "SAVED")

        if location_mode == "CURRENT":
            if attrs.get("lat") is None or attrs.get("lng") is None:
                raise serializers.ValidationError({
                    "location": "현재 위치를 사용하려면 위도와 경도가 필요합니다."
                })

        return attrs


    def create(self, validated_data):
        """작성 요청의 위치 방식에 따라 게시글 지역을 결정합니다."""

        request = self.context["request"]
        user = request.user

        location_mode = validated_data.pop("locationMode", "SAVED")
        lat = validated_data.pop("lat", None)
        lng = validated_data.pop("lng", None)

        if location_mode == "CURRENT":
            region = find_nearest_region(lat, lng)

            if region is None:
                raise serializers.ValidationError({
                    "location": "지원하는 국내 지역의 위치를 확인할 수 없습니다."
                })

        else:
            region = user.region

            if region is None:
                raise serializers.ValidationError({
                    "region": "저장된 지역이 없습니다. 지역을 먼저 설정해주세요."
                })

        return Post.objects.create(
            user=user,
            region=region,
            **validated_data,
        )


    def update(self, instance, validated_data):
        """
        게시글 수정으로 작성 당시 지역을 바꿀 수 없도록
        위치 관련 입력값을 제거합니다.
        """

        validated_data.pop("locationMode", None)
        validated_data.pop("lat", None)
        validated_data.pop("lng", None)

        return super().update(instance, validated_data)
