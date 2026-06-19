from django.contrib import admin
from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("acronym", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "acronym")
    ordering = ("-created_at",)
    readonly_fields = ("org_id", "created_at")