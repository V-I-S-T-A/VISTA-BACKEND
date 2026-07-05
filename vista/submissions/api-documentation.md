# Submissions API Documentation

Base URL: `/api/`

## Submission Endpoints

### List Submissions

- `GET /api/submissions/`
- Permission: Authenticated
- Notes: `admin` and `staff` see all submissions; normal users see only their own

### Create Submission

- `POST /api/submissions/`
- Permission: Authenticated
- Request body:
  - `doc_type_id` (UUID, required)
  - `org_id` (UUID, required or null)
  - `category_id` (UUID, required or null)
  - `academic_year_id` (UUID, required or null)
  - `title` (string, required)
  - `description` (string)
- Response: created submission object (created `submitted_by` uses request user and status defaults to `pending`)

### Retrieve / Update / Delete

- `GET /api/submissions/{submission_id}/`
- `PUT /api/submissions/{submission_id}/`
- `PATCH /api/submissions/{submission_id}/`
- `DELETE /api/submissions/{submission_id}/`
- Permissions: `retrieve`/`update`/`partial_update` — Authenticated, `IsOwnerOrAdminOrStaff`; `destroy` — Authenticated, `IsAdminOrStaff`

### Change Status (Custom Action)

- `PATCH /api/submissions/{submission_id}/status/`
- Permission: Authenticated, Admin or Staff only
- Request body:
  - `status` (string, required) — allowed transitions validated by server
  - `remarks_text` (string, optional, write-only)
- Response: updated submission object

### Submission Object Schema

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

### Sample request (create)

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

### Sample response (created)

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

### Sample request (change status)

```json
{
  "status": "under_review",
  "remarks_text": "Starting review"
}
```

### Sample response (after status change)

```json
{
  "submission_id": "8f9a0b1c-3456-4d7e-9f8a-3b4c5d6e7f8a",
  "status": "under_review",
  "updated_at": "2026-06-25T10:00:00Z"
}
```
