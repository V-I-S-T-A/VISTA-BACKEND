from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated

from .models import Organization
from .serializers import OrganizationSerializer, OrganizationListSerializer
from users.permissions import IsAdmin
from .filters import OrganizationFilter
from vista.paginations import StandardResultsPagination
from django_filters.rest_framework import DjangoFilterBackend


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    lookup_field = "org_id"
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrganizationFilter
    search_fields = ["name", "acronym"]
    ordering_fields = ["name", "created_at"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return OrganizationListSerializer
        return OrganizationSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")
        return queryset

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])