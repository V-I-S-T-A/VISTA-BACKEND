import django_filters
from .models import Submission


class SubmissionFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(method="filter_status")
    org_id = django_filters.UUIDFilter(field_name="org_id__org_id")
    category_id = django_filters.UUIDFilter(field_name="category_id__category_id")
    doc_type_id = django_filters.UUIDFilter(field_name="doc_type_id__doc_type_id")
    academic_year_id = django_filters.UUIDFilter(field_name="academic_year_id__academic_year_id")
    submitted_by = django_filters.UUIDFilter(field_name="submitted_by__user_id")
    submitted_after = django_filters.DateTimeFilter(field_name="submitted_at", lookup_expr="gte")
    submitted_before = django_filters.DateTimeFilter(field_name="submitted_at", lookup_expr="lte")

    def filter_status(self, queryset, name, value):
        if not value or value.strip().lower() in ["all", "all status", ""]:
            return queryset
        val = value.strip().lower()
        if val in ["process", "in_process", "in-process", "in process"]:
            return queryset.filter(status__in=[Submission.STATUS_PENDING, Submission.STATUS_UNDER_REVIEW])
        if val in ["approved", "verified"]:
            return queryset.filter(status=Submission.STATUS_APPROVED)
        if val in ["returned", "rejected", "flagged", "resubmission_required"]:
            return queryset.filter(status__in=[Submission.STATUS_REJECTED, Submission.STATUS_RESUBMISSION_REQUIRED])
        if "," in val:
            statuses = [s.strip() for s in val.split(",")]
            return queryset.filter(status__in=statuses)
        return queryset.filter(status=val)

    class Meta:
        model = Submission
        fields = ["status", "org_id", "category_id", "doc_type_id", "academic_year_id", "submitted_by", "submitted_after", "submitted_before"]