from django.contrib import admin
from .models import AppRelease


@admin.register(AppRelease)
class AppReleaseAdmin(admin.ModelAdmin):
    list_display = (
        "version_name",
        "version_code",
        "is_active",
        "min_supported_code",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("version_name", "version_code")
    readonly_fields = ("created_at",)
