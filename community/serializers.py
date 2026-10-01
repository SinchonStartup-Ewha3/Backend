from django.utils import timezone
from rest_framework import serializers

from .models import Post


class PostSerializer(serializers.ModelSerializer):
    postId = serializers.IntegerField(source="pk", read_only=True)

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
