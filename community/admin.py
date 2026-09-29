from django.contrib import admin

from .models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "tag",
        "created_at",
        "modified_at",
    ]

    list_filter = [
        "tag",
        "created_at",
    ]

    search_fields = [
        "content",
        "user__nickname",
    ]

    readonly_fields = [
        "created_at",
        "modified_at",
    ]