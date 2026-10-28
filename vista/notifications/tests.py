from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from notifications.services import (
    create_drive_upload_notification,
    update_drive_upload_notification,
)
from notifications.views import IsNotificationRecipient


class NotificationRolePermissionTests(SimpleTestCase):
    def test_students_staff_and_admin_can_view_their_notifications(self):
        permission = IsNotificationRecipient()
        for role in ("student", "staff", "admin"):
            request = SimpleNamespace(
                user=SimpleNamespace(is_authenticated=True, role=role)
            )
            with self.subTest(role=role):
                self.assertTrue(permission.has_permission(request, None))

    def test_other_roles_cannot_view_notifications(self):
        permission = IsNotificationRecipient()
        request = SimpleNamespace(
            user=SimpleNamespace(is_authenticated=True, role="guest")
        )
        self.assertFalse(permission.has_permission(request, None))


class DriveUploadNotificationServiceTests(SimpleTestCase):
    @patch("notifications.services.Notification.objects.create")
    def test_creates_pending_upload_notification_for_uploader(self, create):
        user = object()
        submission = object()

        create_drive_upload_notification(user, submission, "approved.pdf")

        create.assert_called_once_with(
            user_id=user,
            actor=user,
            submission_id=submission,
            type="drive_upload_pending",
            message="Uploading approved.pdf to Google Drive.",
        )

    @patch("notifications.services.Notification.objects.filter")
    def test_updates_upload_notification_status(self, filter_notifications):
        update_drive_upload_notification("notification-id", "success", "Uploaded.")

        filter_notifications.assert_called_once_with(notification_id="notification-id")
        filter_notifications.return_value.update.assert_called_once_with(
            type="drive_upload_success",
            message="Uploaded.",
        )
