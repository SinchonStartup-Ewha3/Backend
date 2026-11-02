from django.urls import path

from .views import (
    CommunityWeatherCopyView,
    LikedPostListView,
    MyPostListView,
    PostDetailView,
    PostLikeToggleView,
    PostListCreateView,
)

app_name = "community"

urlpatterns = [
    path("posts/", PostListCreateView.as_view(), name="post-list-create"),
    path("posts/mine/", MyPostListView.as_view(), name="my-post-list"),
    path(
        "posts/liked/",
        LikedPostListView.as_view(),
        name="liked-post-list",
    ),
    path("posts/<int:post_id>/", PostDetailView.as_view(), name="post-detail"),
    path(
        "posts/<int:post_id>/like/",
        PostLikeToggleView.as_view(),
        name="post-like-toggle",
    ),
    path(
        "weather-copy/",
        CommunityWeatherCopyView.as_view(),
        name="weather-copy",
    ),
]
