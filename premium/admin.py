from django.contrib import admin

from .models import PaddleWebhookEvent, PremiumEntitlement, PremiumPurchase


@admin.register(PremiumEntitlement)
class PremiumEntitlementAdmin(admin.ModelAdmin):
    list_display = ("user", "started_at", "expires_at", "modified_at")
    search_fields = ("user__nickname",)


@admin.register(PremiumPurchase)
class PremiumPurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "paddle_transaction_id",
        "status",
        "amount",
        "currency_code",
        "created_at",
    )
    list_filter = ("status", "currency_code")
    search_fields = ("user__nickname", "paddle_transaction_id")
    readonly_fields = ("created_at", "modified_at")


@admin.register(PaddleWebhookEvent)
class PaddleWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "occurred_at", "processed_at")
    list_filter = ("event_type",)
    search_fields = ("event_id", "notification_id")
    readonly_fields = ("payload", "processed_at")
