import django_filters
from django.db.models import Q
from .models import Organization


class OrganizationFilter(django_filters.FilterSet):
    query = django_filters.CharFilter(method="filter_query")
    is_active = django_filters.BooleanFilter()
    created_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    def filter_query(self, queryset, name, value):
        # Preserve the configuration table's full-phrase substring search.
        return queryset.filter(
            Q(name__icontains=value) | Q(acronym__icontains=value)
            | Q(description__icontains=value) | Q(org_id__icontains=value)
        )

    class Meta:
        model = Organization
        fields = ["is_active", "created_after", "created_before"]
