import django_filters
from .models import ReviewLog


class ReviewLogFilter(django_filters.FilterSet):
    submission_id = django_filters.UUIDFilter(field_name="submission_id__submission_id")
    changed_by = django_filters.UUIDFilter(field_name="changed_by__user_id")
    new_status = django_filters.CharFilter(field_name="new_status")
    changed_after = django_filters.DateTimeFilter(field_name="changed_at", lookup_expr="gte")
    changed_before = django_filters.DateTimeFilter(field_name="changed_at", lookup_expr="lte")

    class Meta:
        model = ReviewLog
        fields = ["submission_id", "changed_by", "new_status", "changed_after", "changed_before"]