from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, OrganizationMembershipAudit


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
        ("Important Dates", {"fields": ("created_at", "updated_at", "org_joined_at")}),
    )
    add_fieldsets = (
        (None, {"fields": ("email", "first_name", "last_name", "role", "password1", "password2")}),
    )
    readonly_fields = ("created_at", "updated_at", "org_joined_at")

    def save_model(self, request, obj, form, change):
        obj._membership_actor = request.user
        super().save_model(request, obj, form, change)


@admin.register(OrganizationMembershipAudit)
class OrganizationMembershipAuditAdmin(admin.ModelAdmin):
    list_display = ("user", "org_id_value", "joined_at", "reason", "actor", "recorded_at")
    readonly_fields = tuple(field.name for field in OrganizationMembershipAudit._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(User, UserAdmin)
