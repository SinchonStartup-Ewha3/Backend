from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsPostAuthorOrReadOnly(BasePermission):
    message = "게시글 작성자만 수정할 수 있습니다."

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True

        # 빈칸 3: 현재 로그인한 사용자의 PK
        return obj.user_id == request.user.id