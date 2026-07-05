from django.contrib import admin
from .models import ReviewLog


@admin.register(ReviewLog)
class ReviewLogAdmin(admin.ModelAdmin):
    list_display = ("submission_id", "old_status", "new_status", "changed_by", "changed_at")
    list_filter = ("old_status", "new_status")
    search_fields = ("remarks_text",)
    ordering = ("-changed_at",)
    readonly_fields = ("log_id", "submission_id", "changed_by", "old_status", "new_status", "changed_at", "remarks_text")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False