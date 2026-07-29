# Submissions API Documentation

Base URL: `/api/`

## Submission Endpoints

### List Submissions

- `GET /api/submissions/`
- Permission: Authenticated
- Notes: `admin` and `staff` users see all submissions; normal users only see submissions they created.
- Query parameters:
  - `status` (string)
  - `org_id` (UUID)
  - `category_id` (UUID)
  - `doc_type_id` (UUID)
  - `academic_year_id` (UUID)
  - `submitted_by` (UUID)
  - `submitted_after` (datetime, `submitted_at >=`)
  - `submitted_before` (datetime, `submitted_at <=`)
  - `search` (string, searches title and description)
  - `ordering` (string, any of `submitted_at`, `updated_at`, `title`, `status`)
- Response: paginated list of submissions.

### Create Submission

- `POST /api/submissions/`
- Permission: Authenticated
- Request body:
  - `doc_type_id` (UUID, required)
  - `org_id` (UUID, optional)
  - `category_id` (UUID, optional)
  - `academic_year_id` (UUID, optional)
  - `title` (string, required)
  - `description` (string, optional)
  - `submitted_by` (UUID, optional; only allowed for `staff` or `admin` users)
- Notes:
  - `submitted_by` is automatically set to the requesting user for normal users.
  - `status` is set to `pending` on creation.

### Retrieve a Submission

- `GET /api/submissions/{submission_id}/`
- Permission: Authenticated, owner or admin/staff.

### Update a Submission

- `PUT /api/submissions/{submission_id}/`
- `PATCH /api/submissions/{submission_id}/`
- Permission: Authenticated, owner or admin/staff.

### Delete a Submission

- `DELETE /api/submissions/{submission_id}/`
- Permission: Authenticated, admin or staff only.
- Note: delete is a soft delete (`is_active` is set to `False`).

### Change Submission Status

- `PATCH /api/submissions/{submission_id}/status/`
- Permission: Authenticated, admin or staff only.
- Request body:
  - `status` (string, required)
  - `remarks_text` (string, optional, write-only)
- Allowed status values:
  - `pending`
  - `under_review`
  - `approved`
  - `rejected`
  - `resubmission_required`
- Valid transitions:
  - `pending` → `under_review`, `rejected`
  - `under_review` → `approved`, `rejected`, `resubmission_required`
  - `resubmission_required` → `under_review`, `pending`
  - `approved` / `rejected` → no further transitions

### Export Submission List

- `GET /api/submissions/export/list/`
- Permission: Authenticated, admin or staff only.
- Query parameters are the same as list filters plus:
  - `date_from` (date)
  - `date_to` (date)
- Response: PDF file download of the filtered submission list.

### Export Submission Detail

- `GET /api/submissions/{submission_id}/export/detail/`
- Permission: Authenticated, admin or staff only.
- Response: PDF file download for a single submission.

### OCR Autofill Draft

- `POST /api/submissions/autofill/`
- Permission: Authenticated
- Content type: `multipart/form-data`
- Form field:
  - `file` (PDF or image file, required)
- Response: draft suggestion payload with OCR-extracted values and optional suggested IDs.
- Notes: this endpoint does not create a submission record; it only returns suggested values for the client to prefill the submission form.

## Submission Object Schema

- `submission_id` (UUID)
- `doc_type_id` (UUID)
- `doc_type_name` (string)
- `submitted_by` (UUID)
- `submitted_by_name` (string)
- `org_id` (UUID)
- `org_name` (string)
- `category_id` (UUID)
- `category_name` (string)
- `academic_year_id` (UUID)
- `academic_year` (string)
- `title` (string)
- `description` (string)
- `status` (string)
- `submitted_at` (datetime)
- `updated_at` (datetime)

## Sample request (create)

```json
{
  "doc_type_id": "c3d4e5f6-3333-4a2b-8c7d-9e0f1a2b3c4d",
  "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
  "category_id": "b1c2d3e4-2222-4f5a-9b8c-1d2e3f4a5b6c",
  "academic_year_id": "d3b5a8e1-1111-4a2c-9c7d-0a1b2c3d4e5f",
  "title": "My Transcript Submission",
  "description": "Uploading my official transcript for review"
}
```

## Sample response (created)

```json
{
  "submission_id": "8f9a0b1c-3456-4d7e-9f8a-3b4c5d6e7f8a",
  "doc_type_id": "c3d4e5f6-3333-4a2b-8c7d-9e0f1a2b3c4d",
  "doc_type_name": "Transcript",
  "submitted_by": "4c0e5f4b-1234-4d6f-9f8a-1a2b3c4d5e6f",
  "submitted_by_name": "Student Name",
  "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
  "org_name": "Example University",
  "category_id": "b1c2d3e4-2222-4f5a-9b8c-1d2e3f4a5b6c",
  "category_name": "Research Papers",
  "academic_year_id": "d3b5a8e1-1111-4a2c-9c7d-0a1b2c3d4e5f",
  "academic_year": "2026/2027",
  "title": "My Transcript Submission",
  "description": "Uploading my official transcript for review",
  "status": "pending",
  "submitted_at": "2026-06-25T09:00:00Z",
  "updated_at": "2026-06-25T09:00:00Z"
}
```

## Sample request (change status)

```json
{
  "status": "under_review",
  "remarks_text": "Starting review"
}
```

## Sample response (after status change)

```json
{
  "submission_id": "8f9a0b1c-3456-4d7e-9f8a-3b4c5d6e7f8a",
  "status": "under_review",
  "updated_at": "2026-06-25T10:00:00Z"
}
```
