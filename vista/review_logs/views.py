from datetime import timedelta

from django.utils import timezone
from django.db import transaction
from django.db.models import Count
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import ReviewLog, ReviewReply
from .serializers import ReviewLogSerializer, ReviewReplySerializer, ReviewReplyCreateSerializer
from .filters import ReviewLogFilter
from .notifications import notify_staff_of_reply
from vista.pagination import StandardResultsPagination
from submissions.visibility import student_submission_scope, can_reply_to_submission
from users.models import User


class ReviewLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ReviewLog.objects.select_related("submission_id", "changed_by").annotate(reply_count=Count("replies"))
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
            queryset = queryset.filter(student_submission_scope(user, "submission_id__"))

        changed_after = self.request.query_params.get("changed_after")
        if changed_after:
            return queryset.filter(changed_at__gte=changed_after)

        # If filtering by a specific submission, return ALL logs (no time cutoff)
        # so the review panel can display the full decision history.
        if self.request.query_params.get("submission_id") or self.detail:
            return queryset

        cutoff = timezone.now() - timedelta(hours=24)
        return queryset.filter(changed_at__gte=cutoff)

    @action(detail=True, methods=["get", "post"], url_path="replies", filter_backends=[])
    def replies(self, request, *args, **kwargs):
        # Lock membership for a write so a concurrent membership update cannot race authorization.
        if request.method == "POST":
            with transaction.atomic():
                request.user = User.objects.select_for_update().get(pk=request.user.pk)
                log = self.get_object()
                if not can_reply_to_submission(request.user, log.submission_id):
                    raise PermissionDenied("Only the original submitter and authorized staff can reply.")
                if not log.remarks_text.strip():
                    raise ValidationError({"detail": "Replies require a staff remark on this history entry."})
                payload = ReviewReplyCreateSerializer(data=request.data, context={"review_log": log})
                payload.is_valid(raise_exception=True)
                data = payload.validated_data
                reply, created = ReviewReply.objects.get_or_create(
                    author=request.user, client_request_id=data["client_request_id"],
                    defaults={"review_log": log, "message": data["message"], "parent_reply_id": data.get("parent_reply")},
                )
                if (reply.review_log_id != log.pk or reply.message != data["message"]
                        or reply.parent_reply_id != data.get("parent_reply")):
                    return Response({"detail": "This request ID was already used for a different reply."}, status=409)
                if created and request.user.role == "student":
                    notify_staff_of_reply(reply)
                return Response(ReviewReplySerializer(reply).data, status=201 if created else 200)
        log = self.get_object()
        queryset = log.replies.select_related("author", "parent_reply__author", "review_log__changed_by")
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(ReviewReplySerializer(page, many=True).data)
