from types import SimpleNamespace

from django.core import mail
from django.test import SimpleTestCase, override_settings

from .emails import send_welcome_email, send_password_code_email


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    FRONTEND_URL="https://vista-web-production-4086.up.railway.app/",
)
class TransactionalEmailTests(SimpleTestCase):
    def setUp(self):
        self.user = SimpleNamespace(first_name="Alex <Admin>", email="alex@example.com")

    def test_welcome_has_credentials_and_site_in_both_formats(self):
        send_welcome_email(self.user, "Example<&123")
        message = mail.outbox[-1]
        self.assertEqual(message.to, [self.user.email])
        self.assertIn("Example<&123", message.body)
        self.assertIn("https://vista-web-production-4086.up.railway.app/", message.body)
        html = message.alternatives[0].content
        self.assertIn("Alex &lt;Admin&gt;", html)
        self.assertIn("Example&lt;&amp;123", html)
        self.assertIn('href="https://vista-web-production-4086.up.railway.app/"', html)
        self.assertIn("Sign in to VISTA", html)
        self.assertEqual(message.alternatives[0].mimetype, "text/html")

    def test_change_and_reset_codes_have_expiry_and_no_password(self):
        for reset in (False, True):
            send_password_code_email(self.user, SimpleNamespace(code="012345"), reset=reset)
            message = mail.outbox[-1]
            for content in (message.body, message.alternatives[0].content):
                self.assertIn("012345", content)
                self.assertIn("10 minutes", content)
                self.assertNotIn("Temporary password", content)
                self.assertIn("https://vista-web-production-4086.up.railway.app/", content)
            self.assertIn("reset" if reset else "change", message.subject)
