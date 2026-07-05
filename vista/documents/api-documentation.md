# Documents API Documentation

Base URL: `/api/`

## Document Endpoints

### List Documents

- `GET /api/documents/`
- Permission: Authenticated
- Notes: non-admin/staff users see only documents belonging to their submissions; admin/staff see all

### Create Document

- `POST /api/documents/`
- Permission: Authenticated
- Request body:
  - `submission_id` (UUID, required)
  - `file_name` (string, required)
  - `file_url` (string, required)
  - `mime_type` (string, required)
  - `file_size_kb` (integer, required)
- Response: created document object (DocumentCreateSerializer uses custom create logic to set `version` and `is_current`)

### Retrieve / Update / Delete

- `GET /api/documents/{document_id}/`
- `PUT /api/documents/{document_id}/`
- `PATCH /api/documents/{document_id}/`
- `DELETE /api/documents/{document_id}/`
- Permissions: `destroy` — Authenticated, AdminOrStaff; `retrieve`/`update`/`partial_update` — Authenticated, IsSubmissionOwnerOrAdminOrStaff

### Document Object Schema

- `document_id` (UUID)
- `submission_id` (UUID)
- `file_name` (string)
- `file_url` (string)
- `mime_type` (string)
- `file_size_kb` (integer)
- `version` (integer)
- `is_current` (boolean)
- `uploaded_at` (datetime)

### Sample request (create)

```json
{
  "submission_id": "8f9a0b1c-3456-4d7e-9f8a-3b4c5d6e7f8a",
  "file_name": "transcript.pdf",
  "file_url": "https://storage.example.com/transcript.pdf",
  "mime_type": "application/pdf",
  "file_size_kb": 245
}
```

### Sample response (created)

```json
{
  "document_id": "f7e6d5c4-4444-4b3a-8d7e-6f5a4b3c2d1e",
  "submission_id": "8f9a0b1c-3456-4d7e-9f8a-3b4c5d6e7f8a",
  "file_name": "transcript.pdf",
  "file_url": "https://storage.example.com/transcript.pdf",
  "mime_type": "application/pdf",
  "file_size_kb": 245,
  "version": 1,
  "is_current": true,
  "uploaded_at": "2026-06-25T09:30:00Z"
}
```
