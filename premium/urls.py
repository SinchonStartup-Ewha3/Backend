from django.urls import path

from .views import NotificationPreferenceView, PremiumProfileView


app_name = "premium"

urlpatterns = [
    path("profile/", PremiumProfileView.as_view(), name="profile"),
    path(
        "notification-settings/",
        NotificationPreferenceView.as_view(),
        name="notification-settings",
    ),
]
