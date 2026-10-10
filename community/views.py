from django.db.models import Count, Exists, OuterRef
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Post, PostLike
from .pagination import PostPagination
from .permissions import IsPostAuthorOrReadOnly
from .serializers import PostSerializer


class PostListCreateView(generics.ListCreateAPIView):
    """태그별 피드 조회와 게시물 작성을 담당한다."""

    serializer_class = PostSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PostPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = Post.objects.select_related("region").annotate(
            like_count=Count("likes", distinct=True),
            is_liked=Exists(
                PostLike.objects.filter(
                    post_id=OuterRef("pk"),
                    user=self.request.user,
                )
            ),
        ).order_by("-created_at", "-pk")

        tag = self.request.query_params.get("tag")
        if not tag:
            raise ValidationError({"tag": "조회할 태그를 선택해주세요."})

        allowed_tags = {choice.value for choice in Post.Tag}
        if tag not in allowed_tags:
            raise ValidationError({
                "tag": "가디건, 패딩, 코트 중 하나를 선택해주세요."
            })

        return queryset.filter(tag=tag)

    def perform_create(self, serializer):
        serializer.save()


def _activity_post_queryset(user):
    """마이페이지 게시물 목록에 필요한 공감 정보를 함께 조회한다."""

    return (
        Post.objects
        .select_related("region")
        .annotate(
            like_count=Count("likes", distinct=True),
            is_liked=Exists(
                PostLike.objects.filter(
                    post_id=OuterRef("pk"),
                    user=user,
                )
            ),
        )
        .order_by("-created_at", "-pk")
    )


class MyPostListView(generics.ListAPIView):
    """현재 사용자가 작성한 게시물 목록을 반환한다."""

    serializer_class = PostSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PostPagination

    def get_queryset(self):
        return _activity_post_queryset(
            self.request.user,
        ).filter(user=self.request.user)


class LikedPostListView(generics.ListAPIView):
    """현재 사용자가 공감한 게시물 목록을 반환한다."""

    serializer_class = PostSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PostPagination

    def get_queryset(self):
        return _activity_post_queryset(
            self.request.user,
        ).filter(
            likes__user=self.request.user,
        ).distinct()


class PostUpdateView(generics.RetrieveUpdateDestroyAPIView):
    """작성자 본인에게만 게시물 상세 조회·수정·삭제를 제공한다."""

    serializer_class = PostSerializer
    permission_classes = [IsAuthenticated, IsPostAuthorOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    lookup_url_kwarg = "post_id"

    def get_queryset(self):
        return Post.objects.select_related(
            "user",
            "region",
        ).filter(user=self.request.user)


class PostLikeToggleView(APIView):
    """좋아요를 누르면 추가하고, 다시 누르면 취소한다."""

    permission_classes = [IsAuthenticated]

    def post(self, request, post_id):
        post = get_object_or_404(Post, pk=post_id)
        like, created = PostLike.objects.get_or_create(
            post=post,
            user=request.user,
        )

        if created:
            is_liked = True
        else:
            like.delete()
            is_liked = False

        return Response({
            "postId": post.pk,
            "isLiked": is_liked,
            "likeCount": post.likes.count(),
        })
