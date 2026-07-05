from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import AuditLog
from .serializers import AuditLogSerializer, AuditLogListSerializer
from .filters import AuditLogFilter
from users.permissions import IsAdminOrStaff
from vista.pagination import StandardResultsPagination
from django.utils import timezone
from datetime import timedelta

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all().select_related("user_id")
    lookup_field = "audit_id"
    permission_classes = [IsAuthenticated, IsAdminOrStaff]
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AuditLogFilter
    search_fields = ["user_id__full_name", "user_id__email", "table_name"]
    ordering_fields = ["performed_at", "action", "table_name"]
    ordering = ["-performed_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return AuditLogListSerializer
        return AuditLogSerializer
    
    def get_queryset(self):
        queryset = AuditLog.objects.all().select_related("user_id")

        # If no date filters are provided, default to past 24 hours
        has_date_filter = (
            self.request.query_params.get("performed_after")
            or self.request.query_params.get("performed_before")
        )
        if not has_date_filter:
            since = timezone.now() - timedelta(hours=24)
            queryset = queryset.filter(performed_at__gte=since)

        return queryset