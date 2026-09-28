from datetime import datetime
import platform

from django.http import FileResponse
from rest_framework import viewsets, filters, status as http_status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from django.core.files.uploadedfile import UploadedFile
from PIL import Image
from pdf2image import convert_from_bytes
from rapidfuzz import process, fuzz
import pytesseract



if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

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
from academic_years.models import AcademicYear

# Import Audit Log Utilities ---
from audit_logs.utility import log_create, log_update, log_delete, log_status_change


# --- OCR autofill helpers -----------------------------------------------
# These support the `autofill` action below. Kept as module-level functions
# (rather than methods) since they don't touch `self` / view state at all.

def _load_as_image(uploaded_file: UploadedFile) -> Image.Image:
    """Accepts either a PDF or a plain image upload and returns a PIL Image."""
    content = uploaded_file.read()
    if uploaded_file.content_type == "application/pdf":
        if platform.system() == "Windows":
            return convert_from_bytes(content, dpi=300, poppler_path=r'C:\poppler\Library\bin')[0]
        else:
            return convert_from_bytes(content, dpi=300)[0]
    return Image.open(uploaded_file)

def _suggest_academic_year(ay_string: str):
    if not ay_string:
        return None
    return AcademicYear.objects.filter(year=ay_string).first()


def _suggest_doc_type(template_id: str):
    # Direct lookup against DocumentType.code (see document_types app --
    # this field was added specifically to support this lookup, replacing
    # an earlier static Python dict mapping template_id -> name).
    return DocumentType.objects.filter(code=template_id, is_active=True).first()


