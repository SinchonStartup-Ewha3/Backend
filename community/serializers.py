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

    # 업로드할 때 사용하는 필드
    image = serializers.ImageField(
        required=False,
        allow_null=True,
        write_only=True,
    )

    # 조회 결과에 표시할 이미지 주소
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
                "게시글 내용은 2000자 이하여야 합니다."
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