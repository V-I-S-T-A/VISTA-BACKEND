from django.urls import path

from .views import (
    NotificationListView,
    NotificationReadView,
    NotificationUnreadCountView,
)

urlpatterns = [
    path("notifications/", NotificationListView.as_view(), name="notifications-list"),
    path("notifications/unread-count/", NotificationUnreadCountView.as_view(), name="notifications-unread-count"),
    path("notifications/<uuid:notification_id>/read/", NotificationReadView.as_view(), name="notification-read"),
]
