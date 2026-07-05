# VISTA Backend — Project Context

## Project Overview

**VISTA** is a Django REST Framework backend for an **Office of Student Affairs (OSA)** document submission and review system. Student organizations submit documents (reports, proposals, etc.) to the OSA. Staff review them through a workflow, and approved documents are automatically uploaded to a **centralized OSA Google Drive** folder via a service account (not per-staff OAuth).

**Stack:** Django 6.0.6 · PostgreSQL · DRF 3.17.1 · SimpleJWT · Celery + Redis · Google Drive API v3 · ReportLab 4.5.1

---

## Project Structure

```
vista-backend/
├── myenv/                        # virtualenv
├── vista/
│   ├── vista/
│   │   ├── __init__.py           # imports celery_app
│   │   ├── settings.py
│   │   ├── urls.py               # root URL config
│   │   ├── asgi.py
│   │   ├── wsgi.py
│   │   ├── celery.py             # Celery app definition
│   │   └── pagination.py         # StandardResultsPagination (shared)
│   ├── users/
│   ├── organizations/
│   ├── academic_years/
│   ├── categories/
│   ├── document_types/
│   ├── documents/
│   ├── submissions/
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py              # includes export_list and export_detail actions
│   │   ├── urls.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── filters.py
│   │   ├── permissions.py
│   │   └── pdf_generator.py      # ReportLab PDF generation logic
│   ├── review_logs/
│   ├── audit_logs/               # contains extra utils.py
│   ├── integrations/             # Google Drive integration (pending rebuild)
│   └── manage.py
├── .env
└── requirements.txt
```

Each app contains: `models.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`, `apps.py`, `filters.py` (where applicable), `permissions.py` (where applicable).

`audit_logs/` additionally contains `utils.py` — helper functions imported by other apps to write log entries.

`submissions/` additionally contains `pdf_generator.py` — all ReportLab PDF logic, kept separate from views.

---

## Database

- **PostgreSQL** with **psycopg3** (`psycopg[binary]==3.3.4`)
- All PKs are `UUIDField` with `uuid.uuid4`
- `pgcrypto` extension enabled via a migration using `CreateExtension('pgcrypto')` from `django.contrib.postgres.operations`
- `DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'`

---

## ERD / Models

### `tbl_Organizations` — `organizations.Organization`
```python
org_id          UUIDField (PK)
name            CharField(255, db_index=True)
acronym         CharField(50, unique=True, db_index=True)
description     TextField
is_active       BooleanField(default=True, db_index=True)
created_at      DateTimeField(auto_now_add=True)
```
Indexes: composite `(is_active, name)`, `(-created_at)`
Soft-delete on destroy.

---

### `tbl_Users` — `users.User`
Extends `AbstractBaseUser + PermissionsMixin` (required for JWT).
```python
user_id         UUIDField (PK)
org_id          ForeignKey(Organization, SET_NULL)
full_name       CharField(255, db_index=True)
email           CharField(255, unique=True)       # USERNAME_FIELD
role            CharField choices: student|staff|admin (db_index=True)
is_active       BooleanField(db_index=True)
is_staff        BooleanField
created_at      DateTimeField(auto_now_add=True)
updated_at      DateTimeField(auto_now=True)
```
Custom `UserManager` with `create_user()` and `create_superuser()`.
Indexes: composite `(role, is_active)`, `(-created_at)`
`AUTH_USER_MODEL = "users.User"`
`password_hash` from the original ERD was removed — `AbstractBaseUser` handles hashing internally via `set_password()` / `check_password()`.

---

### `tbl_Acacdemic_Year` — `academic_years.AcademicYear`
(Note: typo "Acacdemic" is preserved from the ERD to match the actual DB table name)
```python
academic_year_id    UUIDField (PK)
year                CharField(50, unique=True, db_index=True)
created_at          DateTimeField(auto_now_add=True)
```
Index: `(-year)`

---

### `tbl_Category` — `categories.Category`
```python
category_id     UUIDField (PK)
name            CharField(255, unique=True, db_index=True)
```

---

### `tbl_Document_types` — `document_types.DocumentType`
```python
doc_type_id     UUIDField (PK)
name            CharField(255, unique=True, db_index=True)
description     TextField
required_fields JSONField(default=dict)
is_active       BooleanField(default=True, db_index=True)
```
Indexes: composite `(is_active, name)`
Soft-delete only — hard delete blocked because Submissions FK into this table.

