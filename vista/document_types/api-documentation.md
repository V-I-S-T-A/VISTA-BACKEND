# Document Types API Documentation

Base URL: `/api/`

## Document Type Endpoints

### List Document Types

- `GET /api/document-types/`
- Permission: Authenticated
- Filters: `is_active` (boolean), `code` (exact match, case-insensitive)
- Response: list of document type objects (list view returns `doc_type_id`, `name`, `code`, `is_active`)

### Create Document Type

- `POST /api/document-types/`
- Permission: Authenticated, Admin only
- Request body:
  - `name` (string, required)
  - `code` (string, optional) — machine-readable form code (e.g. `FM-USTP-OSA-04B`); normalized to uppercase server-side; leave blank if this document type has no standardized scannable form
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
- `code` (string, nullable) — machine-readable form code, unique when set
- `description` (string)
- `required_fields` (JSON object) — a JSON schema-like map of fields required for this document type
- `is_active` (boolean)

### Sample request (create)

```json
{
  "name": "Student Activity Request Form (SARF)",
  "code": "FM-USTP-OSA-010",
  "description": "Standardized OSA activity request form",
  "required_fields": {
    "organization_name": { "type": "string", "required": true }
  },
  "is_active": true
}
```

### Sample response (created)

```json
{
  "doc_type_id": "c3d4e5f6-3333-4a2b-8c7d-9e0f1a2b3c4d",
  "name": "Student Activity Request Form (SARF)",
  "code": "FM-USTP-OSA-010",
  "description": "Standardized OSA activity request form",
  "required_fields": {
    "organization_name": { "type": "string", "required": true }
  },
  "is_active": true
}
```

### Sample response — document type with no scannable form (`code: null`)

```json
{
  "doc_type_id": "8b1a2c3d-4444-4a2b-8c7d-9e0f1a2b3c4e",
  "name": "Transcript",
  "code": null,
  "description": "Official academic transcript",
  "required_fields": {
    "student_id": { "type": "string", "required": true },
    "term": { "type": "string" }
  },
  "is_active": true
}
```