# Academic Years API Documentation

Base URL: `/api/`

## Model

`AcademicYear` stores a school year label and is used on submissions and the OCR autofill suggestions.

## Endpoints

### List academic years

- `GET /api/academic-years/`
- Permission: Authenticated
- Response: paginated list of academic year records

### Create academic year

- `POST /api/academic-years/`
- Permission: Authenticated, Admin only
- Request body:
  - `year` (string, required, unique)
  - `is_active` (boolean, optional)

### Retrieve / update / delete

- `GET /api/academic-years/{academic_year_id}/`
- `PUT /api/academic-years/{academic_year_id}/`
- `PATCH /api/academic-years/{academic_year_id}/`
- `DELETE /api/academic-years/{academic_year_id}/`
- Permissions: `retrieve` — authenticated; `update`/`partial_update`/`destroy` — admin only

## Object schema

- `academic_year_id` (UUID)
- `year` (string)
- `is_active` (boolean)
- `created_at` (datetime)

## Example request

```json
{
  "year": "2026/2027",
  "is_active": true
}
```

## Example response

```json
{
  "academic_year_id": "d3b5a8e1-1111-4a2c-9c7d-0a1b2c3d4e5f",
  "year": "2026/2027",
  "is_active": true,
  "created_at": "2026-06-25T08:00:00Z"
}
```