---

### `tbl_Submissions` — `submissions.Submission`
The central workflow object.
```python
submission_id       UUIDField (PK)
doc_type_id         ForeignKey(DocumentType, SET_NULL)
submitted_by        ForeignKey(User, SET_NULL)
org_id              ForeignKey(Organization, SET_NULL)
category_id         ForeignKey(Category, SET_NULL)
academic_year_id    ForeignKey(AcademicYear, SET_NULL)
title               CharField(255, db_index=True)
description         TextField
status              CharField(50, choices=STATUS_CHOICES, db_index=True)
submitted_at        DateTimeField(auto_now_add=True)   # server-set, not client
updated_at          DateTimeField(auto_now=True)
```
Status choices (enforced state machine):
- `pending` → `under_review` | `rejected`
- `under_review` → `approved` | `rejected` | `resubmission_required`
- `resubmission_required` → `under_review` | `pending`
- `approved` → terminal
- `rejected` → terminal

Indexes: `(submitted_by, status)`, `(org_id, status)`, `(status, -submitted_at)`, `(-submitted_at)`

---

### `tbl_Review_Logs` — `review_logs.ReviewLog`
Append-only audit trail for submission status changes. Never directly created via API — written automatically by `SubmissionStatusUpdateSerializer.update()` whenever status changes. Django admin also blocks add/change/delete.
```python
log_id          UUIDField (PK)
submission_id   ForeignKey(Submission, CASCADE)
changed_by      ForeignKey(User, SET_NULL)
remarks_text    TextField(blank=True)
old_status      CharField(50)
new_status      CharField(50)
changed_at      DateTimeField(auto_now_add=True)
```
Indexes: composite `(submission_id, -changed_at)`, `(-changed_at)`

---

### `tbl_Documents` — `documents.Document`
File metadata for uploaded documents. Supports versioning.
```python
document_id     UUIDField (PK)
submission_id   ForeignKey(Submission, CASCADE)
file_name       CharField(255)
file_url        CharField(500)
mime_type       CharField(100)
file_size_kb    IntegerField
version         IntegerField(default=1)             # auto-incremented on create
is_current      BooleanField(default=True, db_index=True)  # only one per submission
uploaded_at     DateTimeField(auto_now_add=True)
```
Indexes: composite `(submission_id, is_current)`, `(-uploaded_at)`
Auto-versioning: `DocumentCreateSerializer.create()` computes `next_version`, sets `is_current=True`, and demotes all previous documents for that submission to `is_current=False`.

---

### `tbl_Audit_logs` — `audit_logs.AuditLog`
System-wide audit trail for all significant actions across all tables. Append-only — never directly created or modified via API. Django admin also blocks add/change/delete. Other apps write entries by importing from `audit_logs/utils.py`.
```python
audit_id        UUIDField (PK)
user_id         ForeignKey(User, SET_NULL)
action          CharField(50, choices=ACTION_CHOICES, db_index=True)
table_name      CharField(255, db_index=True)
changes         JSONField(default=dict)
performed_at    DateTimeField(auto_now_add=True)
```
Action choices: `create`, `update`, `delete`, `login`, `logout`, `status_change`
Indexes: composite `(user_id, -performed_at)`, composite `(table_name, action)`, `(-performed_at)`
Default API view scoped to past 24 hours — overridable via `performed_after`/`performed_before` params.

---

### `tbl_Google_Drive_Connections` — `integrations.GoogleDriveConnection`
**Architecture note: this model was built for per-staff OAuth but is being revised to use a single service account for the centralized OSA folder.** See "Open Questions" below.
```python
connection_id           UUIDField (PK)
staff                   OneToOneField(User)
google_account_email    EmailField
_access_token           TextField (Fernet-encrypted, use .access_token property)
_refresh_token          TextField (Fernet-encrypted, use .refresh_token property)
token_expiry            DateTimeField
scopes                  JSONField
folder_mode             CharField choices: existing|created
folder_id               CharField(255)
folder_name             CharField(255)
is_active               BooleanField(db_index=True)
last_synced_at          DateTimeField(null=True)
created_at/updated_at   DateTimeField
```
Token encryption uses `cryptography.fernet.Fernet` with key from `settings.DRIVE_TOKEN_ENCRYPTION_KEY`.

