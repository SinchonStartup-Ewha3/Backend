from django.urls import path

from .views import PostLikeToggleView, PostListCreateView, PostUpdateView


app_name = "community"

urlpatterns = [
    path("posts/", PostListCreateView.as_view(), name="post-list-create"),
    path("posts/<int:post_id>/", PostUpdateView.as_view(), name="post-update"),
    path(
        "posts/<int:post_id>/like/",
        PostLikeToggleView.as_view(),
        name="post-like-toggle",
    ),
]
