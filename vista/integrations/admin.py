from django.contrib import admin
from .models import GoogleDriveConnection


@admin.register(GoogleDriveConnection)
class GoogleDriveConnectionAdmin(admin.ModelAdmin):
    list_display = ("staff", "google_account_email", "folder_name", "is_active", "last_synced_at")
    list_filter = ("is_active", "folder_mode")
    search_fields = ("staff__email", "google_account_email", "folder_name")
    readonly_fields = (
        "connection_id",
        "staff",
        "google_account_email",
        "token_expiry",
        "scopes",
        "folder_mode",
        "folder_id",
        "folder_name",
        "last_synced_at",
        "created_at",
        "updated_at",
    )
    exclude = ("_access_token", "_refresh_token")