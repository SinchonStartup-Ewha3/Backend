from django.urls import path

from .views import PostDetailView, PostListCreateView

app_name = "community"

urlpatterns = [
    path("posts/", PostListCreateView.as_view(), name="post-list-create"),
    path("posts/<int:post_id>/", PostDetailView.as_view(), name="post-detail"),
]
