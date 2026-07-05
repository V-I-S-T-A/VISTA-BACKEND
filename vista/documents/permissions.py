from rest_framework.permissions import BasePermission


class IsSubmissionOwnerOrAdminOrStaff(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.user.role in ("admin", "staff"):
            return True
        return obj.submission_id.submitted_by_id == request.user.user_id