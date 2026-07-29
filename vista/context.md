# VISTA Backend — Project Context

## Project Overview

**VISTA** is a Django REST Framework backend for an **Office of Student Affairs (OSA)** document submission and review system. Student organizations submit documents (reports, proposals, etc.) to the OSA. Staff review them through a workflow, and approved documents are automatically uploaded to a **centralized OSA Google Drive** folder via a service account (not per-staff OAuth).

**Stack:** Django 6.0.6 · PostgreSQL · DRF 3.17.1 · SimpleJWT · Celery + Redis · Google Drive API v3 · ReportLab 4.5.1 · Cloudinary

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
│   │   ├── pagination.py         # StandardResultsPagination (shared)
│   │   └── ocr_autofill_pipeline.py  # OCR auto-fill for OSA form intake (see below) —
│   │                                 # location assumed, not yet confirmed; must live
│   │                                 # somewhere on the Python path since submissions/views.py
│   │                                 # imports it as a bare `from ocr_autofill_pipeline import ...`
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
first_name      CharField(150, db_index=True)
last_name       CharField(150, db_index=True)
email           CharField(255, unique=True)       # USERNAME_FIELD
role            CharField choices: student|staff|admin (db_index=True)
image_url       URLField(500, blank=True, null=True)
is_active       BooleanField(db_index=True)
is_staff        BooleanField
created_at      DateTimeField(auto_now_add=True)
updated_at      DateTimeField(auto_now=True)
```

Custom `UserManager` with `create_user()` and `create_superuser()`, both taking `first_name`/`last_name` instead of a single `full_name`.
`get_full_name()` returns `"{first_name} {last_name}"`; `get_short_name()` returns `first_name`.
Indexes: composite `(role, is_active)`, `(-created_at)`, composite `(last_name, first_name)`
`AUTH_USER_MODEL = "users.User"`
`REQUIRED_FIELDS = ["first_name", "last_name"]`
`password_hash` from the original ERD was removed — `AbstractBaseUser` handles hashing internally via `set_password()` / `check_password()`.

**`image_url`** stores the Cloudinary `secure_url` returned on upload — see "Avatar Upload (Cloudinary)" below. It is never set directly by API clients; it's derived server-side from an uploaded `image` file.

**Note:** the model was originally a single `full_name` field and was split into `first_name`/`last_name`. If a production database already has rows under the old schema, this requires a data migration to backfill `first_name`/`last_name` from the existing `full_name` values before dropping the old column — a plain `makemigrations`/`migrate` will not do this safely. See Open Questions.

---

### `tbl_Acacdemic_Year` — `academic_years.AcademicYear`

(Note: typo "Acacdemic" is preserved from the ERD to match the actual DB table name)

```python
academic_year_id    UUIDField (PK)
year                CharField(50, unique=True, db_index=True)
created_at          DateTimeField(auto_now_add=True)
```

is_active BooleanField(default=True, db_index=True)

Indexes: composite `(is_active, -year)`

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
code            CharField(50, unique=True, null=True, blank=True)  # NEW — see below
description     TextField
required_fields JSONField(default=dict)
is_active       BooleanField(default=True, db_index=True)
```

Indexes: composite `(is_active, name)`
Soft-delete only — hard delete blocked because Submissions FK into this table.

**`code`** (added for OCR auto-fill integration — see "OCR Auto-Fill Pipeline" below): a machine-readable form code (e.g. `"FM-USTP-OSA-04B"`) used to match an OCR-identified template directly to a `DocumentType` row. Nullable since pre-existing document types (and any type with no standardized scannable form, e.g. "Transcript") won't have one. Normalized to uppercase/stripped in `DocumentType.save()` so admin edits, shell inserts, and API writes all end up consistent regardless of entry point. The serializer additionally does its own case-normalized uniqueness check in `validate_code()`, rather than relying solely on the automatic `UniqueValidator` DRF attaches for `unique=True` fields — that validator runs _before_ normalization, so it would check the raw (possibly differently-cased) input and could miss a collision.

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
PATCH /api/auth/me/                 → update own profile (supports multipart avatar upload — see below)
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

### Parsers

`UserViewSet` and `MeView` use `parser_classes = [MultiPartParser, FormParser, JSONParser]` so both plain JSON updates and multipart avatar-image uploads work through the same endpoints. All other ViewSets remain on DRF's default JSON-only parsing.

### Filtering

