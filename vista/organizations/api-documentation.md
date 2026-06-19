# Organizations API Documentation

Base URL: `/api/`

## Organization Endpoints

The organizations endpoints are exposed via the registered router with `basename="organization"` and lookup field `org_id`.

### List Organizations

- `GET /api/organizations/`
- Permission: Authenticated
- Query params:
  - `is_active` (boolean, optional) - filter active organizations by `true` or `false`
  - `search` (string, optional) - search by `name` or `acronym`
  - `ordering` (string, optional) - order by `name` or `created_at`
- Response: list of organization objects

#### Sample response

```json
[
  {
    "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
    "name": "Vista Academy",
    "acronym": "VISTA",
    "is_active": true
  },
  {
    "org_id": "c8d7e6f5-4321-4a9b-8c7d-6e5f4a3b2c1d",
    "name": "Learning Hub",
    "acronym": "LHUB",
    "is_active": false
  }
]
```

### Create Organization

- `POST /api/organizations/`
- Permission: Authenticated, Admin only
- Request body:
  - `name` (string, required)
  - `acronym` (string, required)
  - `description` (string, required)
  - `is_active` (boolean, optional; defaults to `true`)
- Response: created organization object

#### Sample request

```json
{
  "name": "Vista Academy",
  "acronym": "VISTA",
  "description": "A school for teaching students and staff how to use the VISTA platform.",
  "is_active": true
}
```

#### Sample response

```json
{
  "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
  "name": "Vista Academy",
  "acronym": "VISTA",
  "description": "A school for teaching students and staff how to use the VISTA platform.",
  "is_active": true,
  "created_at": "2026-06-19T14:20:00Z"
}
```

### Retrieve Organization

- `GET /api/organizations/{org_id}/`
- Permission: Authenticated
- Response: single organization object

#### Sample response

```json
{
  "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
  "name": "Vista Academy",
  "acronym": "VISTA",
  "description": "A school for teaching students and staff how to use the VISTA platform.",
  "is_active": true,
  "created_at": "2026-06-19T14:20:00Z"
}
```

### Update Organization

- `PUT /api/organizations/{org_id}/`
- `PATCH /api/organizations/{org_id}/`
- Permission: Authenticated, Admin only
- Request body: any subset of fields allowed by `OrganizationSerializer`
  - `name` (string)
  - `acronym` (string)
  - `description` (string)
  - `is_active` (boolean)
- Response: updated organization object

#### Sample request

```json
{
  "name": "Vista Academy International",
  "description": "An expanded organization for staff and students worldwide.",
  "is_active": true
}
```

#### Sample response

```json
{
  "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
  "name": "Vista Academy International",
  "acronym": "VISTA",
  "description": "An expanded organization for staff and students worldwide.",
  "is_active": true,
  "created_at": "2026-06-19T14:20:00Z"
}
```

### Delete Organization

- `DELETE /api/organizations/{org_id}/`
- Permission: Authenticated, Admin only
- Behavior: marks the organization as inactive (`is_active = false`) instead of hard delete
- Response: standard DRF delete response or no content

#### Sample response

```json
{
  "detail": "Organization deleted successfully."
}
```

## Organization Object Schema

All organization responses use `OrganizationSerializer` except list results use `OrganizationListSerializer`.

- `org_id` (UUID)
- `name` (string)
- `acronym` (string)
- `description` (string)
- `is_active` (boolean)
- `created_at` (datetime)

## Permissions Summary

- `IsAuthenticated`: required for all organization endpoints
- `IsAdmin`: required for create, update, partial update, and destroy operations

## Notes

- Organization lookup uses `org_id` UUID values.
- `acronym` is normalized to uppercase by the serializer.
- Use the `is_active` query parameter to filter active records in list requests.
