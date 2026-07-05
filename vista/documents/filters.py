import django_filters
from .models import Document


class DocumentFilter(django_filters.FilterSet):
    submission_id = django_filters.UUIDFilter(field_name="submission_id__submission_id")
    is_current = django_filters.BooleanFilter()
    mime_type = django_filters.CharFilter(field_name="mime_type", lookup_expr="icontains")
    uploaded_after = django_filters.DateTimeFilter(field_name="uploaded_at", lookup_expr="gte")
    uploaded_before = django_filters.DateTimeFilter(field_name="uploaded_at", lookup_expr="lte")

    class Meta:
        model = Document
        fields = ["submission_id", "is_current", "mime_type", "uploaded_after", "uploaded_before"]