Uses `django-filter` (`DjangoFilterBackend`) + DRF's `SearchFilter` + `OrderingFilter` on every ViewSet.
Each app has its own `filters.py` with a `FilterSet` class.

- `DjangoFilterBackend` → exact-match filters (role, status, is_active, FK UUID lookups, date ranges)
- `SearchFilter` → free-text search (`first_name`, `last_name`, `title`, `name`, etc.)
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

Hard delete (or disabled): `Category`. `AcademicYear` now uses soft-delete via `is_active` (see model above).

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
POST   /api/users/                             admin only (creates staff or student; multipart if uploading image)
GET    /api/users/{user_id}/                   self or admin
PATCH  /api/users/{user_id}/                   self or admin (multipart if uploading image)
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
POST   /api/submissions/autofill/              authenticated (any role) — OCR draft only, see below.
                                                Multipart file upload (PDF or image). NEVER creates a
                                                Submission — returns suggested field values for the
                                                frontend to pre-fill the normal create form with.

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

### Avatar Upload (Cloudinary)

`users.models.User.image_url` (`URLField`) stores a Cloudinary `secure_url`. Both `UserCreateSerializer` and `UserUpdateSerializer` (and `MeView.patch`, which reuses `UserUpdateSerializer`) accept a write-only `image` file field:

```python
image = serializers.ImageField(write_only=True, required=False, allow_null=True)
```

On `create()`/`update()`, if `image` is present:

```python
upload_result = cloudinary.uploader.upload(image, folder="vista/users")
user.image_url = upload_result["secure_url"]
user.save(update_fields=["image_url"])
```

No transformation/crop/resize parameters are passed to `cloudinary.uploader.upload()`, so the image is stored at its original uploaded resolution and file size — nothing is downscaled or cropped server-side.
`image_url` is read-only in both serializers; clients cannot set it directly, only via the `image` upload field.
Requests that include `image` must use `multipart/form-data`; JSON-only requests (no image) continue to work unchanged — see "Parsers" above.

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

## OCR Auto-Fill Pipeline (Submissions Intake)

Rule-based (no ML) auto-fill for standardized OSA forms, calibrated against
three real forms so far. Lets a student upload a scanned/photographed form
and pre-fill their submission instead of typing everything by hand.

### Purpose & Guardrail

Automatically suggests `doc_type_id`, `org_id`, `category_id`, and a couple
of raw field values from an uploaded PDF/image. **Never auto-submits.**
`POST /api/submissions/autofill/` is read-only — it has no write path to
the database at all. A person still has to review the pre-filled values
and hit submit on the _existing_ `POST /api/submissions/` endpoint
(`SubmissionCreateSerializer`, unchanged) for anything to actually be
created. This is the whole guardrail: there is no second, OCR-specific
create/confirm endpoint — the normal create flow already is the human
confirmation step.

### Module: `ocr_autofill_pipeline.py`

Standalone module, no Django imports inside it (keeps it testable outside
the framework). Pipeline stages:

```
Preprocess -> Template Identification -> Zonal Extraction (OCR)
           -> Checkbox/Mark Detection (ink density) -> Fuzzy/Pattern Cleanup
           -> draft dict (status: draft_pending_review | unrecognized_template)
```