---

## Authentication & Authorization

### JWT (SimpleJWT)
- Access token lifetime: 30 minutes
- Refresh token lifetime: 7 days
- `ROTATE_REFRESH_TOKENS = True`, `BLACKLIST_AFTER_ROTATION = True`
- `USER_ID_FIELD = "user_id"`, `USER_ID_CLAIM = "user_id"`
- Role is embedded in the JWT payload on login

### Roles
Three roles: `student`, `staff`, `admin`

### Permission Classes (`users/permissions.py`)
```python
IsAdmin                         # role == "admin"
IsStaff                         # role == "staff"
IsStudent                       # role == "student"
IsAdminOrStaff                  # role in ("admin", "staff")
IsSelfOrAdmin                   # own record or admin
ReadOnlyOrAdmin                 # GET for all, write for admin only
```
Additional per-app permissions:
- `submissions/permissions.py` → `IsOwnerOrAdminOrStaff` (students can edit own submission only while status == "pending")
- `documents/permissions.py` → `IsSubmissionOwnerOrAdminOrStaff`

### Auth Endpoints
```
POST  /api/auth/login/              → returns access + refresh tokens + user data
POST  /api/auth/logout/             → blacklists refresh token
POST  /api/auth/token/refresh/      → rotates access token
GET   /api/auth/me/                 → own profile
PATCH /api/auth/me/                 → update own profile
POST  /api/auth/change-password/
```

**User creation is admin-only** — no public self-registration. First admin must be created via `python manage.py createsuperuser`. Admins provision staff and student accounts via `POST /api/users/`.

---

## API Design Patterns

### ViewSets vs APIView
All resources use `ModelViewSet` except:
- `ReviewLogViewSet`, `AuditLogViewSet` — use `ReadOnlyModelViewSet` (no write actions exist)
- Login, logout, me, change-password — use manual `APIView` (auth-specific, not resource CRUD)

### Pagination (`vista/vista/pagination.py`)
`StandardResultsPagination` — `PageNumberPagination`, page_size=20, max=100.
Response shape:
```json
{
  "count": 100,
  "total_pages": 5,
  "current_page": 1,
  "page_size": 20,
  "next": "...",
  "previous": null,
  "results": [...]
}
```
Set globally via `REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]` pointing to `vista.pagination.StandardResultsPagination`.

### Filtering
Uses `django-filter` (`DjangoFilterBackend`) + DRF's `SearchFilter` + `OrderingFilter` on every ViewSet.
Each app has its own `filters.py` with a `FilterSet` class.
- `DjangoFilterBackend` → exact-match filters (role, status, is_active, FK UUID lookups, date ranges)
- `SearchFilter` → free-text search (`full_name`, `title`, `name`, etc.)
- `OrderingFilter` → client-controlled sort

### Queryset Scoping (row-level security)
Students only see their own data — enforced in `get_queryset()`, not just `has_object_permission()`, to prevent 403 vs 404 information leaks:
- `UserViewSet` → admin sees all, student sees only self
- `SubmissionViewSet` → admin/staff sees all, student sees `submitted_by=user`
- `DocumentViewSet` → admin/staff sees all, student sees `submission_id__submitted_by=user`
- `ReviewLogViewSet` → admin/staff sees all, student sees `submission_id__submitted_by=user`
- `AuditLogViewSet` → admin-only, no scoping needed

### Soft Delete
`perform_destroy()` sets `is_active=False` and saves with `update_fields` on:
`Organization`, `DocumentType`, `User`

Hard delete (or disabled): `AcademicYear`, `Category` — see Open Questions.

### select_related
Used on all list queries involving FKs to avoid N+1:
- `UserViewSet`: `.select_related("org_id")`
- `SubmissionViewSet`: `.select_related("submitted_by", "org_id", "category_id", "doc_type_id", "academic_year_id")`
- `DocumentViewSet`: `.select_related("submission_id")`
- `ReviewLogViewSet`: `.select_related("submission_id", "changed_by")`
- `AuditLogViewSet`: `.select_related("user_id")`

---

## Endpoints Reference

