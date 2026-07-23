import django_filters
from .models import DocumentType


class DocumentTypeFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()
    code = django_filters.CharFilter(lookup_expr="iexact")

    class Meta:
        model = DocumentType
        fields = ["is_active", "code"]