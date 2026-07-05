from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import AcademicYear
from .serializers import AcademicYearSerializer
from .filters import AcademicYearFilter
from users.permissions import IsAdmin
from vista.pagination import StandardResultsPagination


class AcademicYearViewSet(viewsets.ModelViewSet):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    lookup_field = "academic_year_id"
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AcademicYearFilter
    search_fields = ["year"]
    ordering_fields = ["year", "created_at"]
    ordering = ["-year"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsAdmin()]
        return [IsAuthenticated()]