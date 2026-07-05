from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import DocumentType
from .serializers import DocumentTypeSerializer, DocumentTypeListSerializer
from .filters import DocumentTypeFilter
from users.permissions import IsAdmin
from vista.pagination import StandardResultsPagination


class DocumentTypeViewSet(viewsets.ModelViewSet):
    queryset = DocumentType.objects.all()
    lookup_field = "doc_type_id"
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = DocumentTypeFilter
    search_fields = ["name", "description"]
    ordering_fields = ["name"]
    ordering = ["name"]

    def get_serializer_class(self):
        if self.action == "list":
            return DocumentTypeListSerializer
        return DocumentTypeSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsAdmin()]
        return [IsAuthenticated()]

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])