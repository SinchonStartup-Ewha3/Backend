from rest_framework import serializers
from django.utils import timezone
from rest_framework import serializers

from .models import Post


class PostSerializer(serializers.ModelSerializer):
    postId = serializers.IntegerField(
        source="pk",
        read_only=True,
    )

    author = serializers.CharField(
        source="user.nickname",
        read_only=True,
    )


    image = serializers.ImageField(
        required=False,
        allow_null=True,
        write_only=True,
    )


    imageUrl = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "postId",
            "author",
            "content",
            "tag",
            "image",
            "imageUrl",
            "created_at",
            "modified_at",
        ]

        read_only_fields = [
            "postId",
            "author",
            "imageUrl",
            "created_at",
            "modified_at",
        ]

    def get_imageUrl(self, obj):
        if not obj.image:
            return None

        request = self.context.get("request")

        if request:
            return request.build_absolute_uri(obj.image.url)

        return obj.image.url

    def validate_content(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "게시글 내용을 입력해주세요."
            )

        if len(value) > 200:
            raise serializers.ValidationError(
                "게시글 내용은 200자 이하여야 합니다."
            )

        return value

    def validate_image(self, image):
        if image is None:
            return image

        # 빈칸 1, 2: MB를 byte로 바꾸려면?
        max_size = 5 * 1024 * 1024

        if image.size > max_size:
            raise serializers.ValidationError(
                "이미지 크기는 5MB 이하여야 합니다."
            )

        allowed_content_types = [
            "image/jpeg",
            "image/png",
            "image/webp",
        ]

        if image.content_type not in allowed_content_types:
            raise serializers.ValidationError(
                "JPG, PNG, WEBP 이미지만 등록할 수 있습니다."
            )

        return image



class PostSerializer(serializers.ModelSerializer):
    postId = serializers.IntegerField(
        source="pk",
        read_only=True,
    )


    author = serializers.CharField(
        source="user.nickname",
        read_only=True,
    )

    authorProfileImage = serializers.URLField(
        source="user.profile_image",
        read_only=True,
        allow_null=True,
    )

    image = serializers.ImageField(
        required=False,
        allow_null=True,
        write_only=True,
    )


    imageUrl = serializers.SerializerMethodField()

    tagLabel = serializers.CharField(
        source="get_tag_display",
        read_only=True,
    )

 
    createdAt = serializers.DateTimeField(
        source="created_at",
        read_only=True,
    )

    modifiedAt = serializers.DateTimeField(
        source="modified_at",
        read_only=True,
    )

    createdAtDisplay = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "postId",
            "author",
            "authorProfileImage",
            "content",
            "tag",
            "tagLabel",
            "image",
            "imageUrl",
            "createdAt",
            "createdAtDisplay",
            "modifiedAt",
        ]

        read_only_fields = [
            "postId",
            "author",
            "authorProfileImage",
            "tagLabel",
            "imageUrl",
            "createdAt",
            "createdAtDisplay",
            "modifiedAt",
        ]

    def get_imageUrl(self, obj):
        if not obj.image:
            return None

        request = self.context.get("request")

        if request:
            return request.build_absolute_uri(obj.image.url)

        return obj.image.url

    def get_createdAtDisplay(self, obj):
        """
        [기능 7 설명]
        1분 미만: 방금 전
        1시간 미만: N분 전
        24시간 미만: N시간 전
        올해 작성: 9월 30일 14:30
        이전 연도: 2025년 12월 31일 14:30
        """
        now = timezone.now()
        difference = now - obj.created_at


        seconds = max(int(difference.total_seconds()), 0)

        if seconds < 60:
            return "방금 전"

        if seconds < 60 * 60:
            minutes = seconds // 60
            return f"{minutes}분 전"

        if seconds < 60 * 60 * 24:
            hours = seconds // (60 * 60)
            return f"{hours}시간 전"

        created_at = timezone.localtime(obj.created_at)
        local_now = timezone.localtime(now)

        if created_at.year == local_now.year:
            return (
                f"{created_at.month}월 {created_at.day}일 "
                f"{created_at:%H:%M}"
            )

        return (
            f"{created_at.year}년 "
            f"{created_at.month}월 {created_at.day}일 "
            f"{created_at:%H:%M}"
        )

    def validate_content(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "게시글 내용을 입력해주세요."
            )

        if len(value) > 200:
            raise serializers.ValidationError(
                "게시글 내용은 200자 이하여야 합니다."
            )

        return value

    def validate_image(self, image):
        if image is None:
            return image


        max_size = 5 * 1024 * 1024

        if image.size > max_size:
            raise serializers.ValidationError(
                "이미지 크기는 5MB 이하여야 합니다."
            )

        allowed_content_types = [
            "image/jpeg",
            "image/png",
            "image/webp",
        ]

        if image.content_type not in allowed_content_types:
            raise serializers.ValidationError(
                "JPG, PNG, WEBP 이미지만 등록할 수 있습니다."
            )

        return image