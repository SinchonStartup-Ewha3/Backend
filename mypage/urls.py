from django.urls import path

from .views import MyPageFortuneProfileView


urlpatterns = [
    path(
        "fortune-profile/",
        MyPageFortuneProfileView.as_view(),
        name="mypage-fortune-profile",
    ),
]
