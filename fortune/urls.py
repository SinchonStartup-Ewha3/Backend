from django.urls import path

from .views import (
    FortunePaymentConfirmView,
    FortuneProductListView,
    FortuneProfileView,
    FortunePurchaseCreateView,
    PurchaseFortuneResultListView,
    TodayFortuneResultView,
)


urlpatterns = [
    path(
        "profile/",
        FortuneProfileView.as_view(),
        name="fortune-profile",
    ),
    path(
        "products/",
        FortuneProductListView.as_view(),
        name="fortune-product-list",
    ),
    path(
        "purchases/",
        FortunePurchaseCreateView.as_view(),
        name="fortune-purchase-create",
    ),
    path(
        "purchases/<int:purchase_id>/confirm/",
        FortunePaymentConfirmView.as_view(),
        name="fortune-payment-confirm",
    ),
    path(
        "purchases/<int:purchase_id>/results/",
        PurchaseFortuneResultListView.as_view(),
        name="fortune-result-list",
    ),
    path(
        "results/today/",
        TodayFortuneResultView.as_view(),
        name="today-fortune-result",
    ),
]