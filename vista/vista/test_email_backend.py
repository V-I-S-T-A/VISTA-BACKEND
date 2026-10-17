from unittest.mock import patch, Mock
import os
import runpy
from pathlib import Path

import requests
from django.core.mail import send_mail
from django.test import SimpleTestCase, override_settings

from vista.email_backend import EmailDeliveryError


class EmailBackendSelectionTests(SimpleTestCase):
    def test_explicit_backend_overrides_resend_key(self):
        with patch.dict(os.environ, {
            "RESEND_API_KEY": "test-key",
            "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "DEBUG": "False",
        }):
            configured = runpy.run_path(str(Path(__file__).with_name("settings.py")))
        self.assertEqual(configured["EMAIL_BACKEND"], "django.core.mail.backends.smtp.EmailBackend")

    def test_without_key_explicit_backend_is_preserved(self):
        with patch.dict(os.environ, {
            "RESEND_API_KEY": "",
            "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            "DEBUG": "False",
        }):
            configured = runpy.run_path(str(Path(__file__).with_name("settings.py")))
        self.assertEqual(configured["EMAIL_BACKEND"], "django.core.mail.backends.locmem.EmailBackend")


@override_settings(
    EMAIL_BACKEND="vista.email_backend.ResendEmailBackend",
    RESEND_API_KEY="test-key",
    DEFAULT_FROM_EMAIL="VISTA <sender@example.com>",
    EMAIL_TIMEOUT=15,
)
class ResendBackendTests(SimpleTestCase):
    @patch("vista.email_backend.requests.post")
    def test_send_mail_uses_https_and_timeout(self, post):
        post.return_value = Mock(status_code=200)
        self.assertEqual(send_mail("Subject", "Body", None, ["user@example.com"]), 1)
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.resend.com/emails")
        self.assertEqual(kwargs["json"]["text"], "Body")
        self.assertEqual(kwargs["json"]["from"], "VISTA <sender@example.com>")
        self.assertEqual(kwargs["timeout"], (5, 15))
        self.assertFalse(kwargs["allow_redirects"])

    @patch("vista.email_backend.requests.post")
    def test_rejection_raises_sanitized_error(self, post):
        post.return_value = Mock(status_code=403, text="secret response")
        with self.assertRaisesRegex(EmailDeliveryError, r"HTTP 403"):
            send_mail("Subject", "secret", None, ["user@example.com"])

    @patch("vista.email_backend.requests.post", side_effect=requests.Timeout("secret"))
    def test_timeout_is_sanitized_and_fail_silently_is_supported(self, post):
        with self.assertRaisesRegex(EmailDeliveryError, "failed or timed out") as error:
            send_mail("Subject", "Body", None, ["user@example.com"])
        self.assertIsNone(error.exception.__context__)
        self.assertEqual(send_mail("Subject", "Body", None, ["user@example.com"], fail_silently=True), 0)

    @override_settings(RESEND_API_KEY="")
    @patch("vista.email_backend.requests.post")
    def test_missing_key_does_not_make_network_request(self, post):
        self.assertEqual(send_mail("Subject", "Body", None, ["user@example.com"], fail_silently=True), 0)
        post.assert_not_called()
