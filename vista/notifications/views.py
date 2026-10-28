from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer


class IsNotificationRecipient(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ("student", "staff", "admin")
        )


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated, IsNotificationRecipient]

    def get_queryset(self, request):
        cutoff = timezone.now() - timedelta(days=30)
        return Notification.objects.filter(
            user_id=request.user, created_at__gte=cutoff,
        ).select_related("submission_id", "actor").order_by("-created_at")

    def get(self, request):
        notifications = self.get_queryset(request)
        return Response({
            "results": NotificationSerializer(notifications, many=True).data,
            "unread_count": notifications.filter(is_read=False).count(),
        })


class NotificationUnreadCountView(NotificationListView):
    def get(self, request):
        unread_count = self.get_queryset(request).filter(is_read=False).count()
        return Response({"unread_count": unread_count})


class NotificationReadView(NotificationListView):
    def post(self, request, notification_id):
        notification = get_object_or_404(
            self.get_queryset(request), notification_id=notification_id,
        )
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data, status=status.HTTP_200_OK)
