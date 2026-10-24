# Gmail API email on Railway Hobby

This backend sends welcome, password-change, and password-reset email over
HTTPS. It uses one authorized Gmail sender account; recipients do not need
to authorize the app. No custom domain or SMTP connection is needed.

1. In Google Cloud create a separate email project and enable Gmail API.
2. Configure Google Auth Platform for your sender. For a personal Gmail
   account use External and add that account as a test user during setup.
3. Add only the `https://www.googleapis.com/auth/gmail.send` scope.
4. Create a Web application OAuth client with redirect URI
   `https://developers.google.com/oauthplayground`.
5. In Google's OAuth Playground settings select **Use your own OAuth
   credentials**, enter that client's ID and secret, and select Offline
   access and Consent Screen prompting.
6. Authorize the gmail.send scope as the sender and exchange the code for
   tokens. Securely copy the refresh token, not the short-lived access token.
7. Set the following in Railway's Backend service Variables:

   ```dotenv
   EMAIL_BACKEND=vista.gmail_backend.GmailAPIEmailBackend
   GMAIL_API_CLIENT_ID=your-email-client-id
   GMAIL_API_CLIENT_SECRET=your-email-client-secret
   GMAIL_API_REFRESH_TOKEN=your-sender-refresh-token
   DEFAULT_FROM_EMAIL=VISTA <your-authorized-account@gmail.com>
   EMAIL_TIMEOUT=15
   ```

8. Deploy the merged code and variables. Test a password code and welcome
   email to a mailbox you control; verify the inbox/spam folder. API acceptance
   alone is not proof of inbox delivery. Check the user list before retrying
   failed account creation, since the account is saved before email delivery.

EMAIL_BACKEND explicitly selects the provider. A leftover RESEND_API_KEY
does not override it. SMTP credentials and Google App Passwords are not used
by this backend. Keep these credentials separate from VISTA's Drive OAuth
variables and never put them in frontend variables or source control.

External OAuth apps in Testing issue Gmail refresh tokens that expire after
seven days. Arrange appropriate production publishing/verification before
regular use; publishing alone does not guarantee verification or unlimited
access. Tokens can also be revoked, so reauthorization may be necessary.
Gmail sending limits still apply. Requests have bounded connection/read
timeouts and no automatic retries to avoid duplicate messages after an
ambiguous network failure. Error logs omit provider response bodies and tokens.

## Resend a missed invitation

After restoring the sender's Gmail authorization, open Admin > User Management
and choose **Resend invitation** on the affected user's row. Confirm the email
address in the prompt. The action is available only for active accounts that
have never signed in and still require a temporary password.

The admin-only `POST /api/users/{user_id}/resend-invitation/` endpoint sends a
new temporary password and replaces the old password when sending is accepted.
The user should use the newest invitation. Failed sends return HTTP 503 with
`code: invitation_email_failed`; the password change is rolled back so the
administrator can retry after fixing the email service. Invitations are not
retried automatically. A timeout can leave delivery uncertain; an email that
arrives from a failed attempt may contain an unusable password.

Deploy both Backend and Frontend for this action. No database migration is
needed. Verify acceptance in the toast and actual arrival in the inbox/spam
folder; acceptance does not guarantee delivery.

## Diagnose a failed resend on Railway

The `invitation_email_failed` response is generic: it does not establish that
the refresh token expired. In Railway, select the **Backend** service, open
**Variables**, and check `EMAIL_BACKEND` and the three `GMAIL_API_*` variables
listed above. Local `.env` values do not establish what Railway is running.

After deploying the diagnostic changes, retry once and open the Backend's
deployment logs. Look for `Resend invitation failed for user`. The log includes
the authorization/sending stage, HTTP status, and recognized provider reason,
without raw provider messages or tokens:

| Log reason | Action |
| --- | --- |
| `invalid_grant` | Reauthorize the sender in OAuth Playground using your own matching email OAuth client and offline access; replace `GMAIL_API_REFRESH_TOKEN` in Backend Variables and redeploy. |
| `invalid_client` | Check that `GMAIL_API_CLIENT_ID` and `GMAIL_API_CLIENT_SECRET` belong to the client used to issue the refresh token. |
| `insufficientPermissions` | Reauthorize the sender with `https://www.googleapis.com/auth/gmail.send`. |
| `accessNotConfigured` | Enable Gmail API in the project owning the email OAuth client. |
| `dailyLimitExceeded` or rate-limit reasons | Check the project's API quota and sender limits before retrying. |
| `ImproperlyConfigured` | Check the selected email backend and its required Backend Variables. |
| Request failed or timed out | Check service/network availability; delivery may be uncertain. |

An unrecognized provider error retains its stage and HTTP status only. Unexpected
exceptions log the exception type without its potentially sensitive message.
The GUI keeps its generic error and the password transaction is rolled back.
Do not change the separate Drive OAuth variables to repair Gmail sending.

References:
- https://developers.google.com/workspace/gmail/api/guides/sending
- https://developers.google.com/oauthplayground/
- https://developers.google.com/identity/protocols/oauth2/
