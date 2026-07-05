import django_filters
from .models import Submission


class SubmissionFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=Submission.STATUS_CHOICES)
    org_id = django_filters.UUIDFilter(field_name="org_id__org_id")
    category_id = django_filters.UUIDFilter(field_name="category_id__category_id")
    doc_type_id = django_filters.UUIDFilter(field_name="doc_type_id__doc_type_id")
    academic_year_id = django_filters.UUIDFilter(field_name="academic_year_id__academic_year_id")
    submitted_by = django_filters.UUIDFilter(field_name="submitted_by__user_id")
    submitted_after = django_filters.DateTimeFilter(field_name="submitted_at", lookup_expr="gte")
    submitted_before = django_filters.DateTimeFilter(field_name="submitted_at", lookup_expr="lte")

    class Meta:
        model = Submission
        fields = ["status", "org_id", "category_id", "doc_type_id", "academic_year_id", "submitted_by", "submitted_after", "submitted_before"]