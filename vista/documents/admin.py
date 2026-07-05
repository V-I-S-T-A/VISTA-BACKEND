from django.contrib import admin
from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("file_name", "submission_id", "version", "is_current", "uploaded_at")
    list_filter = ("is_current", "mime_type")
    search_fields = ("file_name",)
    ordering = ("-uploaded_at",)
    readonly_fields = ("document_id", "uploaded_at")