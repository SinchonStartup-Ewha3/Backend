from django.contrib import admin
from django.utils import timezone

from .models import (
    PaddleWebhookEvent,
    PremiumEntitlement,
    PremiumPurchase,
    PremiumRefundRequest,
)


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


@admin.register(PremiumRefundRequest)
class PremiumRefundRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "purchase",
        "requested_amount",
        "currency_code",
        "status",
        "paddle_adjustment_id",
        "created_at",
        "completed_at",
    )
    list_filter = ("status",)
    search_fields = ("user__nickname",)
    readonly_fields = (
        "user",
        "purchase",
        "reason",
        "requested_amount",
        "currency_code",
        "remaining_seconds",
        "paddle_adjustment_id",
        "status",
        "completed_at",
        "created_at",
        "modified_at",
    )
    actions = (
        "mark_as_processing",
        "mark_as_rejected",
    )

    @admin.action(description="Paddle 환불 처리 중으로 변경")
    def mark_as_processing(self, request, queryset):
        updated = queryset.filter(
            status=PremiumRefundRequest.Status.REQUESTED,
        ).update(
            status=PremiumRefundRequest.Status.PROCESSING,
            modified_at=timezone.now(),
        )
        self.message_user(request, f"{updated}건을 처리 중으로 변경했습니다.")

    @admin.action(description="선택한 요청을 환불 거절로 처리")
    def mark_as_rejected(self, request, queryset):
        updated = 0
        now = timezone.now()
        for refund_request in queryset.filter(
            status__in=[
                PremiumRefundRequest.Status.REQUESTED,
                PremiumRefundRequest.Status.PROCESSING,
            ]
        ):
            refund_request.status = PremiumRefundRequest.Status.REJECTED
            if not refund_request.rejection_reason:
                refund_request.rejection_reason = (
                    "운영진 검토 결과 환불 요청이 거절되었습니다."
                )
            refund_request.modified_at = now
            refund_request.save(
                update_fields=[
                    "status",
                    "rejection_reason",
                    "modified_at",
                ]
            )
            updated += 1
        self.message_user(request, f"{updated}건을 환불 거절 처리했습니다.")


@admin.register(PaddleWebhookEvent)
class PaddleWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "occurred_at", "processed_at")
    list_filter = ("event_type",)
    search_fields = ("event_id", "notification_id")
    readonly_fields = ("payload", "processed_at")
