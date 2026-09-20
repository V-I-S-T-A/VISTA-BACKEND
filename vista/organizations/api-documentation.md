# Organizations API Documentation

Base URL: `/api/`

## Model

`Organization` represents a student organization or institutional unit linked to users and submissions.

## Endpoints

### List organizations

- `GET /api/organizations/`
- Permission: Authenticated
- Query params:
  - `is_active` (boolean, optional)
  - `search` (string, optional)
  - `ordering` (string, optional)

### Create organization

- `POST /api/organizations/`
- Permission: Authenticated, Admin only
- Request body:
  - `name` (string, required)
  - `acronym` (string, required, unique)
  - `description` (string, optional)
  - `image_url` (string, optional)
  - `is_active` (boolean, optional)

### Retrieve / update / delete

- `GET /api/organizations/{org_id}/`
- `PUT /api/organizations/{org_id}/`
- `PATCH /api/organizations/{org_id}/`
- `DELETE /api/organizations/{org_id}/`
- Permissions: `retrieve` — authenticated; `create`/`update`/`partial_update`/`destroy` — admin only
- Note: `destroy` does a soft deactivate by setting `is_active = false`.

## Object schema

- `org_id` (UUID)
- `name` (string)
- `acronym` (string)
- `description` (string or null)
- `image_url` (string or null)
- `is_active` (boolean)
- `created_at` (datetime)

## Example request

```json
{
  "name": "Vista Academy",
  "acronym": "VISTA",
  "description": "A school for teaching students and staff how to use the VISTA platform.",
  "image_url": "https://example.com/logo.png",
  "is_active": true
}
```

## Example response

```json
{
  "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
  "name": "Vista Academy",
  "acronym": "VISTA",
  "description": "A school for teaching students and staff how to use the VISTA platform.",
  "image_url": "https://example.com/logo.png",
  "is_active": true,
  "created_at": "2026-06-19T14:20:00Z"
}
```
