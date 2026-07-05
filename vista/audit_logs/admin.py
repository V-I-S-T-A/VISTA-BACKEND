from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("user_id", "action", "table_name", "performed_at")
    list_filter = ("action", "table_name")
    search_fields = ("user_id__full_name", "user_id__email", "table_name")
    ordering = ("-performed_at",)
    readonly_fields = ("audit_id", "user_id", "action", "table_name", "changes", "performed_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False