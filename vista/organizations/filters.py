import django_filters
from .models import Organization


class OrganizationFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()
    created_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Organization
        fields = ["is_active", "created_after", "created_before"]