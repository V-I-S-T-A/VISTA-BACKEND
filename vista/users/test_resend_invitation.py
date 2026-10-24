from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from vista.email_backend import EmailDeliveryError

from .models import User


class ResendInvitationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com", first_name="Admin", last_name="User", role="admin",
        )
        self.user = User.objects.create_user(
            email="invite@example.com", first_name="Alex", last_name="User",
            password="OriginalPassword123!", must_change_password=True,
        )
        self.url = reverse("user-resend-invitation", args=[self.user.pk])
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    @patch("users.views.send_welcome_email", return_value=1)
    def test_sends_new_password_and_keeps_existing_account(self, send):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        recipient, password = send.call_args.args
        self.assertEqual(recipient.pk, self.user.pk)
        self.assertTrue(self.user.check_password(password))
        self.assertFalse(self.user.check_password("OriginalPassword123!"))
        self.assertTrue(self.user.must_change_password)
        self.assertNotIn(password, str(response.data))
        self.assertEqual(User.objects.count(), 2)

    @patch("users.views.send_welcome_email")
    def test_failure_or_zero_send_preserves_previous_password(self, send):
        original_hash = self.user.password
        for failure in (False, True):
            with self.subTest(exception=failure):
                send.side_effect = RuntimeError("private provider details") if failure else None
                send.return_value = 0
                response = self.client.post(self.url)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.data["code"], "invitation_email_failed")
                self.assertNotIn("private provider details", str(response.data))
                self.user.refresh_from_db()
                self.assertEqual(self.user.password, original_hash)

    @patch("users.views.send_welcome_email")
    def test_logs_safe_delivery_reason_but_keeps_client_response_generic(self, send):
        send.side_effect = EmailDeliveryError("Gmail API authorization rejected request (HTTP 400). invalid_grant.")
        with self.assertLogs("users.views", level="WARNING") as logs:
            response = self.client.post(self.url)
        self.assertEqual(response.status_code, 503)
        self.assertIn("invalid_grant", " ".join(logs.output))
        self.assertNotIn("invalid_grant", str(response.data))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OriginalPassword123!"))

    @patch("users.views.send_welcome_email", side_effect=RuntimeError("private provider details"))
    def test_unexpected_error_logs_type_without_private_details(self, send):
        with self.assertLogs("users.views", level="WARNING") as logs:
            response = self.client.post(self.url)
        self.assertEqual(response.status_code, 503)
        self.assertIn("RuntimeError", " ".join(logs.output))
        self.assertNotIn("private provider details", " ".join(logs.output))

    @patch("users.views.send_welcome_email")
    def test_only_admin_can_resend(self, send):
        for role in ("student", "staff"):
            self.user.role = role
            self.user.save(update_fields=["role"])
            self.client.force_authenticate(self.user)
            self.assertEqual(self.client.post(self.url).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.url).status_code, 401)
        send.assert_not_called()

    @patch("users.views.send_welcome_email")
    def test_rejects_inactive_and_already_used_accounts(self, send):
        for fields in (
            {"is_active": False},
            {"is_active": True, "last_login": timezone.now()},
            {"last_login": None, "must_change_password": False},
        ):
            for name, value in fields.items():
                setattr(self.user, name, value)
            self.user.save()
            self.assertEqual(self.client.post(self.url).status_code, 400)
        send.assert_not_called()