```
# Users
GET    /api/users/                             admin only
POST   /api/users/                             admin only (creates staff or student)
GET    /api/users/{user_id}/                   self or admin
PATCH  /api/users/{user_id}/                   self or admin
DELETE /api/users/{user_id}/                   admin only (soft-delete)

# Organizations
GET    /api/organizations/                     authenticated
POST   /api/organizations/                     admin only
GET    /api/organizations/{org_id}/            authenticated
PATCH  /api/organizations/{org_id}/            admin only
DELETE /api/organizations/{org_id}/            admin only (soft-delete)

# Academic Years
GET    /api/academic-years/                    authenticated
POST   /api/academic-years/                    admin only
GET    /api/academic-years/{id}/               authenticated
PATCH  /api/academic-years/{id}/               admin only
DELETE /api/academic-years/{id}/               admin only (hard delete — see open questions)

# Categories
GET    /api/categories/                        authenticated
POST   /api/categories/                        admin only
GET    /api/categories/{category_id}/          authenticated
PATCH  /api/categories/{id}/                   admin only
DELETE /api/categories/{id}/                   admin only

# Document Types
GET    /api/document-types/                    authenticated
POST   /api/document-types/                    admin only
GET    /api/document-types/{id}/               authenticated
PATCH  /api/document-types/{id}/               admin only
DELETE /api/document-types/{id}/               admin only (soft-delete)

# Submissions
GET    /api/submissions/                       authenticated (scoped by role)
POST   /api/submissions/                       authenticated (student creates own)
GET    /api/submissions/{id}/                  owner or admin/staff
PATCH  /api/submissions/{id}/                  owner (while pending) or admin/staff
DELETE /api/submissions/{id}/                  admin/staff only
PATCH  /api/submissions/{id}/status/           admin/staff only (state machine + auto ReviewLog)
GET    /api/submissions/export/list/           admin/staff only — downloads list PDF
GET    /api/submissions/{id}/export/detail/    admin/staff only — downloads single submission PDF

# Documents
GET    /api/documents/                         authenticated (scoped by role)
POST   /api/documents/                         authenticated (auto-versioning)
GET    /api/documents/{document_id}/           owner or admin/staff
PATCH  /api/documents/{id}/                    owner or admin/staff
DELETE /api/documents/{id}/                    admin/staff only

# Review Logs (read-only)
GET    /api/review-logs/                       authenticated (scoped by role)
GET    /api/review-logs/{log_id}/              authenticated (scoped)

# Audit Logs (read-only, admin only)
GET    /api/audit-logs/                        admin only (defaults to past 24h)
GET    /api/audit-logs/{audit_id}/             admin only

# Google Drive (integrations — pending service account rebuild)
GET    /api/drive/connection/                  staff/admin
GET    /api/drive/auth/start/                  staff/admin (?mode=existing|created)
GET    /api/drive/auth/callback/               staff/admin — OAuth callback
GET    /api/drive/folders/                     staff/admin (?search=)
POST   /api/drive/folders/select/              staff/admin
POST   /api/drive/folders/create/              staff/admin
POST   /api/drive/disconnect/                  staff/admin
```

---

## Key Business Logic

### Status Transition (Submission Workflow)
Enforced in `SubmissionStatusUpdateSerializer.validate_status()`:
```
pending               → under_review, rejected
under_review          → approved, rejected, resubmission_required
resubmission_required → under_review, pending
approved              → (terminal)
rejected              → (terminal)
```

### Auto ReviewLog Creation
`SubmissionStatusUpdateSerializer.update()` always creates a `ReviewLog` row when status changes — there is no code path where status changes without a log entry. Django admin blocks add/change/delete on ReviewLog to preserve audit integrity.

### Auto AuditLog Creation (`audit_logs/utils.py`)
Other apps import these helpers to write audit entries with a consistent `changes` JSON shape:
```python
from audit_logs.utils import log_create, log_update, log_delete, log_login, log_logout, log_status_change
```
Helper signatures:
```python
log_create(user, table_name, new_data)
log_update(user, table_name, old_data, new_data)
log_delete(user, table_name, old_data)
log_login(user)
log_logout(user)
log_status_change(user, table_name, record_id, old_status, new_status)
```
Where to call them:
- `log_login` / `log_logout` → `users/views.py` `LoginView` and `LogoutView`
- `log_create` / `log_update` / `log_delete` → any ViewSet's `perform_create()`, `perform_update()`, `perform_destroy()`
- `log_status_change` → `submissions/serializers.py` `SubmissionStatusUpdateSerializer.update()`

