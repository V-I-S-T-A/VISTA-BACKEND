"""Django email backend using Resend's HTTPS API (no SMTP connection)."""

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend


class EmailDeliveryError(Exception):
    """A sanitized delivery error safe to include in application logs."""


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages or []:
            if not message.recipients():
                continue
            try:
                self._send(message)
            except (EmailDeliveryError, ImproperlyConfigured):
                if not self.fail_silently:
                    raise
            else:
                sent += 1
        return sent

    def _send(self, message):
        if not settings.RESEND_API_KEY:
            raise ImproperlyConfigured("RESEND_API_KEY is required for Resend email delivery.")
        if message.attachments:
            raise EmailDeliveryError("Attachments are not supported by this email backend.")
        payload = {
            "from": message.from_email,
            "subject": message.subject,
            "html" if message.content_subtype == "html" else "text": message.body,
        }
        for field in ("to", "cc", "bcc", "reply_to"):
            if getattr(message, field):
                payload[field] = list(getattr(message, field))
        for alternative in getattr(message, "alternatives", []):
            if alternative.mimetype == "text/html":
                payload["html"] = alternative.content
        # Never log response bodies or request exceptions: they can contain
        # recipients, verification codes, temporary passwords, or API keys.
        failed = False
        try:
            response = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json=payload,
                timeout=(5, settings.EMAIL_TIMEOUT),
                allow_redirects=False,
            )
        except requests.RequestException:
            failed = True
        if failed:
            raise EmailDeliveryError("Resend email request failed or timed out.")
        if not 200 <= response.status_code < 300:
            raise EmailDeliveryError(f"Resend rejected email (HTTP {response.status_code}).")
