from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from .models import Post
from .permissions import IsPostAuthorOrReadOnly
from .serializers import PostSerializer


class PostListCreateView(generics.ListCreateAPIView):
    queryset = (
        Post.objects
        .select_related("user")
        .all()
    )

    serializer_class = PostSerializer
    permission_classes = [IsAuthenticated]

    parser_classes = [
        MultiPartParser,
        FormParser,
        JSONParser,
    ]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class PostDetailView(generics.RetrieveUpdateAPIView):
    queryset = (
        Post.objects
        .select_related("user")
        .all()
    )

    serializer_class = PostSerializer

    permission_classes = [
        IsAuthenticated,
        IsPostAuthorOrReadOnly,
    ]

    parser_classes = [
        MultiPartParser,
        FormParser,
        JSONParser,
    ]

    lookup_url_kwarg = "post_id"

    def perform_update(self, serializer):
        post = self.get_object()

        if post.user_id != self.request.user.pk:
            raise PermissionDenied(
                "게시글 작성자만 수정할 수 있습니다."
            )

        serializer.save()