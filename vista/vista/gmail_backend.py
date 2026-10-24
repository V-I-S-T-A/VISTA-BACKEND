"""Send Django email through Gmail's HTTPS API using a sender refresh token."""

import base64

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

from .email_backend import EmailDeliveryError


class GmailAPIEmailBackend(BaseEmailBackend):
    def _post(self, url, **kwargs):
        # Raise outside the handler so tracebacks cannot expose request bodies,
        # OAuth tokens, verification codes, or provider response bodies.
        failed = False
        try:
            response = requests.post(
                url, timeout=(5, settings.EMAIL_TIMEOUT),
                allow_redirects=False, **kwargs,
            )
        except requests.RequestException:
            failed = True
        if failed:
            raise EmailDeliveryError("Gmail API request failed or timed out.")
        if not 200 <= response.status_code < 300:
            stage = "authorization" if url == "https://oauth2.googleapis.com/token" else "sending"
            # Only fixed, recognized error codes may enter logs. Never include
            # Google's free-form descriptions, response bodies, or credentials.
            hints = {
                "invalid_grant": "invalid_grant: renew the sender refresh token using the matching OAuth client",
                "invalid_client": "invalid_client: check the Gmail OAuth client ID and secret",
                "unauthorized_client": "unauthorized_client: check the Gmail OAuth client configuration",
                "insufficientPermissions": "insufficientPermissions: authorize the gmail.send scope",
                "accessNotConfigured": "accessNotConfigured: enable Gmail API in the email OAuth project",
                "dailyLimitExceeded": "dailyLimitExceeded: check the Google Cloud project's daily API quota",
                "rateLimitExceeded": "rateLimitExceeded: the provider rate limit was reached",
                "userRateLimitExceeded": "userRateLimitExceeded: the sender rate limit was reached",
            }
            hint = ""
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, str):
                    hint = hints.get(error, "")
                elif isinstance(error, dict):
                    errors = error.get("errors", [])
                    for item in errors if isinstance(errors, list) else []:
                        reason = item.get("reason") if isinstance(item, dict) else None
                        if isinstance(reason, str) and reason in hints:
                            hint = hints[reason]
                            break
            suffix = f" {hint}." if hint else ""
            raise EmailDeliveryError(
                f"Gmail API {stage} rejected request (HTTP {response.status_code}).{suffix}"
            )
        invalid = False
        try:
            data = response.json()
        except ValueError:
            invalid = True
        if invalid or not isinstance(data, dict):
            raise EmailDeliveryError("Gmail API returned an invalid response.")
        return data

    def _access_token(self):
        credentials = {
            "client_id": settings.GMAIL_API_CLIENT_ID,
            "client_secret": settings.GMAIL_API_CLIENT_SECRET,
            "refresh_token": settings.GMAIL_API_REFRESH_TOKEN,
        }
        if not all(value.strip() for value in credentials.values()):
            raise ImproperlyConfigured(
                "Gmail API requires GMAIL_API_CLIENT_ID, GMAIL_API_CLIENT_SECRET, "
                "and GMAIL_API_REFRESH_TOKEN."
            )
        data = self._post(
            "https://oauth2.googleapis.com/token",
            data={**credentials, "grant_type": "refresh_token"},
        )
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise EmailDeliveryError("Gmail API did not return an access token.")
        return token

    def send_messages(self, email_messages):
        messages = [message for message in email_messages or [] if message.recipients()]
        if not messages:
            return 0
        try:
            token = self._access_token()
        except (EmailDeliveryError, ImproperlyConfigured):
            if not self.fail_silently:
                raise
            return 0
        sent = 0
        for message in messages:
            mime = message.message()
            # Gmail determines recipients from MIME headers; Django omits Bcc.
            if message.bcc:
                mime["Bcc"] = ", ".join(message.bcc)
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")
            try:
                data = self._post(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"raw": raw},
                )
                if not data.get("id"):
                    raise EmailDeliveryError("Gmail API did not confirm email acceptance.")
            except EmailDeliveryError:
                if not self.fail_silently:
                    raise
            else:
                sent += 1
        return sent
