from django.db.models import Q
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import AuditLog
from .serializers import AuditLogSerializer, AuditLogListSerializer, AuditLogSummarySerializer
from .filters import AuditLogFilter
from vista.pagination import StandardResultsPagination
from submissions.models import Submission
from submissions.visibility import student_submission_scope

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all().select_related("user_id__org_id")
    lookup_field = "audit_id"
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AuditLogFilter
    search_fields = ["user_id__first_name", "user_id__last_name", "user_id__email", "table_name"]
    ordering_fields = ["performed_at", "action", "table_name"]
    ordering = ["-performed_at", "-audit_id"]

    def get_serializer_class(self):
        if self.action == "list":
            if self.request.query_params.get("compact") == "true":
                return AuditLogSummarySerializer
            return AuditLogListSerializer
        return AuditLogSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if self.action == "list" and self.request.query_params.get("compact") == "true":
            queryset = queryset.defer("changes")

        if not user or not user.is_authenticated:
            return queryset.none()

        # 1. ADMINS: View absolutely everything (including logins and logouts from all accounts)
        if user.role == "admin":
            return queryset

        # 2. STAFF: View ONLY staff logs (theirs and others). EXCLUDE logins and logouts.
        if user.role == "staff":
            return queryset.filter(
                user_id__role="staff"
            ).exclude(
                action__in=["login", "logout"]
            ).distinct()

        # 3. STUDENTS: Own actions and changes to their visible organization submissions.
        if user.role == "student":
            student_q = Q(user_id=user)

            student_sub_ids = list(
                Submission.objects.filter(student_submission_scope(user))
                .values_list("submission_id", flat=True)
                .distinct()
            )
            sub_id_strs = [str(sid) for sid in student_sub_ids if sid]

            conditions = student_q
            if sub_id_strs:
                sub_changes_q = Q()
                for sid_str in sub_id_strs:
                    sub_changes_q |= (
                        Q(changes__record_id=sid_str)
                        | Q(changes__new__submission_id=sid_str)
                        | Q(changes__deleted__submission_id=sid_str)
                    )
                conditions |= (Q(table_name="tbl_Submissions") & sub_changes_q)

            return queryset.filter(conditions).distinct()

        return queryset.none()
