from django.urls import path

from .views import (
    WebSocketTicketView,
    PushDeviceView,
    PushDeviceRevokeView,
    StudentNotificationListView,
    StudentNotificationReadView,
    StudentNotificationUnreadCountView,
)

urlpatterns = [
    path('notifications/ws-ticket/', WebSocketTicketView.as_view(), name='notifications-ws-ticket'),
    path("notifications/devices/", PushDeviceView.as_view(), name='push-devices'),
    path("notifications/devices/revoke/", PushDeviceRevokeView.as_view(), name='push-device-revoke'),
    path("notifications/", StudentNotificationListView.as_view(), name="notifications-list"),
    path("notifications/unread-count/", StudentNotificationUnreadCountView.as_view(), name="notifications-unread-count"),
    path("notifications/<uuid:notification_id>/read/", StudentNotificationReadView.as_view(), name="notification-read"),
]
