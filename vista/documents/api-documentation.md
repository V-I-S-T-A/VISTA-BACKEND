# Documents API Documentation

Base URL: `/api/`

## Model

`Document` stores file metadata for a submission; it tracks versioning and the current active file for that submission.

## Endpoints

### List documents

- `GET /api/documents/`
- Permission: Authenticated
- Notes: students only see documents for their own submissions; admin/staff can view all.

### Create document

- `POST /api/documents/`
- Permission: Authenticated
- Request body:
  - `submission_id` (UUID, required)
  - `file_name` (string, required)
  - `file_url` (string, required)
  - `mime_type` (string, required)
  - `file_size_kb` (integer, required)

### Retrieve / update / delete

- `GET /api/documents/{document_id}/`
- `PUT /api/documents/{document_id}/`
- `PATCH /api/documents/{document_id}/`
- `DELETE /api/documents/{document_id}/`
- Permissions: `destroy` — admin/staff; `retrieve`/`update`/`partial_update` — owner or admin/staff

## Object schema

- `document_id` (UUID)
- `submission_id` (UUID)
- `file_name` (string)
- `file_url` (string)
- `mime_type` (string)
- `file_size_kb` (integer)
- `version` (integer)
- `is_current` (boolean)
- `uploaded_at` (datetime)

## Example request

```json
{
  "submission_id": "8f9a0b1c-3456-4d7e-9f8a-3b4c5d6e7f8a",
  "file_name": "transcript.pdf",
  "file_url": "https://storage.example.com/transcript.pdf",
  "mime_type": "application/pdf",
  "file_size_kb": 245
}
```

## Example response

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
