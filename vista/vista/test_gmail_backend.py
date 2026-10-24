import base64
from email import message_from_bytes
from unittest.mock import Mock, patch

import requests
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives, send_mail
from django.test import SimpleTestCase, override_settings

from vista.email_backend import EmailDeliveryError


@override_settings(
    EMAIL_BACKEND="vista.gmail_backend.GmailAPIEmailBackend",
    GMAIL_API_CLIENT_ID="test-client",
    GMAIL_API_CLIENT_SECRET="test-secret",
    GMAIL_API_REFRESH_TOKEN="test-refresh",
    DEFAULT_FROM_EMAIL="VISTA <sender@example.com>",
    EMAIL_TIMEOUT=15,
)
class GmailBackendTests(SimpleTestCase):
    @patch("vista.gmail_backend.requests.post")
    def test_send_mail_refreshes_then_sends_mime_over_https(self, post):
        post.side_effect = [
            Mock(status_code=200, json=lambda: {"access_token": "test-token"}),
            Mock(status_code=200, json=lambda: {"id": "message-id"}),
        ]
        self.assertEqual(send_mail("Code", "Your code is 123456", None, ["to@example.com"]), 1)
        refresh, delivery = post.call_args_list
        self.assertEqual(refresh.args[0], "https://oauth2.googleapis.com/token")
        self.assertEqual(refresh.kwargs["data"]["grant_type"], "refresh_token")
        self.assertEqual(delivery.args[0], "https://gmail.googleapis.com/gmail/v1/users/me/messages/send")
        self.assertEqual(delivery.kwargs["headers"]["Authorization"], "Bearer test-token")
        mime = message_from_bytes(base64.urlsafe_b64decode(delivery.kwargs["json"]["raw"]))
        self.assertEqual(mime["To"], "to@example.com")
        self.assertIn(b"123456", mime.get_payload(decode=True))
        for call in post.call_args_list:
            self.assertEqual(call.kwargs["timeout"], (5, 15))
            self.assertFalse(call.kwargs["allow_redirects"])

    @patch("vista.gmail_backend.requests.post")
    def test_html_and_bcc_are_in_mime(self, post):
        post.side_effect = [
            Mock(status_code=200, json=lambda: {"access_token": "test-token"}),
            Mock(status_code=200, json=lambda: {"id": "message-id"}),
        ]
        message = EmailMultiAlternatives("Subject", "Text", to=["to@example.com"], bcc=["hidden@example.com"])
        message.attach_alternative("<p>HTML</p>", "text/html")
        self.assertEqual(message.send(), 1)
        mime = message_from_bytes(base64.urlsafe_b64decode(post.call_args.kwargs["json"]["raw"]))
        self.assertEqual(mime["Bcc"], "hidden@example.com")
        self.assertTrue(mime.is_multipart())

    @patch("vista.gmail_backend.requests.post", side_effect=requests.Timeout("private-token"))
    def test_timeout_is_sanitized(self, post):
        with self.assertRaises(EmailDeliveryError) as caught:
            send_mail("Subject", "Body", None, ["to@example.com"])
        self.assertNotIn("private-token", str(caught.exception))
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(send_mail("Subject", "Body", None, ["to@example.com"], fail_silently=True), 0)

    @patch("vista.gmail_backend.requests.post")
    def test_revoked_token_and_delivery_rejection(self, post):
        for responses in (
            [Mock(status_code=400)],
            [Mock(status_code=200, json=lambda: {"access_token": "token"}), Mock(status_code=403)],
        ):
            post.side_effect = responses
            with self.assertRaises(EmailDeliveryError):
                send_mail("Subject", "Body", None, ["to@example.com"])

    @patch("vista.gmail_backend.requests.post")
    def test_authorization_failure_identifies_cause_without_provider_details(self, post):
        post.return_value = Mock(status_code=400, json=lambda: {
            "error": "invalid_grant", "error_description": "private-token-and-account",
        })
        with self.assertRaisesRegex(EmailDeliveryError, "authorization.*invalid_grant") as caught:
            send_mail("Subject", "Body", None, ["to@example.com"])
        self.assertNotIn("private-token-and-account", str(caught.exception))
        self.assertEqual(post.call_count, 1)

    @patch("vista.gmail_backend.requests.post")
    def test_send_permission_failure_is_sanitized(self, post):
        post.side_effect = [
            Mock(status_code=200, json=lambda: {"access_token": "token"}),
            Mock(status_code=403, json=lambda: {"error": {
                "message": "private-body",
                "errors": [{"reason": "insufficientPermissions", "message": "private-message"}],
            }}),
        ]
        with self.assertRaisesRegex(EmailDeliveryError, "sending.*gmail.send") as caught:
            send_mail("Subject", "Body", None, ["to@example.com"])
        self.assertNotIn("private", str(caught.exception))

    @patch("vista.gmail_backend.requests.post")
    def test_unknown_or_malformed_error_body_stays_private(self, post):
        for payload in (
            {"error": "private-provider-detail"},
            {"error": {"errors": [{"reason": "private-provider-detail"}]}},
            {"error": {"errors": [{"reason": ["invalid_grant"]}]}},
            {"error": {"errors": "private-provider-detail"}},
            [],
        ):
            with self.subTest(payload=payload):
                post.return_value = Mock(status_code=403, json=lambda: payload)
                with self.assertRaises(EmailDeliveryError) as caught:
                    send_mail("Subject", "Body", None, ["to@example.com"])
                self.assertNotIn("private", str(caught.exception))
                self.assertNotIn("invalid_grant", str(caught.exception))
        post.return_value = Mock(status_code=502)
        post.return_value.json.side_effect = ValueError("private-response")
        with self.assertRaisesRegex(EmailDeliveryError, "HTTP 502") as caught:
            send_mail("Subject", "Body", None, ["to@example.com"])
        self.assertIsNone(caught.exception.__context__)

    @override_settings(GMAIL_API_REFRESH_TOKEN="")
    @patch("vista.gmail_backend.requests.post")
    def test_missing_credentials_fail_before_network(self, post):
        with self.assertRaises(ImproperlyConfigured):
            send_mail("Subject", "Body", None, ["to@example.com"])
        post.assert_not_called()

    @patch("vista.gmail_backend.requests.post")
    def test_malformed_success_is_not_counted_as_delivery(self, post):
        post.side_effect = [
            Mock(status_code=200, json=lambda: {"access_token": "token"}),
            Mock(status_code=200, json=lambda: {}),
        ]
        with self.assertRaisesRegex(EmailDeliveryError, "confirm email acceptance"):
            send_mail("Subject", "Body", None, ["to@example.com"])
