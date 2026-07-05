import django_filters
from .models import AcademicYear


class AcademicYearFilter(django_filters.FilterSet):
    year = django_filters.CharFilter(field_name="year", lookup_expr="icontains")
    created_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = AcademicYear
        fields = ["year", "created_after", "created_before"]