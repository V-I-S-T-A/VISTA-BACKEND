from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsStudent
from .models import Notification
from .serializers import NotificationSerializer
from .models import PushDevice
from rest_framework import serializers
from django.core import signing
from rest_framework.permissions import AllowAny
from .devices import bind_device, revocation_key, revoke_device


class PushDeviceSerializer(serializers.Serializer):
    token = serializers.RegexField(r'^(ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_-]+\]$', max_length=255)
    previous_token = serializers.RegexField(r'^(ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_-]+\]$', max_length=255, required=False)


class PushDeviceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payload = PushDeviceSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        device = bind_device(request.user, **payload.validated_data)
        return Response({'registered': True, 'revoke_key': revocation_key(device)})

    def delete(self, request):
        payload = PushDeviceSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        PushDevice.objects.filter(user=request.user, token=payload.validated_data['token']).delete()
        return Response(status=204)


class PushDeviceRevokeView(APIView):
    # A signed, device/binding-scoped credential permits cleanup even after the
    # user's JWT expires. It grants no read, registration, or user permissions.
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        key = request.data.get('revoke_key')
        if not isinstance(key, str) or len(key) > 2048:
            return Response({'detail': 'Invalid revocation credential.'}, status=400)
        try:
            revoke_device(key)
        except (signing.BadSignature, KeyError, ValueError, TypeError):
            return Response({'detail': 'Invalid revocation credential.'}, status=400)
        return Response(status=204)


class IsNotificationRecipient(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ("student", "staff", "admin"))


class StudentNotificationListView(APIView):
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

class WebSocketTicketView(APIView):
    permission_classes = [IsAuthenticated, IsNotificationRecipient]

    def post(self, request):
        from .events import WS_TICKET_SALT
        return Response({
            "ticket": signing.dumps({"user_id": str(request.user.pk)}, salt=WS_TICKET_SALT),
            "expires_in": 60,
        })
