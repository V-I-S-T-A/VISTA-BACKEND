from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ("email", "first_name", "last_name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("-created_at",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "org_id", "role", "image_url")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important Dates", {"fields": ("created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"fields": ("email", "first_name", "last_name", "role", "password1", "password2")}),
    )
    readonly_fields = ("created_at", "updated_at")


admin.site.register(User, UserAdmin)