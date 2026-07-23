from datetime import datetime

from django.http import FileResponse
from rest_framework import viewsets, filters, status as http_status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser
from django_filters.rest_framework import DjangoFilterBackend
from django.core.files.uploadedfile import UploadedFile
from PIL import Image
from pdf2image import convert_from_bytes
from rapidfuzz import process, fuzz
import pytesseract

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
from organizations.models import Organization
from document_types.models import DocumentType
from categories.models import Category
from .ocr_autofill_pipeline import run_autofill_pipeline

# Import Audit Log Utilities ---
from audit_logs.utility import log_create, log_update, log_delete, log_status_change


# --- OCR autofill helpers -----------------------------------------------
# These support the `autofill` action below. Kept as module-level functions
# (rather than methods) since they don't touch `self` / view state at all.

def _load_as_image(uploaded_file: UploadedFile) -> Image.Image:
    """Accepts either a PDF or a plain image upload and returns a PIL Image."""
    content = uploaded_file.read()
    if uploaded_file.content_type == "application/pdf":
        return convert_from_bytes(content, dpi=300)[0]
    return Image.open(uploaded_file)


def _suggest_doc_type(template_id: str):
    # Direct lookup against DocumentType.code (see document_types app --
    # this field was added specifically to support this lookup, replacing
    # an earlier static Python dict mapping template_id -> name).
    return DocumentType.objects.filter(code=template_id, is_active=True).first()


def _suggest_organization(raw_org_name: str):
    """Fuzzy-matches OCR'd organization text against real Organization rows."""
    if not raw_org_name:
        return None, None
    org_names = list(Organization.objects.filter(is_active=True).values_list("name", flat=True))
    if not org_names:
        return None, None
    match, score, _ = process.extractOne(raw_org_name, org_names, scorer=fuzz.ratio)
    org = Organization.objects.filter(name=match).first() if score >= 70 else None
    return org, score


# Maps the SARF's "venue_category" checkbox result (see CheckboxGroup in
# ocr_autofill_pipeline.py -- its option keys are "in_campus"/"off_campus")
# to the actual Category row name. Kept as a small static dict here rather
# than a field on Category itself, since this naming is specific to how the
# OCR pipeline labels its checkbox options, not an intrinsic property of
# Category.
#
# NOTE: assumes Category has an `is_active` boolean, matching the pattern
# used by Organization/DocumentType elsewhere in this codebase -- adjust
# the filter below if Category doesn't actually have that field.
CHECKBOX_VALUE_TO_CATEGORY_NAME = {
    "in_campus": "In-Campus",
    "off_campus": "Off-Campus",
}


def _suggest_category(checkbox_value: str):
    category_name = CHECKBOX_VALUE_TO_CATEGORY_NAME.get(checkbox_value)
    if not category_name:
        return None
    return Category.objects.filter(name__iexact=category_name).first()


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
        # `autofill` deliberately falls through to here: any authenticated
        # user (not just admin/staff) can get a draft for their own upload,
        # since this is meant to help a student pre-fill their own create
        # form -- not a staff-only review tool.
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

    # --- NEW: OCR autofill draft endpoint ---------------------------------
    @action(
        detail=False, methods=["post"], url_path="autofill",
        parser_classes=[MultiPartParser],
    )
    def autofill(self, request):
        """
        POST /api/submissions/autofill/

        Read-only OCR draft endpoint. NEVER creates a Submission and has no
        write path to the database at all. The frontend uses this response
        to pre-fill the normal POST /api/submissions/ create form; a person
        still has to review the pre-filled values and submit that form
        themselves -- this endpoint only ever returns suggestions.
        """
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"detail": "No file provided."}, status=http_status.HTTP_400_BAD_REQUEST)

        image = _load_as_image(uploaded)
        full_text = pytesseract.image_to_string(image)
        draft = run_autofill_pipeline(image, full_text)

        if draft["status"] != "draft_pending_review":
            return Response(draft, status=http_status.HTTP_200_OK)

        doc_type = _suggest_doc_type(draft["template_id"])

        org_field = draft["fields"].get("organization_name")
        suggested_org, org_score = (
            _suggest_organization(org_field["value"]) if org_field else (None, None)
        )

        # venue_category comes from checkbox/mark detection, not OCR text --
        # see CheckboxGroup in ocr_autofill_pipeline.py. Its value is either
        # "in_campus", "off_campus", or None (nothing marked / ambiguous).
        venue_field = draft["fields"].get("venue_category")
        suggested_category = (
            _suggest_category(venue_field["value"])
            if venue_field and venue_field.get("value")
            else None
        )

        draft["suggested_doc_type_id"] = str(doc_type.doc_type_id) if doc_type else None
        draft["suggested_org_id"] = str(suggested_org.org_id) if suggested_org else None
        draft["suggested_org_match_score"] = org_score
        draft["suggested_category_id"] = str(suggested_category.category_id) if suggested_category else None

        return Response(draft, status=http_status.HTTP_200_OK)