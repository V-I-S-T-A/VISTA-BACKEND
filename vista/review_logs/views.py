from datetime import timedelta

from django.utils import timezone
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import ReviewLog
from .serializers import ReviewLogSerializer
from .filters import ReviewLogFilter
from vista.pagination import StandardResultsPagination


class ReviewLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ReviewLog.objects.all().select_related("submission_id", "changed_by")
    serializer_class = ReviewLogSerializer
    lookup_field = "log_id"
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ReviewLogFilter
    search_fields = ["remarks_text"]
    ordering_fields = ["changed_at"]
    ordering = ["-changed_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.role in ("admin", "staff"):
            queryset = queryset
        else:
            queryset = queryset.filter(submission_id__submitted_by=user)

        changed_after = self.request.query_params.get("changed_after")
        if changed_after:
            return queryset.filter(changed_at__gte=changed_after)

        cutoff = timezone.now() - timedelta(hours=24)
        return queryset.filter(changed_at__gte=cutoff)