- **`preprocess()`** — perspective-corrects an unguided photo (Canny edge
  detection + contour search for the page's outer quad, then warps it flat
  to the template's calibrated page size) with a plain-resize fallback for
  inputs already tightly cropped by a client-side scanner. Handles both PDF
  page renders and plain photo/scan uploads identically — the pipeline only
  needs a PIL `Image`, so `Image.open()` on a JPG/PNG works exactly like a
  `pdf2image`-converted PDF page.
- **`identify_template()`** — fuzzy-matches (`rapidfuzz`) whole-page OCR
  text against each template's anchor phrases. The one place whole-document
  text matching is used deliberately (classification, not extraction).
- **Zonal OCR extraction** — crops a calibrated pixel bounding box per field
  and OCRs only that region; location does the disambiguation a flat
  keyword search across the whole page can't.
- **Checkbox/mark detection (`detect_checkbox_group`)** — a _different_
  technique from OCR, for fields where staff mark a blank with a check or
  slash rather than writing text (currently: SARF's Venue
  In-Campus/Off-Campus line). Measures ink density in each option's zone
  and compares it to that option's own calibrated **blank-form baseline**
  (not a single global threshold — printed rule lines/table borders already
  contribute some density even unmarked, and that baseline differs option
  to option). If more than one option crosses the mark threshold (common
  when a mark's ink bleeds across the boundary between adjacent zones,
  e.g. an oversized checkmark glyph spanning both lines), it picks a
  dominant option when one has ≥1.5× the ink of the runner-up, but still
  flags `needs_review: true` either way — a suggestion, never a silent
  guess.
- **`normalize_document_code()`** — regex extraction of the
  `FM-USTP-OSA-<code>` pattern out of noisy zone text (label text, stray
  icon glyphs), with lookalike-character correction (`O↔0`, `I/l↔1`,
  `S↔5`) applied only within the trailing numeric/letter suffix.

### Template Registry (calibrated so far)

| `template_id`     | Form                                                  | Orientation | Page size @ 300 DPI | Fields                                                                                  |
| ----------------- | ----------------------------------------------------- | ----------- | ------------------- | --------------------------------------------------------------------------------------- |
| `FM-USTP-OSA-04B` | Accomplishment Report                                 | Landscape   | 4200×2550           | `document_code`, `organization_name`                                                    |
| `FM-USTP-OSA-010` | Student Activity Request Form (SARF)                  | Landscape   | 4200×2550           | `document_code`, `organization_name`, `venue_category` (checkbox: in_campus/off_campus) |
| `FM-USTP-OSA-11`  | Local Off-Campus Activities Certificate of Compliance | Portrait    | 2481×3509           | `document_code` only — this form has no organization field anywhere on the page         |

**Calibration gotchas found by measuring the real forms (not guessed from spec):**

- The "Document Code No." box is at the **top right** of the page on all
  three forms, not top left.
- The SARF's _printed_ code is `FM-USTP-OSA-010` (leading zero); the
  sample filename says `-10`. `identify_template()`'s anchor phrases
  include both spellings — any exact-string check elsewhere (e.g. against
  a filename) would disagree with the OCR'd value.
- Only 2 of 3 forms print an organization field at all — `FM-USTP-OSA-11`
  has no zone registered for it (missing zone = "not applicable";
  an empty zone would misleadingly read as "extraction failed").

### Django Integration

- **`submissions/views.py`** — new `autofill` action on `SubmissionViewSet`
  (`MultiPartParser`, falls through to default `IsAuthenticated()` in
  `get_permissions()` — intentionally available to any student, not just
  admin/staff, since it's meant to pre-fill their own create form).
  Helper functions (module-level, not view methods):
  - `_load_as_image()` — PDF via `pdf2image.convert_from_bytes`, else
    `PIL.Image.open()` directly.
  - `_suggest_doc_type()` — direct `DocumentType.objects.filter(code=...)`
    lookup (this is what `DocumentType.code` was added for).
  - `_suggest_organization()` — fuzzy-matches OCR'd org text against real
    `Organization.name` rows (`rapidfuzz`, threshold 70).
  - `_suggest_category()` — maps the `venue_category` checkbox result
    (`"in_campus"`/`"off_campus"`) to a real `Category` row via a small
    static dict (`CHECKBOX_VALUE_TO_CATEGORY_NAME`) + `name__iexact`
    lookup. **Assumes `Category` has an `is_active` field**, matching the
    `Organization`/`DocumentType` convention — not yet confirmed against
    the actual `categories/models.py`; will raise `FieldError` if wrong.
- **`document_types` app** — `code` field added (model/admin/serializer/
  filter/views all updated, migration hand-written pending a real
  `dependencies` entry — see Open Questions).

### Client-Side Capture (React Native, mobile app)

For phone-camera uploads, recommended: **`react-native-document-scanner-plugin`**
(actively maintained, wraps Apple VisionKit + Google ML Kit Document
Scanner, no OpenCV bundling, Expo-compatible) or the newer
**`@dariyd/react-native-document-scanner`** (same native pairing, explicit
New Architecture support). Two initially-considered packages
(`react-native-document-scanner-with-auto-crop`,
`react-native-auto-document-scanner`) are both effectively abandoned and
require old-style manual OpenCV linking — avoid. Note: ML Kit's document
scanner is Android-only from Google's side, which is why both recommended
packages pair it with VisionKit for iOS rather than claiming pure
cross-platform ML Kit support. The server-side `preprocess()` perspective
correction is a complementary fallback for anything that arrives
uncropped (gallery photos, web uploads bypassing the scanner UI).

### Testing Done So Far

- All 3 real sample PDFs run end-to-end at 100% template-match confidence.
- Format independence confirmed: identical output from a PDF-derived image
  vs. a plain JPG with no `pdf2image` involved.
- Perspective correction validated against a synthetic skewed/rotated
  "handheld photo" test case (background visible, no manual pre-crop) —
  recovered a clean, correctly-zoned page.
- Checkbox detection validated against a real user-submitted marked SARF:
  first attempt showed **zero pixel difference** from the blank template
  in the checkbox region (the mark hadn't actually been flattened into the
  PDF by whatever tool was used — a useful diagnostic, not a pipeline bug).
  Second attempt had a genuine mark; initial result was
  `multiple_options_marked` because the mark's glyph was tall enough to
  bleed across both zones — the dominant-option fix (≥1.5× ink ratio)
  resolved this correctly.
- No formal `pytest` suite wired up yet — see example test file provided
  separately (`test_ocr_intake.py`), not yet added to the actual repo.

### New Dependencies

```
pytesseract==0.3.13
pdf2image==1.17.0
rapidfuzz>=3.0
opencv-python-headless    # NOT opencv-python -- headless avoids GUI libs on a server
numpy
```

System packages (Linux server): `tesseract-ocr`, `poppler-utils`, `libgl1`
(the last one specifically for `opencv-python`'s runtime import on
headless servers). Windows dev-machine equivalents: UB-Mannheim's
Tesseract installer + a Windows Poppler build (both need to be on `PATH`,
or pointed to explicitly via `pytesseract.pytesseract.tesseract_cmd` /
`poppler_path=`); `libgl1` has no Windows equivalent requirement —
`opencv-python-headless` installs and imports fine via plain `pip install`.

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
"cloudinary",
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

### Cloudinary Configuration

`python-decouple`'s `config()` reads `.env` directly — it does **not** populate `os.environ`, so the `cloudinary` package's automatic `CLOUDINARY_URL` env-var detection won't pick anything up on its own. `cloudinary.config()` must be called explicitly at startup in `settings.py`:

```python
import cloudinary

cloudinary.config(
    cloud_name=config('CLOUDINARY_CLOUD_NAME'),
    api_key=config('CLOUDINARY_API_KEY'),
    api_secret=config('CLOUDINARY_API_SECRET'),
    secure=True,
)
```

### Upload Size Limits

Django's defaults (`DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE`, 2.5 MB each) are too small for unresized avatar uploads and must be raised in `settings.py`, or large images fail with a bare `400 Bad Request` (raised as `RequestDataTooBig` before the view/serializer ever runs):

```python
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB
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

# Cloudinary
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=

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

# Image Hosting
cloudinary==1.41.0

# OCR Auto-Fill Pipeline (submissions intake)
pytesseract==0.3.13
pdf2image==1.17.0
rapidfuzz>=3.0
opencv-python-headless
numpy

# Dev / Type Stubs (editor only)
google-api-python-client-stubs==1.37.0
```

Requires system packages not installable via pip: `tesseract-ocr`,
`poppler-utils` on the server, plus `libgl1` specifically for
`opencv-python-headless`'s runtime import on headless Linux (`apt-get
install -y tesseract-ocr poppler-utils libgl1`). See "OCR Auto-Fill
Pipeline" above for Windows dev-machine equivalents.

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

### 3. Academic Year / Category Delete (updated)

`AcademicYear` now includes `is_active` and uses soft-delete semantics; deleting an academic year will set `is_active=False` rather than hard-deleting rows, avoiding silent orphaning of `Submission.academic_year_id`. `Category` still uses hard delete — consider adding `is_active` to `Category` for consistency if desired.

### 4. Audit Log Wiring (not yet done)

`audit_logs/utils.py` helpers exist but have not yet been wired into the other apps' ViewSets. The next step is adding `perform_create()`, `perform_update()`, `perform_destroy()` overrides to each ViewSet and calling the appropriate util function.

### 5. `full_name` → `first_name`/`last_name` Migration Path

The `User` model's `full_name` field was split into `first_name`/`last_name`. If any environment already has rows written under the old single-field schema, a straight `makemigrations`/`migrate` will not populate the new columns correctly — a data migration is needed to backfill `first_name`/`last_name` from the existing `full_name` values (e.g. splitting on the first space) before the old column is dropped.

### 6. HEIC/HEIF Avatar Uploads

Pillow (used internally by DRF's `ImageField` validation) does not decode HEIC/HEIF out of the box — the default format for photos taken on iPhones. Uploads in that format currently fail validation with "Upload a valid image." Either install and register `pillow-heif` (`register_heif_opener()`), or restrict the frontend's file picker to formats Pillow already supports.

### 7. `ocr_autofill_pipeline.py` Location (unresolved)

Currently referenced from `submissions/views.py` as a bare
`from ocr_autofill_pipeline import run_autofill_pipeline` — this only
resolves if the module sits somewhere on the Python path (e.g. next to
`settings.py`, or the project root next to `manage.py`). Needs a firm
decision on where this lives — possibly its own app (e.g. `ocr_intake/`)
if it grows beyond a single module, for consistency with how every other
piece of business logic in this project is organized as an app.

### 8. `Category` Model — `is_active` Field Unconfirmed

`submissions/views.py`'s `_suggest_category()` (OCR auto-fill category
suggestion) filters on `Category.objects.filter(..., is_active=True)`,
assumed by convention with `Organization`/`DocumentType`. The actual
`categories/models.py` shown earlier in this doc (`tbl_Category`) does
**not** list an `is_active` field — only `category_id` and `name`. This
will raise `FieldError` at runtime as-is. Either add `is_active` to
`Category` for consistency with the other reference tables, or remove
that filter clause from `_suggest_category()`.

### 9. `DocumentType.code` Migration Dependency

The hand-written migration adding `DocumentType.code` has a placeholder
`dependencies` entry (`("document_types", "0001_initial")`) — needs to be
swapped for the actual latest migration file in that app before running.
Includes an optional data-backfill step (`KNOWN_FORM_CODES`) populating
`code` for the 3 calibrated OSA forms by matching on `DocumentType.name`
— silently no-ops (not an error) if those exact names don't already exist
as rows.

### 10. Checkbox Detection Tuning Against Real Scans

`mark_delta_threshold` (0.03) and the dominant-option ratio (1.5×) were
tuned against one real user-submitted test and one synthetic test — not
yet validated against a broader sample of real staff/student handwriting,
pen pressure, or photo quality. May need adjustment once running against
actual production uploads. Only the SARF's Venue field has a calibrated
checkbox group so far; the SARF also has un-calibrated checkbox-style
fields (`Type of Activity`, `Mode`) that would need the same treatment if
auto-filled later.

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
- `User.full_name` was replaced with separate `first_name`/`last_name` fields — this touches the model, `UserManager`, `USERNAME_FIELD`/`REQUIRED_FIELDS`, both serializers, `UserAdmin`, and `UserViewSet`'s `search_fields`/`ordering_fields`
- `cloudinary.config()` must run explicitly at Django startup (in `settings.py`) — `python-decouple`'s `config()` reads `.env` but does not populate `os.environ`, so Cloudinary's own automatic `CLOUDINARY_URL` env-var pickup silently does nothing here; omitting the explicit `cloudinary.config()` call surfaces at upload time as `ValueError: Must supply api_key`
- `cloudinary.uploader.upload()` is called with no transformation/crop/resize options anywhere in the codebase — this is intentional, avatars are stored at their original uploaded size
- `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` were raised from Django's 2.5 MB default to accommodate unresized avatar uploads — a plain `400 Bad Request` with no JSON body (vs. a serializer validation error) on an image upload usually means these are still at the default
- OCR auto-fill zones are calibrated in **absolute pixel coordinates at 300 DPI** — any new template needs its own calibration pass (render at 300 DPI, run `pytesseract.image_to_data()` to find real label coordinates) rather than guessing positions from a form's written spec; the spec description and the actual printed layout disagreed twice already (code position, org-field presence) when checked against the real sample PDFs
- Checkbox/mark fields (ink density) are a fundamentally different extraction technique from OCR text zones — don't try to route a checkbox field through `clean_field()`/OCR; use `CheckboxOption`/`CheckboxGroup` and `detect_checkbox_group()` instead, and always calibrate `blank_baseline` from the actual unmarked template rather than assuming zero, since printed rule lines/table borders contribute nonzero ink even unmarked
- The `autofill` endpoint's read-only guarantee depends on there being no second create/confirm endpoint for OCR-derived data — if anyone ever adds a "confirm autofill draft" endpoint that writes directly to `Submission`, that would break the "human always submits the normal form" guardrail this was deliberately built around
- `DocumentType.code` and the OCR pipeline's `template_id` are the same string space (`"FM-USTP-OSA-04B"` etc.) — keep them in sync manually; there's no FK or shared source of truth between the Django model field and the Python `TEMPLATE_REGISTRY` list in `ocr_autofill_pipeline.py`
