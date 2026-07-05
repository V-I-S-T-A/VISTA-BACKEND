from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import Document
from .serializers import DocumentSerializer, DocumentCreateSerializer
from .filters import DocumentFilter
from .permissions import IsSubmissionOwnerOrAdminOrStaff
from users.permissions import IsAdminOrStaff
from vista.pagination import StandardResultsPagination


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all().select_related("submission_id")
    lookup_field = "document_id"
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = DocumentFilter
    search_fields = ["file_name"]
    ordering_fields = ["uploaded_at", "version", "file_size_kb"]
    ordering = ["-uploaded_at"]

    def get_serializer_class(self):
        if self.action == "create":
            return DocumentCreateSerializer
        return DocumentSerializer

    def get_permissions(self):
        if self.action == "destroy":
            return [IsAuthenticated(), IsAdminOrStaff()]
        if self.action in ("retrieve", "update", "partial_update"):
            return [IsAuthenticated(), IsSubmissionOwnerOrAdminOrStaff()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.role in ("admin", "staff"):
            return queryset
        return queryset.filter(submission_id__submitted_by=user)