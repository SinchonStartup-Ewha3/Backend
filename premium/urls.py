from django.urls import path

from .views import (
    NotificationPreferenceView,
    PaddleWebhookView,
    PayAppCheckoutView,
    PayAppFeedbackView,
    PremiumBillingView,
    PremiumCheckoutView,
    PremiumProfileView,
    PremiumRefundRequestView,
    PremiumStatusView,
)


app_name = "premium"

urlpatterns = [
    path("status/", PremiumStatusView.as_view(), name="status"),
    path("billing/", PremiumBillingView.as_view(), name="billing"),
    path("checkout/", PremiumCheckoutView.as_view(), name="checkout"),
    path(
        "payapp/checkout/",
        PayAppCheckoutView.as_view(),
        name="payapp-checkout",
    ),
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
    path(
        "webhooks/payapp/",
        PayAppFeedbackView.as_view(),
        name="payapp-feedback",
    ),
    path("profile/", PremiumProfileView.as_view(), name="profile"),
    path(
        "notification-settings/",
        NotificationPreferenceView.as_view(),
        name="notification-settings",
    ),
]