### Audit Log 24h Default View
`AuditLogViewSet.get_queryset()` defaults to the past 24 hours when no date filters are supplied. Admins can override with `?performed_after=` and `?performed_before=` to query older history.
```python
if not has_date_filter:
    since = timezone.now() - timedelta(hours=24)
    queryset = queryset.filter(performed_at__gte=since)
```

### Auto Versioning (Documents)
`DocumentCreateSerializer.create()`:
1. Finds the latest version for the submission
2. Sets `next_version = latest.version + 1` (or 1 if first)
3. Demotes all existing `is_current=True` docs to `is_current=False`
4. Creates new document with `is_current=True`

### PDF Export (`submissions/pdf_generator.py`)
Two public functions used by `SubmissionViewSet` export actions:

**`generate_list_pdf(submissions, generated_by, filters_applied)`**
- Landscape A4
- Table columns: truncated submission ID, title, status, submitted by, organization, category, submitted date
- Alternating row colours, branded header/footer with page numbers
- Returns `io.BytesIO` buffer (no temp files written to disk)

**`generate_detail_pdf(submission, generated_by)`**
- Portrait A4
- Sections: submission metadata, description, attached documents table (current only), review history table
- Status colours per status value
- Same branded header/footer
- Returns `io.BytesIO` buffer

Both functions are called from `@action` methods on `SubmissionViewSet` and streamed back via `FileResponse(buffer, as_attachment=True, content_type="application/pdf")`.

Export endpoints respect all active `SubmissionFilter` params plus dedicated `date_from` / `date_to` query params (plain `YYYY-MM-DD` format, mapped to `submitted_at__date__gte/lte`):
```
GET /api/submissions/export/list/?status=approved&date_from=2026-01-01&date_to=2026-06-30
GET /api/submissions/export/list/?org_id={uuid}&status=pending
GET /api/submissions/{id}/export/detail/
```

### Google Drive Sync (Celery)
When `submission.status` becomes `approved`, `SubmissionStatusUpdateSerializer.update()` calls:
```python
sync_submission_to_drive.delay(
    submission_id=str(instance.submission_id),
    staff_user_id=str(request.user.user_id),
)
```
`integrations/tasks.py` (`sync_submission_to_drive`):
- Fetches submission + its current documents
- Gets the staff's `GoogleDriveConnection`
- Refreshes expired access token silently if needed
- Downloads each `document.file_url` via `requests.get()`
- Uploads to `connection.folder_id` via Google Drive API
- Updates `connection.last_synced_at`
- Retries: `max_retries=5`, exponential backoff, capped at 600s

---

## Settings Summary

### INSTALLED_APPS
```python
"django.contrib.postgres",
"rest_framework",
"rest_framework_simplejwt",
"rest_framework_simplejwt.token_blacklist",
"django_filters",
"corsheaders",
"users",
"organizations",
"academic_years",
"categories",
"document_types",
"documents",
"submissions",
"review_logs",
"audit_logs",
"integrations",
```

### REST_FRAMEWORK
```python
{
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "vista.pagination.StandardResultsPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
}
```

### Required .env Variables
```
# Django
SECRET_KEY=
DEBUG=
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432

# Google Drive
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=
DRIVE_TOKEN_ENCRYPTION_KEY=          # generate: Fernet.generate_key().decode()

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### celery.py (vista/vista/celery.py)
```python
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vista.settings")
app = Celery("vista")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```
And in `vista/vista/__init__.py`:
```python
from .celery import app as celery_app
__all__ = ("celery_app",)
```

---

## Requirements.txt (Final)

```
# Core
Django==6.0.6
asgiref==3.11.1
sqlparse==0.5.5
tzdata==2026.2

# REST & Auth
djangorestframework==3.17.1
djangorestframework-simplejwt==5.5.1
django-cors-headers==4.9.0

# Filtering & Pagination
django-filter==25.2

# Database
psycopg[binary]==3.3.4

# Config
python-decouple==3.8

# Google Drive Integration
google-api-python-client==2.198.0
google-auth==2.55.1
google-auth-oauthlib==1.4.0
google-auth-httplib2==0.4.0

# Token Encryption
cryptography==44.0.0

# Background Tasks
celery[redis]==5.6.3

# HTTP
requests==2.32.3

