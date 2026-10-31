from rest_framework.permissions import BasePermission, SAFE_METHODS
from .visibility import can_read_submission


class IsOwnerOrAdminOrStaff(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.user.role in ("admin", "staff"):
            return True
        if request.method in SAFE_METHODS:
            return can_read_submission(request.user, obj)
        return obj.submitted_by_id == request.user.user_id and obj.status == "pending"
