from django.contrib import admin
from django.utils import timezone

from .models import (
    FortuneProduct,
    FortuneProfile,
    FortunePurchase,
    FortuneRefundRequest,
    FortuneResult,
    FortuneCoupon,
    FortuneCouponAttempt,
    FortunePayAppFeedbackEvent,
)
from .services.refunds import (
    FortuneRefundError,
    complete_fortune_refund,
    reject_fortune_refund,
)


@admin.register(FortuneProfile)
class FortuneProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "calendar_type",
        "birth_date",
        "birth_time_unknown",
        "modified_at",
    )
    search_fields = ("user__nickname",)


@admin.register(FortuneProduct)
class FortuneProductAdmin(admin.ModelAdmin):
    list_display = (
        "product_code",
        "title",
        "price",
        "duration_days",
        "is_active",
        "display_order",
    )
    list_filter = ("is_active", "duration_days")
    search_fields = ("product_code", "title")


@admin.register(FortunePurchase)
class FortunePurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "product_title",
        "payment_status",
        "active_from",
        "active_until",
    )
    list_filter = ("payment_status",)
    search_fields = ("user__nickname", "payment_key")
    readonly_fields = ("created_at", "purchased_at")


@admin.register(FortuneRefundRequest)
class FortuneRefundRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "purchase",
        "reason",
        "requested_amount",
        "unused_days",
        "stop_from",
        "status",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("user__nickname", "purchase__payment_key", "reason")
    readonly_fields = (
        "user",
        "purchase",
        "reason",
        "requested_amount",
        "currency_code",
        "unused_days",
        "requested_on",
        "stop_from",
        "original_active_until",
        "status",
        "completed_at",
        "rejected_at",
        "created_at",
        "modified_at",
    )
    actions = (
        "mark_as_processing",
        "complete_payapp_selected",
        "mark_as_rejected",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="선택한 요청을 환불 처리 중으로 변경")
    def mark_as_processing(self, request, queryset):
        updated = queryset.filter(
            status=FortuneRefundRequest.Status.REQUESTED,
        ).update(
            status=FortuneRefundRequest.Status.PROCESSING,
            modified_at=timezone.now(),
        )
        self.message_user(request, f"{updated}건을 처리 중으로 변경했습니다.")

    @admin.action(
        description="PayApp에서 환불한 선택 요청을 승인·완료 처리"
    )
    def complete_payapp_selected(self, request, queryset):
        completed = 0
        skipped = 0
        for refund_request in queryset:
            try:
                complete_fortune_refund(refund_request)
                completed += 1
            except FortuneRefundError:
                skipped += 1
        self.message_user(
            request,
            f"{completed}건을 완료했습니다. 건너뜀: {skipped}건",
        )

    @admin.action(description="선택한 요청을 환불 거절로 처리")
    def mark_as_rejected(self, request, queryset):
        rejected = 0
        for refund_request in queryset.filter(
            status__in=[
                FortuneRefundRequest.Status.REQUESTED,
                FortuneRefundRequest.Status.PROCESSING,
            ]
        ):
            try:
                reject_fortune_refund(
                    refund_request,
                    reason=(
                        refund_request.rejection_reason
                        or "운영진 검토 결과 환불 요청이 거절되었습니다."
                    ),
                )
                rejected += 1
            except FortuneRefundError:
                continue
        self.message_user(request, f"{rejected}건을 환불 거절 처리했습니다.")


@admin.register(FortuneResult)
class FortuneResultAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "target_date", "title")
    list_filter = ("target_date",)
    search_fields = ("user__nickname", "title")

@admin.register(FortuneCoupon)
class FortuneCouponAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "product",
        "batch_label",
        "is_active",
        "expires_on",
        "redeemed_by",
        "redeemed_at",
    )
    list_filter = ("product", "batch_label", "is_active")
    search_fields = ("code", "redeemed_by__nickname")
    readonly_fields = ("redeemed_by", "redeemed_at", "purchase", "created_at")

@admin.register(FortuneCouponAttempt)
class FortuneCouponAttemptAdmin(admin.ModelAdmin):
    """잘못 잠긴 사용자는 locked_until을 비워서 바로 풀어줄 수 있다."""

    list_display = ("user", "failed_count", "locked_until", "modified_at")
    search_fields = ("user__nickname",)


@admin.register(FortunePayAppFeedbackEvent)
class FortunePayAppFeedbackEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_key",
        "purchase",
        "mul_no",
        "pay_state",
        "price",
        "received_at",
    )
    list_filter = ("pay_state",)
    search_fields = ("event_key", "mul_no", "purchase__user__nickname")
    readonly_fields = (
        "event_key",
        "purchase",
        "mul_no",
        "pay_state",
        "responsedate",
        "price",
        "received_at",
    )
