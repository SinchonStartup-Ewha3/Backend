from django.contrib import admin
from django.utils import timezone

from .models import (
    BankTransferRequest,
    PaddleWebhookEvent,
    PayAppFeedbackEvent,
    PayAppPayment,
    PremiumEntitlement,
    PremiumPurchase,
    PremiumRefundRequest,
)
from .services.bank_transfers import (
    BankTransferStateError,
    approve_bank_transfer,
)
from .services.refunds import (
    RefundCalculationError,
    complete_bank_transfer_refund,
    complete_payapp_refund,
    reject_refund_request,
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


@admin.register(BankTransferRequest)
class BankTransferRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "depositor_name",
        "amount",
        "status",
        "created_at",
        "reviewed_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("user__nickname", "depositor_name")
    readonly_fields = (
        "user",
        "depositor_name",
        "amount",
        "currency_code",
        "status",
        "entitlement_started_at",
        "entitlement_expires_at",
        "reviewed_by",
        "reviewed_at",
        "refunded_at",
        "created_at",
        "modified_at",
    )
    actions = ("approve_selected", "reject_selected")

    @admin.action(description="선택한 입금을 승인하고 21일 권한 부여")
    def approve_selected(self, request, queryset):
        approved = 0
        skipped = 0
        for transfer_request in queryset:
            try:
                approve_bank_transfer(transfer_request, request.user)
                approved += 1
            except BankTransferStateError:
                skipped += 1
        self.message_user(
            request,
            f"{approved}건을 승인했습니다. 건너뜀: {skipped}건",
        )

    @admin.action(description="선택한 입금 요청을 거절")
    def reject_selected(self, request, queryset):
        updated = queryset.filter(
            status=BankTransferRequest.Status.PENDING,
        ).update(
            status=BankTransferRequest.Status.REJECTED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
            admin_note="입금 내역을 확인하지 못했습니다.",
        )
        self.message_user(request, f"{updated}건을 거절했습니다.")


@admin.register(PayAppPayment)
class PayAppPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "mul_no",
        "status",
        "amount",
        "provider_state",
        "created_at",
    )
    list_filter = ("status", "provider_state", "currency_code")
    search_fields = ("user__nickname", "mul_no", "order_token")
    readonly_fields = (
        "user",
        "order_token",
        "mul_no",
        "pay_url",
        "product_name",
        "amount",
        "currency_code",
        "buyer_phone_masked",
        "status",
        "provider_state",
        "entitlement_started_at",
        "entitlement_expires_at",
        "completed_at",
        "provider_canceled_at",
        "failure_reason",
        "created_at",
        "modified_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PayAppFeedbackEvent)
class PayAppFeedbackEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_key",
        "payment",
        "mul_no",
        "pay_state",
        "price",
        "received_at",
    )
    list_filter = ("pay_state",)
    search_fields = ("event_key", "mul_no", "payment__order_token")
    readonly_fields = (
        "event_key",
        "payment",
        "mul_no",
        "pay_state",
        "responsedate",
        "price",
        "received_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PremiumRefundRequest)
class PremiumRefundRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "purchase",
        "bank_transfer_request",
        "payapp_payment",
        "reason",
        "requested_amount",
        "currency_code",
        "status",
        "paddle_adjustment_id",
        "created_at",
        "completed_at",
    )
    list_filter = ("status",)
    search_fields = ("user__nickname", "reason")
    readonly_fields = (
        "user",
        "purchase",
        "bank_transfer_request",
        "payapp_payment",
        "reason",
        "requested_amount",
        "currency_code",
        "remaining_seconds",
        "access_suspended_at",
        "access_restored_at",
        "paddle_adjustment_id",
        "status",
        "completed_at",
        "created_at",
        "modified_at",
    )
    actions = (
        "mark_as_processing",
        "complete_payapp_selected",
        "complete_bank_transfer_selected",
        "mark_as_rejected",
    )

    @admin.action(description="선택한 요청을 환불 처리 중으로 변경")
    def mark_as_processing(self, request, queryset):
        updated = queryset.filter(
            status=PremiumRefundRequest.Status.REQUESTED,
        ).update(
            status=PremiumRefundRequest.Status.PROCESSING,
            modified_at=timezone.now(),
        )
        self.message_user(request, f"{updated}건을 처리 중으로 변경했습니다.")

    @admin.action(description="선택한 계좌이체 요청을 환불 완료 처리")
    def complete_bank_transfer_selected(self, request, queryset):
        completed = 0
        skipped = 0
        for refund_request in queryset:
            try:
                complete_bank_transfer_refund(refund_request)
                completed += 1
            except RefundCalculationError:
                skipped += 1
        self.message_user(
            request,
            f"{completed}건을 완료했습니다. 건너뜀: {skipped}건",
        )

    @admin.action(
        description="PayApp에서 환불한 선택 요청을 승인·완료 처리"
    )
    def complete_payapp_selected(self, request, queryset):
        completed = 0
        skipped = 0
        for refund_request in queryset:
            try:
                complete_payapp_refund(refund_request)
                completed += 1
            except RefundCalculationError:
                skipped += 1
        self.message_user(
            request,
            f"{completed}건을 완료했습니다. 건너뜀: {skipped}건",
        )

    @admin.action(description="선택한 요청을 환불 거절로 처리")
    def mark_as_rejected(self, request, queryset):
        updated = 0
        for refund_request in queryset.filter(
            status__in=[
                PremiumRefundRequest.Status.REQUESTED,
                PremiumRefundRequest.Status.PROCESSING,
            ]
        ):
            try:
                reject_refund_request(
                    refund_request,
                    reason=(
                        refund_request.rejection_reason
                        or "운영진 검토 결과 환불 요청이 거절되었습니다."
                    ),
                )
                updated += 1
            except RefundCalculationError:
                continue
        self.message_user(request, f"{updated}건을 환불 거절 처리했습니다.")


@admin.register(PaddleWebhookEvent)
class PaddleWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "occurred_at", "processed_at")
    list_filter = ("event_type",)
    search_fields = ("event_id", "notification_id")
    readonly_fields = ("payload", "processed_at")
