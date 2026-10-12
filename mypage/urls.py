from django.urls import path

from .views import MyPageFortuneProfileView, MyPageSummaryView


urlpatterns = [
    path(
        "summary/",
        MyPageSummaryView.as_view(),
        name="mypage-summary",
    ),
    path(
        "fortune-profile/",
        MyPageFortuneProfileView.as_view(),
        name="mypage-fortune-profile",
    ),
]
