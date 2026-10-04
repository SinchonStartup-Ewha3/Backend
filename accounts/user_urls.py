from django.urls import path
from .views import NicknameUpdateView, LocationUpdateView, MeView

urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    path("me/location/", LocationUpdateView.as_view(), name="me-location"),
    path("me/nickname/", NicknameUpdateView.as_view(), name="me-nickname"),
]