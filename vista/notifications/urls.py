from django.urls import path

from .views import (
    StudentNotificationListView,
    StudentNotificationReadView,
    StudentNotificationUnreadCountView,
)

urlpatterns = [
    path("notifications/", StudentNotificationListView.as_view(), name="notifications-list"),
    path("notifications/unread-count/", StudentNotificationUnreadCountView.as_view(), name="notifications-unread-count"),
    path("notifications/<uuid:notification_id>/read/", StudentNotificationReadView.as_view(), name="notification-read"),
]
