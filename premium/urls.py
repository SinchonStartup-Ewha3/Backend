from django.urls import path

from .views import (
    NotificationPreferenceView,
    PaddleWebhookView,
    PremiumCheckoutView,
    PremiumProfileView,
    PremiumRefundRequestView,
    PremiumStatusView,
)


app_name = "premium"

urlpatterns = [
    path("status/", PremiumStatusView.as_view(), name="status"),
    path("checkout/", PremiumCheckoutView.as_view(), name="checkout"),
    path(
        "refund-requests/",
        PremiumRefundRequestView.as_view(),
        name="refund-request",
    ),
    path(
        "webhooks/paddle/",
        PaddleWebhookView.as_view(),
        name="paddle-webhook",
    ),
    path("profile/", PremiumProfileView.as_view(), name="profile"),
    path(
        "notification-settings/",
        NotificationPreferenceView.as_view(),
        name="notification-settings",
    ),
]
