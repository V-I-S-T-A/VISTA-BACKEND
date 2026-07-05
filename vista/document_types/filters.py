import django_filters
from .models import DocumentType


class DocumentTypeFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = DocumentType
        fields = ["is_active"]