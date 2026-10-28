from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsStudent
from .models import Notification
from .serializers import NotificationSerializer


class StudentNotificationListView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def get_queryset(self, request):
        cutoff = timezone.now() - timedelta(days=30)
        return Notification.objects.filter(
            user_id=request.user, created_at__gte=cutoff,
        ).select_related("submission_id").order_by("-created_at")

    def get(self, request):
        notifications = self.get_queryset(request)
        return Response({
            "results": NotificationSerializer(notifications, many=True).data,
            "unread_count": notifications.filter(is_read=False).count(),
        })


class StudentNotificationUnreadCountView(StudentNotificationListView):
    def get(self, request):
        unread_count = self.get_queryset(request).filter(is_read=False).count()
        return Response({"unread_count": unread_count})


class StudentNotificationReadView(StudentNotificationListView):
    def post(self, request, notification_id):
        notification = get_object_or_404(
            self.get_queryset(request), notification_id=notification_id,
        )
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data, status=status.HTTP_200_OK)
