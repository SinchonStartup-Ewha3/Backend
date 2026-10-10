from django.urls import path

from .views import PremiumProfileView


app_name = "premium"

urlpatterns = [
    path("profile/", PremiumProfileView.as_view(), name="profile"),
]