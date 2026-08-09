from django.db.models import Q
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import AuditLog
from .serializers import AuditLogSerializer, AuditLogListSerializer
from .filters import AuditLogFilter
from vista.pagination import StandardResultsPagination
from submissions.models import Submission
from review_logs.models import ReviewLog
from users.models import User


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all().select_related("user_id")
    lookup_field = "audit_id"
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AuditLogFilter
    search_fields = ["user_id__first_name", "user_id__last_name", "user_id__email", "table_name"]
    ordering_fields = ["performed_at", "action", "table_name"]
    ordering = ["-performed_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return AuditLogListSerializer
        return AuditLogSerializer
    
    def get_queryset(self):
        user = self.request.user
        queryset = AuditLog.objects.all().select_related("user_id")

        if not user or not user.is_authenticated:
            return queryset.none()

        # Admin can view all system audit logs
        if user.role == "admin":
            return queryset

        if user.role == "staff":
            staff_q = Q(user_id=user)

            reviewed_sub_ids = list(
                ReviewLog.objects.filter(changed_by=user)
                .values_list("submission_id", flat=True)
                .distinct()
            )

            related_student_ids = list(
                Submission.objects.filter(submission_id__in=reviewed_sub_ids)
                .values_list("submitted_by", flat=True)
                .distinct()
            )

            if user.org_id:
                org_student_ids = list(
                    User.objects.filter(org_id=user.org_id, role="student")
                    .values_list("user_id", flat=True)
                )
                org_sub_ids = list(
                    Submission.objects.filter(org_id=user.org_id)
                    .values_list("submission_id", flat=True)
                )
                related_student_ids.extend(org_student_ids)
                reviewed_sub_ids.extend(org_sub_ids)

            sub_id_strs = [str(sid) for sid in set(reviewed_sub_ids) if sid]
            student_id_uuids = [sid for sid in set(related_student_ids) if sid]

            conditions = staff_q
            if student_id_uuids:
                conditions |= Q(user_id__in=student_id_uuids)

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

        if user.role == "student":
            student_q = Q(user_id=user)

            student_sub_ids = list(
                Submission.objects.filter(submitted_by=user)
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