from django.contrib import admin

from .models import (
    FortuneProduct,
    FortuneProfile,
    FortunePurchase,
    FortuneResult,
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
