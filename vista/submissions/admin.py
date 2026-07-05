from django.contrib import admin
from .models import Submission


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("title", "submitted_by", "org_id", "status", "submitted_at")
    list_filter = ("status", "org_id", "category_id")
    search_fields = ("title", "description")
    ordering = ("-submitted_at",)
    readonly_fields = ("submission_id", "submitted_at", "updated_at")