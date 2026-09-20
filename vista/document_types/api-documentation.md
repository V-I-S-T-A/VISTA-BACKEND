# Document Types API Documentation

Base URL: `/api/`

## Model

`DocumentType` defines the form or record type used by a submission, including optional OCR matching codes and metadata requirements.

## Endpoints

### List document types

- `GET /api/document-types/`
- Permission: Authenticated
- Filters:
  - `is_active` (boolean)
  - `code` (exact match, case-insensitive)

### Create document type

- `POST /api/document-types/`
- Permission: Authenticated, Admin only
- Request body:
  - `name` (string, required)
  - `code` (string, optional) — normalized to uppercase on save; used by OCR autofill matching
  - `description` (string, required)
  - `required_fields` (JSON object, optional)
  - `is_active` (boolean, optional)

### Retrieve / update / delete

- `GET /api/document-types/{doc_type_id}/`
- `PUT /api/document-types/{doc_type_id}/`
- `PATCH /api/document-types/{doc_type_id}/`
- `DELETE /api/document-types/{doc_type_id}/`
- Permissions: `retrieve` — authenticated; `update`/`partial_update`/`destroy` — admin only
- Note: the model does not hard-delete; the usual admin action is to set `is_active = false`.

## Object schema

- `doc_type_id` (UUID)
- `name` (string)
- `code` (string or null)
- `description` (string)
- `required_fields` (JSON object)
- `is_active` (boolean)

## Example request

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

## Example response

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