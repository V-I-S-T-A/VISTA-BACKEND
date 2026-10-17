# VISTA deployment guide: Railway, Google APIs, Cloudinary, and React

Last reviewed: October 17, 2026.

This guide covers deploying the Django API, React website, Celery worker,
PostgreSQL, and Redis, then configuring file storage, OCR, email, and Google
Drive. The primary email configuration uses Gmail API over HTTPS so Railway
Hobby does not require SMTP access or an independently registered email domain.

This is an operational guide, not a claim that every function has been tested
in production. Complete the acceptance checklist before handing over the site.
Provider menus, prices, quotas, and OAuth policies can change; official links
are provided at the end.

## Contents

1. [Architecture and prerequisites](#1-architecture-and-prerequisites)
2. [Prepare repositories](#2-prepare-repositories)
3. [Create Railway databases](#3-create-railway-databases)
4. [Configure Cloudinary](#4-configure-cloudinary)
5. [Deploy the Django Backend](#5-deploy-the-django-backend)
6. [Configure Gmail API email](#6-configure-gmail-api-email)
7. [Configure Google Drive](#7-configure-google-drive)
8. [Deploy the Celery Worker](#8-deploy-the-celery-worker)
9. [Deploy the React Frontend](#9-deploy-the-react-frontend)
10. [Create the first administrator](#10-create-the-first-administrator)
11. [Initialize reference data and test OCR](#11-initialize-reference-data-and-test-ocr)
12. [Acceptance checklist](#12-acceptance-checklist)
13. [Troubleshooting](#13-troubleshooting)
14. [Updates, backups, and cost control](#14-updates-backups-and-cost-control)
15. [Email alternatives](#15-email-alternatives)
16. [Official references](#16-official-references)

## 1. Architecture and prerequisites

Deploy these five services in the same Railway project and environment:

| Service name used in this guide | Source | Public access |
| --- | --- | --- |
| `VISTA-BACKEND` | `V-I-S-T-A/VISTA-BACKEND`, root `/vista`, Dockerfile | HTTPS domain |
| `Worker` | Same backend repository, root `/vista`, same Dockerfile | None |
| `Postgres` | Railway PostgreSQL database | Keep private |
| `Redis` | Railway Redis database | Keep private |
| `Frontend` | `V-I-S-T-A/VISTA-WEB`, repository root | HTTPS domain |

The browser calls the public API domain. Django and Celery connect privately
to Postgres and Redis. Uploads use Cloudinary; Drive tasks fetch stored document
URLs and send files to the connected staff member's selected Drive folder.
Gmail API sends account and password emails independently of Drive OAuth.

Prerequisites:

- GitHub access to both repositories and permission to connect them to Railway.
- A Railway account with an appropriate paid plan and a configured payment method.
- Google Cloud access and a Gmail account authorized to send VISTA notifications.
- A Cloudinary account.
- Node/npm and Git locally. Python and the backend virtual environment are
  needed for local checks, but Railway builds the production Python environment.
- Railway CLI for production administration, plus Windows OpenSSH for SSH.

Hobby's advertised monthly amount is a minimum usage commitment, not an
unlimited hosting bundle. Web, worker, databases, CPU-intensive OCR, storage,
and outbound traffic contribute to usage. Measure real consumption rather
than assuming the complete system stays within the included credit.

### URL conventions

The following are this project's deployment URLs from the setup session;
substitute your generated domains if recreating the deployment:

```text
Backend:  https://vista-backend-production-10d7.up.railway.app
Frontend: https://vista-web-production-4086.up.railway.app
```

| Setting | Format |
| --- | --- |
| `ALLOWED_HOSTS` | Backend hostname only, no scheme or path |
| `CORS_ALLOWED_ORIGINS` | Frontend HTTPS origin, no trailing slash |
| `CSRF_TRUSTED_ORIGINS` | Frontend HTTPS origin, no trailing slash |
| `VITE_API_URL` | Public backend URL ending in `/api` |
| `FRONTEND_URL` | Public website URL used by email buttons |
| `GOOGLE_OAUTH_REDIRECT_URI` | Backend HTTPS URL ending in `/api/drive/auth/callback/` |

## 2. Prepare repositories

1. Commit and push the desired code to GitHub through your normal PR workflow.
2. Select the intended deployment branch in each Railway service. Creating a
   PR alone does not deploy its changes: merge it into the configured branch,
   or deliberately configure a test service to use the feature branch.
3. Backend and Worker should deploy the same backend revision.
4. Confirm the frontend includes `serve` in dependencies and these scripts:

   ```json
   "build": "vite build",
   "start": "serve -s dist -l $PORT"
   ```

5. Confirm the backend Dockerfile installs Tesseract and Poppler and starts:

   ```dockerfile
   CMD ["/bin/sh", "-c", "exec gunicorn vista.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --timeout 120"]
   ```

   Railway's assigned `PORT` must match the listening port. `EXPOSE 8000`
   alone does not cause Gunicorn to use Railway's runtime port.

6. Keep real `.env` files, OAuth tokens, and credentials out of Git and the
   Docker build context. Inspect `.gitignore` and `.dockerignore` before
   deployment. `COPY . .` copies any non-excluded build-context files, so do
   not assume that an ignored local file is safe in every deployment method.
7. Do not copy the old `app.yaml` into Railway configuration: it is a
   DigitalOcean specification. The local Compose file is also not the full
   production deployment definition; create the Railway services below.

Frontend and backend are separate Git repositories. Run Git commands from
the relevant directory, not the parent `thesis` folder.

## 3. Create Railway databases

1. Create an empty Railway project named `VISTA`.
2. Choose the production environment and keep all five services there.
3. Add a PostgreSQL database and name it `Postgres`.
4. Add Redis and name it `Redis`.
5. Wait for both to start. Confirm their persistent storage is provisioned.
6. Keep their public TCP access disabled unless a specific administrative
   workflow requires it. Internal references work only within the same
   project/environment, not from a local PowerShell process.

The reference expressions below use exact service names. If you choose other
names, use Railway's variable autocomplete to select their corresponding values.

## 4. Configure Cloudinary

1. Create or select the production Cloudinary environment.
2. Retrieve its cloud name, API key, and API secret from the Cloudinary dashboard.
3. Set these on Backend and Worker:

   ```dotenv
   CLOUDINARY_CLOUD_NAME=<cloud-name>
   API_KEY=<cloudinary-api-key>
   API_SECRET=<cloudinary-api-secret>
   ```

These names are the ones read by `vista/settings.py`. Do not replace them with
different variable names without changing the code. Never put the API secret
in a frontend `VITE_*` variable.

Test both image and document uploads. A successful image upload alone does
not prove PDF document delivery works. Confirm document URLs are accessible
to the Drive worker under the Cloudinary environment's access policies.

## 5. Deploy the Django Backend

### 5.1 Create the service

1. Add a GitHub repository service using `V-I-S-T-A/VISTA-BACKEND`.
2. Name it `VISTA-BACKEND` and select the intended branch, usually `main`.
3. Set **Root Directory** to `/vista`.
4. Let Railway detect `vista/Dockerfile` relative to the repository layout.
   With `/vista` selected as root, the build context contains `manage.py`,
   `requirements.txt`, and `entrypoint.sh`.
5. Leave the custom start command empty so the Dockerfile starts Gunicorn.
6. Do not run `migrate` in the Docker build: database private networking is
   needed at runtime, not while installing image dependencies.

### 5.2 Set runtime variables

Open the Backend's **Variables** tab. For individual entries, put only the
value in the value field; do not paste the `NAME=` prefix there. Raw Editor
can accept whole `NAME=value` lines. Replace placeholders with actual values.

```dotenv
DEBUG=False
DJANGO_SECRET_KEY=<new-production-secret>
DB_HOST=${{Postgres.PGHOST}}
DB_PORT=${{Postgres.PGPORT}}
DB_NAME=${{Postgres.PGDATABASE}}
DB_USER=${{Postgres.PGUSER}}
DB_PASSWORD=${{Postgres.PGPASSWORD}}
CELERY_BROKER_URL=${{Redis.REDIS_URL}}
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}
CLOUDINARY_CLOUD_NAME=<cloud-name>
API_KEY=<cloudinary-api-key>
API_SECRET=<cloudinary-api-secret>
TESSERACT_PATH=/usr/bin/tesseract
POPPLER_PATH=/usr/bin
```

The project reads `DJANGO_SECRET_KEY`, not `SECRET_KEY`. Generate a fresh
value locally using the backend Python environment:

```powershell
cd C:\Users\moyar\Documents\thesis\VISTA-BACKEND\vista
.\venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Store the result privately. Do not copy the development fallback secret into
production. Use `True` or `False` for `DEBUG`, not a label such as `release`.

The current database settings use the individual `DB_*` values; setting only
`DATABASE_URL` is insufficient. The inspected settings do not read a
`DB_SSLMODE` variable, so adding that variable alone does not configure SSL.
Review Django database `OPTIONS` explicitly if your database provider requires
a particular TLS mode.

### 5.3 Generate a public domain and configure origins

In **Settings → Networking → Public Networking**, generate a backend domain.
Configure the domain target to the port used by the deployed process. With
Railway `PORT=8080`, Gunicorn should log `0.0.0.0:8080`.

For the URLs above, set:

```dotenv
ALLOWED_HOSTS=vista-backend-production-10d7.up.railway.app
CORS_ALLOWED_ORIGINS=https://vista-web-production-4086.up.railway.app
CSRF_TRUSTED_ORIGINS=https://vista-web-production-4086.up.railway.app
FRONTEND_URL=https://vista-web-production-4086.up.railway.app
```

If creating the frontend later, return and replace these example origins with
the actual generated domain. Multiple hosts/origins are comma-separated.
Do not include Markdown link syntax, brackets, or literal quotation marks
in values entered through the individual variable UI.

### 5.4 Check startup

Apply staged changes and deploy. Expected milestones in deployment logs:

```text
Waiting for database...
Database is up.
Running migrations:
... static files copied ...
Starting gunicorn ...
Listening at: http://0.0.0.0:8080
```

The Docker entrypoint waits for Postgres, runs migrations, collects static
files, then starts the configured command. A database or settings failure
before Gunicorn starts can produce Railway's `Application failed to respond`.

Test `/admin/login/`. A 404 at the bare backend `/` is expected because no
homepage route is defined. Do not configure `/` as an HTTP-200 health check.
There is no dedicated application health endpoint in the inspected URL config.

**Static-file limitation:** `collectstatic` only collects files. The current
Gunicorn setup does not itself serve `STATIC_ROOT`, and no WhiteNoise/static
server is configured in the inspected settings. Django Admin may therefore
load without styling when `DEBUG=False`. Before relying on the admin UI in
production, add a proper static-file serving solution in a separate change.
Do not enable production `DEBUG` to work around this. React assets are served
by the separate Frontend service.

## 6. Configure Gmail API email

Gmail API uses HTTPS rather than SMTP and can run on Railway Hobby. A custom
email domain is unnecessary when sending from the Gmail account that grants
authorization. Email recipients do not authorize OAuth; only the sender does.

### 6.1 Google Cloud setup

1. Create a separate Google Cloud project such as `VISTA Email`.
2. Under **APIs & Services → Library**, enable **Gmail API**.
3. Configure Google Auth Platform branding, support email, and contact email.
4. For a personal Gmail sender, select External audience. While testing, add
   the sender Gmail address to Test users.
5. In Data Access, add only:

   ```text
   https://www.googleapis.com/auth/gmail.send
   ```

6. Create a Web application OAuth client named `VISTA Email Authorization`.
7. Add the following exact authorized redirect URI:

   ```text
   https://developers.google.com/oauthplayground
   ```

8. Securely retain that client's ID and secret. Do not replace the existing
   Drive OAuth client values with these Gmail credentials.

### 6.2 Obtain the sender refresh token

1. Open Google's OAuth Playground from the references section below.
2. Open its gear/settings panel.
3. Enable **Use your own OAuth credentials** and enter the email client's
   ID and secret. The default Playground credentials are unsuitable for
   persistent deployment because Playground revokes their tokens after 24 hours.
4. Select Server-side flow, Offline access, and Consent Screen prompting.
5. Enter the `gmail.send` scope shown above and click Authorize APIs.
6. Sign in as the intended sender and review/grant access for your own app.
7. Exchange the authorization code for tokens.
8. Securely save the **refresh token**, not the short-lived access token.

An access token lasting about one hour is normal. The implemented backend
obtains an access token from the refresh token for each non-empty send batch.
No manual access-token renewal is necessary.

External OAuth apps in Testing issue Gmail refresh tokens that expire after
seven days. For ongoing operation, arrange appropriate production publishing
and verification, then reauthorize and deploy the new refresh token. Publishing
is not the same as Google verification and does not guarantee permanent token
validity. Account changes, revoked access, or Google policy can invalidate tokens.

### 6.3 Railway email variables

Set these on **VISTA-BACKEND**, where account creation and password emails run:

```dotenv
EMAIL_BACKEND=vista.gmail_backend.GmailAPIEmailBackend
GMAIL_API_CLIENT_ID=<email-oauth-client-id>
GMAIL_API_CLIENT_SECRET=<matching-email-oauth-client-secret>
GMAIL_API_REFRESH_TOKEN=<refresh-token-issued-to-that-client>
DEFAULT_FROM_EMAIL=VISTA <your-authorized-sender@gmail.com>
EMAIL_TIMEOUT=15
```

The client ID, secret, and refresh token must belong together. Leave out
literal placeholder brackets when entering real values. Select the backend
explicitly; unset `EMAIL_BACKEND` defaults to the console backend in the
inspected revision. Console email writes temporary passwords/OTPs to logs
and does not deliver them. Never use it in production.

Deploy and test a controlled password-code email. Verify receipt in the mailbox
and spam folder, not just the API response. Registration messages include a
website button controlled by `FRONTEND_URL`. OTP emails include ten-minute
expiry guidance. HTML and plain-text versions use the same content.

If welcome delivery fails, the account is still saved and the API reports
`welcome_email_sent=false`. Avoid repeatedly creating the same account.
An accepted email request does not guarantee inbox delivery, and changing a
variable does not resend a previously failed welcome email automatically.

See [GMAIL_API.md](vista/GMAIL_API.md) for the focused email guide.

## 7. Configure Google Drive

The current code uses staff Google OAuth connections stored in PostgreSQL,
with tokens encrypted using `DRIVE_TOKEN_ENCRYPTION_KEY`. It does not use a
central service-account credential file. Older project notes may describe
another design; follow the active `integrations` implementation.

1. Select the Google Cloud project used for Drive integration.
2. Enable **Google Drive API** and configure its OAuth audience/consent.
3. Create or update its Web application OAuth client.
4. Add this exact authorized redirect URI:

   ```text
   https://vista-backend-production-10d7.up.railway.app/api/drive/auth/callback/
   ```

5. Generate a Fernet key privately using the backend Python environment:

   ```powershell
   .\venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

6. Set the same values on Backend and Worker:

   ```dotenv
   GOOGLE_OAUTH_CLIENT_ID=<drive-client-id>
   GOOGLE_OAUTH_CLIENT_SECRET=<drive-client-secret>
   GOOGLE_OAUTH_REDIRECT_URI=https://vista-backend-production-10d7.up.railway.app/api/drive/auth/callback/
   DRIVE_TOKEN_ENCRYPTION_KEY=<fernet-key>
   ```

7. Deploy, sign in to VISTA as staff, open the Drive integration screen,
   connect the intended Google account, and choose/create the target folder.
8. Test the approved-submission Drive confirmation and resulting upload.

Do not regenerate the encryption key on every deploy. Existing database tokens
cannot be decrypted with a different key. Back up the key securely alongside
database recovery procedures. Drive OAuth testing/token-expiration policies
also need review before sustained deployment. The implementation includes both
`drive.file` and full-Drive scope paths; review actual granted scopes and
verification requirements instead of assuming Gmail's send-only requirements apply.

## 8. Deploy the Celery Worker

1. Add the backend GitHub repository a second time and name the service Worker.
2. Select the same branch/revision and root `/vista` as Backend.
3. Set the custom start command to:

   ```text
   celery -A vista worker -l info --concurrency=1
   ```

4. Configure the same Django secret, database, Redis, Cloudinary, Drive, and
   Linux OCR variables as Backend. Shared Railway variables or service
   references can reduce duplication; verify they are actually attached to
   both services.
5. Do not generate a public domain for Worker.
6. Start Backend first, wait for migrations to finish, then deploy Worker.

Worker also uses the Docker entrypoint, so it currently runs `migrate` and
`collectstatic` before starting Celery. Avoid simultaneous first deployments
that both attempt schema changes. A future release-command migration design
would be preferable for more complex production releases.

Expected logs include connection to Redis followed by `celery@... ready`.
The root-user warning is a security advisory, not proof that jobs failed.
Running as a non-root container user requires a separately tested Docker
ownership/user change; do not add an arbitrary UID without checking permissions.

Keep the worker available while Drive jobs are expected. Sleeping a continuous
worker or broker can delay background tasks. Verify how sleeping and Redis
connections affect costs before enabling serverless behavior.

## 9. Deploy the React Frontend

1. Add `V-I-S-T-A/VISTA-WEB` as a GitHub service named Frontend.
2. Select the branch containing the desired UI and the `serve` dependency.
3. Leave Root Directory empty or `/`: `package.json` is at repository root.
4. Set Build Command to `npm run build` and Start Command to `npm start`.
   Railway's Node builder should install dependencies before building.
5. Add this variable on Frontend only:

   ```dotenv
   VITE_API_URL=https://vista-backend-production-10d7.up.railway.app/api
   ```

6. Deploy and generate its public HTTPS domain. Confirm the domain target
   matches the port printed by `serve`.
7. Return to Backend and update CORS, CSRF, and `FRONTEND_URL` to this actual
   frontend domain. Deploy Backend's variable changes.
8. Test the homepage, `/login`, and a hard refresh of a nested dashboard URL.
   `serve -s` provides the React Router fallback to `index.html`.

Vite compiles `VITE_API_URL` into the browser bundle during the build. Changing
it requires rebuilding/redeploying Frontend, not just restarting an old image.
Browser requests cannot use Railway's private `.railway.internal` domains.

No frontend `VITE_*` variable may contain server secrets. All such values are
public to the browser. Do not use `vite` development server or `vite preview`
as the production start command.

The npm script's `$PORT` expansion is intended for the Linux deployment shell.
Local Windows npm shell behavior can differ; test the production build locally
with an appropriate explicit port when necessary.

## 10. Create the first administrator

Install Railway CLI and link to the correct project/environment/service from
PowerShell:

```powershell
npm install -g @railway/cli
railway login
cd C:\Users\moyar\Documents\thesis\VISTA-BACKEND
railway link
railway ssh -s VISTA-BACKEND
```

If PowerShell blocks the npm `.ps1` launcher, use `railway.cmd` instead of
changing machine-wide execution policy. If no SSH key exists:

```powershell
ssh-keygen -t ed25519 -C "railway"
```

Accept the default key path only if it does not overwrite an existing key.
Keep the private key private; the `.pub` file is its public counterpart.
Retry Railway SSH and follow the key-registration prompts. Verify unfamiliar
SSH host fingerprints through a trusted provider channel before accepting.

Inside the deployed container:

```sh
cd /app
python manage.py createsuperuser
```

Enter email, first name, last name, and password. Password input is invisible.
The custom user manager sets `role=admin`, `is_staff=True`, and
`is_superuser=True`. This changes the deployed database, not the local one.

Sign in through the React frontend, or test Django Admin at `/admin/login/`.
Then `exit` the SSH shell. Do not put `createsuperuser` in the recurring service
start command or commit an administrator password into configuration.

`railway run` executes locally with Railway variables; it is not the same as
SSH into the deployed container and cannot generally resolve private database
hostnames from your laptop. Prefer SSH for these administration steps.

## 11. Initialize reference data and test OCR

An empty migrated database is not automatically a fully configured VISTA.
Use the application's admin workflows or a reviewed import process to create
organizations, academic years, categories, and document types. Inspect existing
data migrations before duplicating entries; this guide does not assume a seed
command exists.

OCR suggestions depend on these records. Document type codes must match the
pipeline mappings. The autofill handler explicitly checks `FM-USTP-OSA-11`
for Off-Campus and uses In-Campus for other recognized types; verify category
names and actual templates against the current source before populating data.

The Dockerfile provides Tesseract, Poppler, Pillow/OpenCV dependencies. Linux
deployment variables must not contain your Windows installation paths:

```dotenv
TESSERACT_PATH=/usr/bin/tesseract
POPPLER_PATH=/usr/bin
```

The OCR pipeline reads `TESSERACT_PATH`. The current PDF loader relies on
Linux PATH for Poppler; it does not read `POPPLER_PATH` on Linux. The variable
above is a useful convention, not proof that every loader honors it.

Inside Backend SSH, check dependencies:

```sh
tesseract --version
pdftoppm -v
```

Test a supported form as both an image and PDF through document registration.
Verify suggestions and manually review fields. OCR is a draft aid and does not
replace final human submission. The current PDF loader renders PDF pages at
300 DPI before selecting the first page; large/multi-page PDFs may consume
substantial memory. Test realistic documents and monitor the service rather
than assuming unlimited file size or OCR concurrency.

## 12. Acceptance checklist

Complete these on a controlled test account/document before production handover:

- [ ] Backend and Frontend deployment revisions match the intended release.
- [ ] Backend listens on Railway's assigned port and `/admin/login/` responds.
- [ ] Frontend homepage, login, and nested-route refresh work.
- [ ] Login succeeds without CORS/preflight errors; credentials fail gracefully.
- [ ] Admin creates a test staff/student account once; email reaches the mailbox.
- [ ] Welcome email website button opens the deployed frontend.
- [ ] Temporary-password workflow requires a password change as intended.
- [ ] Password-change OTP arrives; valid, invalid, and expired code handling work.
- [ ] Password-reset workflow works without exposing whether an account exists.
- [ ] Profile images and submission files upload to Cloudinary.
- [ ] Uploaded files remain accessible after Backend redeployment.
- [ ] Supported image and PDF OCR produce a draft or usable manual-entry fallback.
- [ ] Staff can authorize Drive and select/create a folder.
- [ ] Approved review invokes its confirmation and uploads through Worker.
- [ ] Returned review does not incorrectly require Drive confirmation.
- [ ] Worker logs show actual task processing, not only broker connection.
- [ ] PostgreSQL data survives service restarts/redeployment.
- [ ] Backups and recovery instructions include the Drive encryption key.
- [ ] Real usage and email/Google quotas are reviewed.

Existing UI controls do not prove backend persistence. In particular, verify
date-of-birth model/serializer/payload support before describing birthday input
as persistent. Do not include that as a successful deployment claim based only
on the form being visible.

## 13. Troubleshooting

### Railway 502 / Application failed to respond

Inspect Backend deployment logs before changing CORS. A Railway-generated
502 has no Django CORS headers and browsers can present it as a CORS error.
Confirm database startup, required settings, Gunicorn startup, assigned PORT,
and public domain target port. A running Celery worker does not prove the
web service is healthy. An ordinary 404 at backend `/` is a different condition.

### Missing Access-Control-Allow-Origin

Confirm the deployed code reads environment-driven CORS and the exact frontend
origin appears in Backend variables. Inspect safe runtime settings via SSH:

```sh
python manage.py shell -c "from django.conf import settings; print(settings.CORS_ALLOWED_ORIGINS); print(settings.CSRF_TRUSTED_ORIGINS); print(settings.ALLOWED_HOSTS)"
```

From PowerShell, issue a read-only preflight:

```powershell
curl.exe -i -X OPTIONS "https://vista-backend-production-10d7.up.railway.app/api/auth/login/" -H "Origin: https://vista-web-production-4086.up.railway.app" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: content-type"
```

Expect the allowed frontend origin in `access-control-allow-origin`. If the
response is 502, address upstream availability first. Missing settings in an
AttributeError often indicate a different/older deployed branch or settings module.

### Website still calls localhost

Set Frontend `VITE_API_URL` before building and trigger a new build. Confirm
the service source repository and branch rather than relying on local changes.

### Email prints in logs instead of reaching an inbox

The console backend is selected. Set `EMAIL_BACKEND` explicitly and redeploy.
Check provider selection and credential presence without displaying secrets:

```sh
python manage.py shell -c "from django.conf import settings; print(settings.EMAIL_BACKEND); print('Gmail refresh token configured:', bool(settings.GMAIL_API_REFRESH_TOKEN.strip()))"
```

Treat any temporary password or OTP printed in shared logs as exposed. Replace
affected credentials, restrict log access, and stop console email in production.
Do not paste entire mail logs containing passwords into support requests.

### Gmail API HTTP 400 during _access_token

The refresh request failed before Gmail accepted an email. Verify that the
client ID, secret, and refresh token belong together. Check whether the token
was revoked, issued using Playground's default client, or expired under Testing.
Reauthorize with your own client and deploy the new refresh token. Do not
substitute the access token or authorization code for the refresh token.
The sanitized HTTP status alone does not establish the provider's exact cause.

### Gmail accepts the request but no email arrives

Check the authorized sender's Sent folder and the recipient's Spam/All Mail,
recipient spelling, and account limits. Confirm that the registration request
reported successful delivery acceptance. Existing accounts are not automatically
resent welcome messages when changing provider settings. Test a controlled OTP
before concluding the mailbox integration works.

### SMTP Network is unreachable or worker timeout

Railway Hobby blocks SMTP. Use Gmail API/Resend HTTPS or upgrade to Pro and
redeploy the affected service. Increasing Gunicorn timeout or moving the same
blocked SMTP request into Celery does not remove the restriction.

### OCR HTTP 500

Read Backend logs, not only Redis/Postgres logs. Check Tesseract's path,
dependencies, input format, and memory/timeout metrics. Windows paths such as
`C:\Program Files\Tesseract-OCR\tesseract.exe` are invalid in the Linux container.
Successful Redis saves/PostgreSQL checkpoints are routine database maintenance,
not evidence of an OCR error. The current endpoint may return an unhandled
500 for processing errors; manual entry is the frontend fallback, not proof
that the OCR service passed validation.

### Drive upload stuck / OAuth redirect mismatch

Confirm Worker is ready and uses the same Redis, database, OAuth client, and
encryption key as Backend. Verify staff authorization and selected folder.
The callback URL must match Google Console exactly, including HTTPS and the
trailing slash. Expired OAuth access may require reconnecting the staff account.
Check Cloudinary document URL access if a task fails fetching the original file.

## 14. Updates, backups, and cost control

For each release:

1. Review and merge changes into the configured deployment branches.
2. Back up PostgreSQL before schema/data changes. Confirm a usable restore
   procedure; an untested backup is not evidence of recoverability.
3. Deploy Backend, monitor migrations and readiness, then deploy Worker.
4. Rebuild Frontend if its source or build-time API URL changed.
5. Run affected acceptance checks and inspect provider/API delivery outcomes.

A code rollback does not roll back database migrations. Evaluate schema
compatibility and restore needs before reverting application versions. Do not
delete production database/Redis services or volumes as a routine troubleshooting
step. Preserve Cloudinary assets and Drive data according to retention needs.

Railway container filesystems are ephemeral unless explicitly backed by persistent
storage. The current document path uses external URLs, but audit any new feature
that writes `/app/media` before assuming it survives a redeploy. Avoid attaching
separate per-service volumes and expecting Backend and Worker to share a folder.

Back up database credentials, application secret, and Drive encryption key through
an appropriate secret manager. Limit who can view Railway logs/variables. Rotate
exposed credentials without posting them in issues, PRs, or documentation.

Use Railway's Usage and Metrics pages to observe memory, CPU, storage, and egress
over representative use, including OCR. Configure alerts and understand that a
hard spending limit can stop workloads. Start Celery at concurrency 1, then
adjust based on measured job throughput and memory. Gunicorn currently runs three
workers; reducing it is a capacity tradeoff that requires testing, not a guaranteed
way to fit a fixed monthly budget. Prefer private database/broker networking.

## 15. Email alternatives

Choose exactly one explicit `EMAIL_BACKEND` on the service that sends email.

### Gmail SMTP on Railway Pro

After upgrading, redeploy Backend so SMTP network access takes effect:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=<sender@gmail.com>
EMAIL_HOST_PASSWORD=<google-app-password>
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=VISTA <sender@gmail.com>
EMAIL_TIMEOUT=15
```

Use a Google App Password where supported by the account, not the regular Gmail
password. Google account/security policy may restrict app-password availability.
Gmail API credentials are not SMTP passwords. Verify connection/STARTTLS before
assuming every SMTP error is an incorrect password.

### Resend HTTPS

```dotenv
EMAIL_BACKEND=vista.email_backend.ResendEmailBackend
RESEND_API_KEY=<resend-key>
DEFAULT_FROM_EMAIL=VISTA <no-reply@your-verified-domain.com>
EMAIL_TIMEOUT=15
```

Verify a domain you control through Resend's DNS instructions for general
recipient delivery. A Gmail address and Railway's generated domain cannot
substitute for that DNS ownership. `onboarding@resend.dev` is a test sender
restricted to the email associated with the Resend account. See
[RESEND.md](vista/RESEND.md). Provider quotas/prices should be checked directly.

## 16. Official references

- [Railway Dockerfiles](https://docs.railway.com/builds/dockerfiles)
- [Railway variables and references](https://docs.railway.com/variables)
- [Railway PostgreSQL](https://docs.railway.com/databases/postgresql)
- [Railway Redis](https://docs.railway.com/databases/redis)
- [Railway public domains](https://docs.railway.com/networking/domains/working-with-domains)
- [Railway SSH](https://docs.railway.com/cli/ssh)
- [Railway SMTP restrictions](https://docs.railway.com/networking/outbound-networking)
- [Railway pricing](https://docs.railway.com/pricing)
- [Railway cost control](https://docs.railway.com/pricing/cost-control)
- [Gmail API sending](https://developers.google.com/workspace/gmail/api/guides/sending)
- [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [OAuth Playground](https://developers.google.com/oauthplayground/)
- [Google OAuth and refresh-token expiration](https://developers.google.com/identity/protocols/oauth2/)
- [Google OAuth verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)
- [Resend domain verification](https://resend.com/docs/dashboard/domains/introduction)
- [Resend test sender restrictions](https://resend.com/docs/knowledge-base/403-error-resend-dev-domain)
