from django.contrib import admin

from .models import (
    FortuneProduct,
    FortuneProfile,
    FortunePurchase,
    FortuneResult,
    FortuneCoupon,
    FortuneCouponAttempt,
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