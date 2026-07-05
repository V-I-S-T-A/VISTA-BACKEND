# Document Types API Documentation

Base URL: `/api/`

## Document Type Endpoints

### List Document Types

- `GET /api/document-types/`
- Permission: Authenticated
- Response: list of document type objects (list view returns `doc_type_id`, `name`, `is_active`)

### Create Document Type

- `POST /api/document-types/`
- Permission: Authenticated, Admin only
- Request body:
  - `name` (string, required)
  - `description` (string, required)
  - `required_fields` (JSON object, optional)
  - `is_active` (boolean, optional)
- Response: created document type object

### Retrieve / Update / Delete

- `GET /api/document-types/{doc_type_id}/`
- `PUT /api/document-types/{doc_type_id}/`
- `PATCH /api/document-types/{doc_type_id}/`
- `DELETE /api/document-types/{doc_type_id}/` (soft delete — sets `is_active = false`)
- Permissions: `retrieve` — Authenticated; `update`/`partial_update`/`destroy` — Authenticated, Admin only

### Document Type Object Schema

- `doc_type_id` (UUID)
- `name` (string)
- `description` (string)
- `required_fields` (JSON object) — a JSON schema-like map of fields required for this document type
- `is_active` (boolean)

### Sample request (create)

```json
{
  "name": "Transcript",
  "description": "Official academic transcript",
  "required_fields": {
    "student_id": { "type": "string", "required": true },
    "term": { "type": "string" }
  },
  "is_active": true
}
```

### Sample response (created)

```json
{
  "doc_type_id": "c3d4e5f6-3333-4a2b-8c7d-9e0f1a2b3c4d",
  "name": "Transcript",
  "description": "Official academic transcript",
  "required_fields": {
    "student_id": { "type": "string", "required": true },
    "term": { "type": "string" }
  },
  "is_active": true
}
```
