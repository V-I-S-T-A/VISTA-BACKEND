# Email on Railway Hobby

SMTP is now the default backend for Railway Pro. To use Gmail, set
`EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, configure the
`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and
`EMAIL_USE_TLS` values shown in `.env.example`, and redeploy after upgrading
Railway. Use a Google App Password, not your normal Google account password.
Any remaining `RESEND_API_KEY` no longer overrides the selected backend.
Remove that variable if you are returning to SMTP.

The following instructions apply only if explicitly choosing Resend instead.

Railway Hobby blocks outbound SMTP. This project can use Resend's HTTPS API
for welcome messages, password-change codes, and password-reset codes.

1. Create a Resend account and verify a sender domain you control, following
   https://resend.com/docs/dashboard/domains/introduction.
2. Create an API key with permission to send email.
3. In Railway's **Backend service Variables**, configure:

   ```dotenv
   EMAIL_BACKEND=vista.email_backend.ResendEmailBackend
   RESEND_API_KEY=your-private-api-key
   DEFAULT_FROM_EMAIL=VISTA <no-reply@your-verified-domain.com>
   EMAIL_TIMEOUT=15
   ```

   Set `EMAIL_BACKEND` explicitly to select Resend. Without a key, selecting the Resend
   backend explicitly fails with a configuration error instead of using SMTP.

4. Deploy the variable changes. A Gmail address cannot substitute for a
   verified Resend sender domain. Resend's test sender has recipient
   restrictions and is not suitable for general user onboarding.
5. Test a welcome email and a password code to a mailbox you control. API
   acceptance does not prove inbox delivery; check the Resend dashboard and
   the recipient's mailbox.

Keep the API key in Railway secrets; never commit it. Existing SMTP settings
are unused when the Resend backend is selected. Console email is available
by explicitly selecting its Django backend; do not use it for production since
message bodies contain temporary passwords and verification codes.

Welcome-email failure preserves the created account and returns
`welcome_email_sent=false`. Check the user list before retrying creation.
Password-change delivery failures return 503. Password-reset requests retain
the same generic response for existing and unknown accounts; failures are
logged without API response bodies. Sending is synchronous with a 5-second
connection timeout and configurable read timeout (15 seconds by default).
No automatic retry is performed, avoiding accidental duplicate messages.
