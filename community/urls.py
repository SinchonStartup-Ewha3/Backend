from django.urls import path

from .views import (
    LikedPostListView,
    MyPostListView,
    PostLikeToggleView,
    PostListCreateView,
    PostUpdateView,
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
    path("posts/<int:post_id>/", PostUpdateView.as_view(), name="post-update"),
    path(
        "posts/<int:post_id>/like/",
        PostLikeToggleView.as_view(),
        name="post-like-toggle",
    ),
]