def _suggest_organization(raw_org_name: str):
    """Fuzzy-matches OCR'd organization text against real Organization rows (name & acronym)."""
    if not raw_org_name:
        return None, None
    
    cleaned_input = raw_org_name.strip()
    active_orgs = list(Organization.objects.filter(is_active=True))

    if not active_orgs:
        return None, None

    # 1. Exact case-insensitive match on acronym (e.g. "SITE", "GDG - USTP")
    for org in active_orgs:
        if org.acronym and org.acronym.strip().upper() == cleaned_input.upper():
            return org, 100.0

    # 2. Check if acronym is contained in raw_org_name or vice-versa
    for org in active_orgs:
        if org.acronym and (org.acronym.strip().upper() in cleaned_input.upper() or cleaned_input.upper() in org.acronym.strip().upper()):
            return org, 90.0

    # 3. Fuzzy match against organization names and acronyms
    choices = []
    org_map = {}
    for org in active_orgs:
        if org.name:
            choices.append(org.name)
            org_map[org.name] = org
        if org.acronym:
            choices.append(org.acronym)
            org_map[org.acronym] = org

    match, score, _ = process.extractOne(cleaned_input, choices, scorer=fuzz.ratio)
    org = org_map.get(match) if score >= 70 else None
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
        if self.action in ("change_status", "destroy", "export_list", "export_detail", "statistics", "export_data"):
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
        instance = serializer.save()
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
    @action(
        detail=True,
        methods=["patch"],
        url_path="status",
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def change_status(self, request, submission_id=None):
        submission = self.get_object()
        old_status = submission.status  # Capture old status

        serializer = SubmissionStatusUpdateSerializer(
            submission, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        updated_submission = serializer.save()


        # Log the specific status change
        log_status_change(
            user=request.user,
            table_name="tbl_Submissions",
            record_id=submission.submission_id,
            old_status=old_status,
            new_status=submission.status
        )

        response_data = SubmissionSerializer(updated_submission).data
        if hasattr(updated_submission, "drive_sync_result"):
            response_data["drive_sync"] = updated_submission.drive_sync_result
        return Response(response_data, status=http_status.HTTP_200_OK)

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

    @action(detail=False, methods=["get"], url_path="statistics")
    def statistics(self, request):
        queryset = self.get_queryset()
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        category = request.query_params.get("category")
        academic_year = request.query_params.get("academic_year")

        if date_from:
            queryset = queryset.filter(submitted_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(submitted_at__date__lte=date_to)
        if category and category != "All Categories":
            queryset = queryset.filter(category_id__name__iexact=category)
        if academic_year:
            queryset = queryset.filter(academic_year_id__year=academic_year)

        total = queryset.count()
        status_counts = {
            "pending": queryset.filter(status="pending").count(),
            "under_review": queryset.filter(status="under_review").count(),
            "approved": queryset.filter(status="approved").count(),
            "rejected": queryset.filter(status="rejected").count(),
            "resubmission_required": queryset.filter(status="resubmission_required").count(),
        }

        from django.db.models import Count
        by_category = list(
            queryset.values("category_id__name")
            .annotate(count=Count("submission_id"))
            .order_by("-count")
        )
        category_data = [
            {"category": item["category_id__name"] or "Uncategorized", "count": item["count"]}
            for item in by_category
        ]

        by_doc_type = list(
            queryset.values("doc_type_id__name")
            .annotate(count=Count("submission_id"))
            .order_by("-count")[:8]
        )
        doc_type_data = [
            {"doc_type": item["doc_type_id__name"] or "Other", "count": item["count"]}
            for item in by_doc_type
        ]

        by_org = list(
            queryset.values("org_id__name", "org_id__acronym")
            .annotate(count=Count("submission_id"))
            .order_by("-count")[:8]
        )
        org_data = [
            {
                "org_name": item["org_id__name"] or "Unknown",
                "org_acronym": item["org_id__acronym"] or item["org_id__name"] or "N/A",
                "count": item["count"]
            }
            for item in by_org
        ]

        from django.db.models.functions import TruncWeek, TruncMonth, TruncYear

        # Weekly trends (last 12 weeks)
        weekly_trends = list(
            queryset.annotate(week=TruncWeek("submitted_at"))
            .values("week")
            .annotate(count=Count("submission_id"))
            .order_by("week")
        )
        weekly_trend_data = [
            {
                "label": item["week"].strftime("%b %d") if item["week"] else "Unknown",
                "count": item["count"]
            }
            for item in weekly_trends[-12:]
        ]

        # Monthly trends (last 12 months)
        monthly_trends = list(
            queryset.annotate(month=TruncMonth("submitted_at"))
            .values("month")
            .annotate(count=Count("submission_id"))
            .order_by("month")
        )
        monthly_trend_data = [
            {
                "label": item["month"].strftime("%b %Y") if item["month"] else "Unknown",
                "count": item["count"]
            }
            for item in monthly_trends[-12:]
        ]

        # Yearly trends
        yearly_trends = list(
            queryset.annotate(year=TruncYear("submitted_at"))
            .values("year")
            .annotate(count=Count("submission_id"))
            .order_by("year")
        )
        yearly_trend_data = [
            {
                "label": item["year"].strftime("%Y") if item["year"] else "Unknown",
                "count": item["count"]
            }
            for item in yearly_trends[-10:]
        ]

        # Document types by timeframe interval (weeks: last 4 weeks, months: last 6 months, years: all-time)
        from datetime import timedelta
        from django.utils import timezone
        now = timezone.now()

        by_doc_weeks = list(
            queryset.filter(submitted_at__gte=now - timedelta(weeks=4))
            .values("doc_type_id__name")
            .annotate(count=Count("submission_id"))
            .order_by("-count")[:8]
        )
        doc_type_weeks = [
            {"doc_type": item["doc_type_id__name"] or "Other", "count": item["count"]}
            for item in by_doc_weeks
        ]

        by_doc_months = list(
            queryset.filter(submitted_at__gte=now - timedelta(days=180))
            .values("doc_type_id__name")
            .annotate(count=Count("submission_id"))
            .order_by("-count")[:8]
        )
        doc_type_months = [
            {"doc_type": item["doc_type_id__name"] or "Other", "count": item["count"]}
            for item in by_doc_months
        ]

        # Status counts per category (All, In-Campus, Off-Campus)
        status_by_category = {
            "all": status_counts,
            "in_campus": {
                "pending": queryset.filter(category_id__name__iexact="In-Campus", status="pending").count(),
                "under_review": queryset.filter(category_id__name__iexact="In-Campus", status="under_review").count(),
                "approved": queryset.filter(category_id__name__iexact="In-Campus", status="approved").count(),
                "rejected": queryset.filter(category_id__name__iexact="In-Campus", status="rejected").count(),
                "resubmission_required": queryset.filter(category_id__name__iexact="In-Campus", status="resubmission_required").count(),
            },
            "off_campus": {
                "pending": queryset.filter(category_id__name__iexact="Off-Campus", status="pending").count(),
                "under_review": queryset.filter(category_id__name__iexact="Off-Campus", status="under_review").count(),
                "approved": queryset.filter(category_id__name__iexact="Off-Campus", status="approved").count(),
                "rejected": queryset.filter(category_id__name__iexact="Off-Campus", status="rejected").count(),
                "resubmission_required": queryset.filter(category_id__name__iexact="Off-Campus", status="resubmission_required").count(),
            },
        }

        resolved = status_counts["approved"] + status_counts["rejected"]
        review_velocity = round((resolved / total * 100), 1) if total > 0 else 0
        approval_rate = round((status_counts["approved"] / (resolved or 1) * 100), 1) if resolved > 0 else 0

        return Response({
            "total": total,
            "status_counts": status_counts,
            "status_by_category": status_by_category,
            "category_data": category_data,
            "doc_type_data": doc_type_data,
            "doc_type_trends": {
                "weeks": doc_type_weeks,
                "months": doc_type_months,
                "years": doc_type_data,
            },
            "organization_data": org_data,
            "monthly_trends": [
                {"month": item["label"], "count": item["count"]} for item in monthly_trend_data
            ],
            "trends": {
                "weeks": weekly_trend_data,
                "months": monthly_trend_data,
                "years": yearly_trend_data,
            },
            "resolved_count": resolved,
            "review_velocity": review_velocity,
            "approval_rate": approval_rate,
        }, status=http_status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="export/data")
    def export_data(self, request):
        queryset = self.get_queryset()
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if date_from:
            queryset = queryset.filter(submitted_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(submitted_at__date__lte=date_to)

        queryset = queryset.select_related(
            "submitted_by", "org_id", "category_id", "doc_type_id", "academic_year_id"
        )
        serializer = SubmissionListSerializer(queryset, many=True)
        return Response(serializer.data, status=http_status.HTTP_200_OK)

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

        # --- NEW CATEGORY LOGIC: Based on Document Type ---
        suggested_category = None
        if doc_type:
            # Check the specific code for the Off-Campus form
            if doc_type.code == "FM-USTP-OSA-11":
                suggested_category = Category.objects.filter(name__iexact="Off-Campus").first()
            else:
                # All other document types default to In-Campus
                suggested_category = Category.objects.filter(name__iexact="In-Campus").first()
        # --------------------------------------------------

        ay_field = draft["fields"].get("academic_year")
        suggested_ay = _suggest_academic_year(ay_field["value"]) if ay_field else None

        draft["suggested_doc_type_id"] = str(doc_type.doc_type_id) if doc_type else None
        draft["suggested_org_id"] = str(suggested_org.org_id) if suggested_org else None
        draft["suggested_org_match_score"] = org_score
        draft["suggested_category_id"] = str(suggested_category.category_id) if suggested_category else None
        draft["suggested_academic_year_id"] = str(suggested_ay.academic_year_id) if suggested_ay else None

        return Response(draft, status=http_status.HTTP_200_OK)