# PDF Generation
reportlab==4.5.1

# Dev / Type Stubs (editor only)
google-api-python-client-stubs==1.37.0
```

---

## Open Questions / Pending Decisions

### 1. Google Drive Architecture (CRITICAL — unresolved)
The current `integrations` app implements **per-staff OAuth** (each staff member connects their personal Google account). However, the requirement was clarified: OSA has a **centralized shared Drive folder** — staff are given access to it, they don't own it.

**The correct architecture is a service account:**
- Create a Google Cloud service account
- OSA shares the centralized archive folder with the service account email (one-time manual step)
- Backend uses `google.oauth2.service_account.Credentials` loaded from a JSON key file — no OAuth flow, no user consent, no token refresh dance
- `GoogleDriveConnection` model can be removed entirely
- Replace with a simpler `DriveFolder` config model storing `(folder_id, org_id or category)` mappings that an admin configures once
- No sensitive scopes, no Google verification review required

**`integrations/` needs to be rebuilt** before this feature is usable in production.

### 2. Submission Hard Delete
`Submission.destroy` is currently a hard delete. Since `ReviewLog` has `on_delete=CASCADE` to `Submission`, deleting a submission wipes its entire review history. Consider soft-delete or disabling delete entirely.

### 3. Academic Year / Category Delete
Both use hard delete. `Submission.academic_year_id` is `SET_NULL` — deleting an academic year silently orphans those submissions' year reference. Consider adding `is_active` + soft-delete to `AcademicYear` for consistency.

### 4. Audit Log Wiring (not yet done)
`audit_logs/utils.py` helpers exist but have not yet been wired into the other apps' ViewSets. The next step is adding `perform_create()`, `perform_update()`, `perform_destroy()` overrides to each ViewSet and calling the appropriate util function.

---

## Running the Project

```bash
# Install dependencies
pip install -r requirements.txt

# Apply migrations
python manage.py makemigrations
python manage.py migrate

# Create first admin
python manage.py createsuperuser

# Run Django
python manage.py runserver

# Run Celery worker (separate terminal, Redis must be running)
celery -A vista worker -l info
```

---

## Notes for Continuing AI

- All models use `UUID` PKs — `lookup_field` on every ViewSet is set to the model's PK field name (e.g. `"user_id"`, `"submission_id"`, `"audit_id"`) not the default `"pk"`
- `pagination.py` lives at `vista/vista/pagination.py` — the `DEFAULT_PAGINATION_CLASS` setting points to `"vista.pagination.StandardResultsPagination"`
- `password_hash` field from the original ERD was removed — `AbstractBaseUser` handles hashing internally
- The ERD has a typo: `tbl_Acacdemic_Year` (double 'a') — preserved intentionally in `db_table`
- `django-filter` for exact-match filtering; DRF's `SearchFilter` for free-text search
- Circular import between `submissions` and `review_logs` is resolved by importing `ReviewLog` inside the `update()` method body in `submissions/serializers.py`
- Same circular import pattern applies if `audit_logs.utils` is imported inside method bodies rather than at module level where it would create circular dependencies
- `google-auth-httplib2` must be explicitly pinned — required runtime dependency of `google-api-python-client`, not always auto-resolved
- Yellow Pylance underlines on Google imports: `pip install google-api-python-client-stubs==1.37.0`
- `AuditLogViewSet` and `ReviewLogViewSet` both use `ReadOnlyModelViewSet` — there are no write endpoints for either; all entries are system-generated
- `audit_logs/utils.py` helpers must be used by other apps instead of calling `AuditLog.objects.create()` directly — this ensures consistent `changes` JSON structure across all tables
- `pdf_generator.py` returns `io.BytesIO` buffers — no temp files are written to disk, buffers are passed directly into `FileResponse`
- ReportLab 5.0.0 was released June 18, 2026 but pinned to `4.5.1` (last stable before major version bump) — upgrade to 5.x only after confirming no breaking Platypus API changes
- Export actions (`export_list`, `export_detail`) are registered in `get_permissions()` under `IsAdminOrStaff` — students cannot export
- PDF export date params use plain `YYYY-MM-DD` format (`date_from`, `date_to`) mapped to `submitted_at__date__gte/lte`, separate from the ISO datetime `submitted_after`/`submitted_before` filter params used by the standard list API