from datetime import datetime

from django.http import FileResponse
from rest_framework import viewsets, filters, status as http_status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import Submission
from .serializers import (
    SubmissionSerializer,
    SubmissionListSerializer,
    SubmissionCreateSerializer,
    SubmissionStatusUpdateSerializer,
)
from .filters import SubmissionFilter
from .permissions import IsOwnerOrAdminOrStaff
from .pdf_generator import generate_list_pdf, generate_detail_pdf
from users.permissions import IsAdminOrStaff
from vista.pagination import StandardResultsPagination

# Import Audit Log Utilities ---
from audit_logs.utility import log_create, log_update, log_delete, log_status_change


class SubmissionViewSet(viewsets.ModelViewSet):
    queryset = Submission.objects.all().select_related(
        "submitted_by", "org_id", "category_id", "doc_type_id", "academic_year_id"
    )
    lookup_field = "submission_id"
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = SubmissionFilter
    search_fields = ["title", "description"]
    ordering_fields = ["submitted_at", "updated_at", "title", "status"]
    ordering = ["-submitted_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return SubmissionListSerializer
        if self.action == "create":
            return SubmissionCreateSerializer
        return SubmissionSerializer

    def get_permissions(self):
        if self.action in ("change_status", "destroy", "export_list", "export_detail"):
            return [IsAuthenticated(), IsAdminOrStaff()]
        if self.action in ("retrieve", "update", "partial_update"):
            return [IsAuthenticated(), IsOwnerOrAdminOrStaff()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.role in ("admin", "staff"):
            return queryset
        return queryset.filter(submitted_by=user)

    # Override perform_create to log creation ---
    def perform_create(self, serializer):
        instance = serializer.save(submitted_by=self.request.user)
        log_create(
            user=self.request.user,
            table_name="tbl_Submissions",
            new_data={"title": instance.title, "submission_id": str(instance.submission_id)}
        )

    # Override perform_update to log edits ---
    def perform_update(self, serializer):
        # Capture old status before saving
        old_status = serializer.instance.status
        instance = serializer.save()
        log_update(
            user=self.request.user,
            table_name="tbl_Submissions",
            old_data={"status": old_status},
            new_data={"status": instance.status}
        )

    # Add tracking to perform_destroy ---
    def perform_destroy(self, instance):
        title = instance.title
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        log_delete(
            user=self.request.user,
            table_name="tbl_Submissions",
            old_data={"title": title, "submission_id": str(instance.submission_id)}
        )

    # Add tracking to change_status ---
    @action(detail=True, methods=["patch"], url_path="status")
    def change_status(self, request, submission_id=None):
        submission = self.get_object()
        old_status = submission.status  # Capture old status
        
        serializer = SubmissionStatusUpdateSerializer(
            submission, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Log the specific status change
        log_status_change(
            user=request.user,
            table_name="tbl_Submissions",
            record_id=submission.submission_id,
            old_status=old_status,
            new_status=submission.status
        )
        
        return Response(SubmissionSerializer(submission).data, status=http_status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="export/list")
    def export_list(self, request):
        # ... (keep your existing export_list code exactly the same) ...
        queryset = self.get_queryset()
        queryset = self.filter_queryset(queryset)
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if date_from:
            queryset = queryset.filter(submitted_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(submitted_at__date__lte=date_to)
        queryset = queryset.select_related("submitted_by", "org_id", "category_id", "doc_type_id", "academic_year_id")
        filters_parts = []
        for param in ("status", "org_id", "category_id", "doc_type_id", "academic_year_id"):
            val = request.query_params.get(param)
            if val:
                filters_parts.append(f"{param}={val}")
        if date_from:
            filters_parts.append(f"from={date_from}")
        if date_to:
            filters_parts.append(f"to={date_to}")
        filters_applied = ", ".join(filters_parts) if filters_parts else "None"
        buffer = generate_list_pdf(list(queryset), generated_by=request.user.full_name, filters_applied=filters_applied)
        filename = f"submissions_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return FileResponse(buffer, as_attachment=True, filename=filename, content_type="application/pdf")

    @action(detail=True, methods=["get"], url_path="export/detail")
    def export_detail(self, request, submission_id=None):
        # ... (keep your existing export_detail code exactly the same) ...
        submission = self.get_object()
        buffer = generate_detail_pdf(submission, generated_by=request.user.full_name)
        filename = f"submission_{str(submission.submission_id)[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return FileResponse(buffer, as_attachment=True, filename=filename, content_type="application/pdf")