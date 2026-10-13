from django.urls import path
from .views import NicknameUpdateView, LocationUpdateView, MeView, LocationUpdateView, MeView, NicknameUpdateView, ProfileImageView


urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    path("me/location/", LocationUpdateView.as_view(), name="me-location"),
    path("me/nickname/", NicknameUpdateView.as_view(), name="me-nickname"),
    path("me/profile-image/", ProfileImageView.as_view(), name="me-profile-image"),
]