from django.db.models import BooleanField, Count, Exists, OuterRef, Value
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
    SAFE_METHODS,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Post, PostLike
from .pagination import PostPagination
from .permissions import IsPostAuthorOrReadOnly
from .serializers import PostSerializer
from .services.files import delete_storage_file_on_commit

from core.serializers import RegionSerializer
from home.services.kma_client import KmaApiError
from home.services.location import LocationError, resolve_location

from .services.weather_copy import (
    build_community_weather_copy,
)


def _post_queryset(user):
    """게시글 조회에 공감 수와 현재 사용자의 공감 여부를 추가한다."""

    if user.is_authenticated:
        is_liked = Exists(
            PostLike.objects.filter(
                post_id=OuterRef("pk"),
                user=user,
            )
        )
    else:
        is_liked = Value(False, output_field=BooleanField())

    return (
        Post.objects
        .select_related("region")
        .annotate(
            like_count=Count("likes", distinct=True),
            is_liked=is_liked,
        )
        .order_by("-created_at", "-pk")
    )


class PostListCreateView(generics.ListCreateAPIView):
    """태그별 피드 조회와 게시물 작성을 담당한다."""

    serializer_class = PostSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    pagination_class = PostPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = _post_queryset(self.request.user)

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

    return _post_queryset(user)


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
    permission_classes = [
        IsAuthenticatedOrReadOnly,
        IsPostAuthorOrReadOnly,
    ]
    parser_classes = [
        MultiPartParser,
        FormParser,
        JSONParser,
    ]
    lookup_url_kwarg = "post_id"

    def get_queryset(self):
        queryset = _post_queryset(self.request.user)
        if self.request.method not in SAFE_METHODS:
            queryset = queryset.filter(user=self.request.user)
        return queryset

    def perform_destroy(self, instance):
        image_name = (
            instance.image.name
            if instance.image
            else None
        )
        image_storage = (
            instance.image.storage
            if instance.image
            else None
        )

        with transaction.atomic():
            super().perform_destroy(instance)

            if image_storage and image_name:
                delete_storage_file_on_commit(
                    storage=image_storage,
                    name=image_name,
                )


class PostLikeToggleView(APIView):
    """좋아요를 누르면 추가하고, 다시 누르면 취소한다."""

    permission_classes = [IsAuthenticated]

    def post(self, request, post_id):
        with transaction.atomic():
            # 같은 게시글의 좋아요 요청을 순차 처리한다.
            post = get_object_or_404(
                Post.objects.select_for_update(),
                pk=post_id,
            )

            like = PostLike.objects.filter(
                post=post,
                user=request.user,
            ).first()

            if like is None:
                PostLike.objects.create(
                    post=post,
                    user=request.user,
                )
                is_liked = True
            else:
                like.delete()
                is_liked = False

            like_count = PostLike.objects.filter(
                post=post,
            ).count()

        return Response({
            "postId": post.pk,
            "isLiked": is_liked,
            "likeCount": like_count,
        })

class CommunityWeatherCopyView(APIView):
    """커뮤니티 화면 상단·하단 날씨 문구를 반환합니다."""

    permission_classes = [AllowAny]

    def get(self, request):
        try:
            location = resolve_location(request)
            region, copy_data = (
                build_community_weather_copy(
                    region=location.region,
                    grid=location.grid,
                )
            )

        except LocationError as exc:
            if exc.code == "LOCATION_REQUIRED":
                return Response(
                    {
                        "detail": "지역을 먼저 설정해주세요.",
                        "code": "COMMUNITY_LOCATION_REQUIRED",
                    },
                    status=exc.status,
                )
            return Response(
                exc.to_response_data(),
                status=exc.status,
            )

        except KmaApiError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "code": "WEATHER_API_ERROR",
                },
                status=502,
            )

        region_data = dict(
            RegionSerializer(region).data
        )

        parts = region.region_name.split()
        region_data["displayName"] = (
            " ".join(parts[:2])
            if len(parts) >= 2
            else region.region_name
        )

        return Response({
            "region": region_data,
            **copy_data,
        })

