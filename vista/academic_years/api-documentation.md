# Academic Years API Documentation

Base URL: `/api/`

## Academic Year Endpoints

### List Academic Years

- `GET /api/academic-years/`
- Permission: Authenticated
- Response: list of academic year objects

### Create Academic Year

- `POST /api/academic-years/`
- Permission: Authenticated, Admin only
- Request body:
  - `year` (string, required)
- Response: created academic year object

### Retrieve / Update / Delete

- `GET /api/academic-years/{academic_year_id}/`
- `PUT /api/academic-years/{academic_year_id}/`
- `PATCH /api/academic-years/{academic_year_id}/`
- `DELETE /api/academic-years/{academic_year_id}/`
- Permissions: `retrieve` — Authenticated; `update`/`partial_update`/`destroy` — Authenticated, Admin only

### Academic Year Object Schema

- `academic_year_id` (UUID)
- `year` (string)
- `created_at` (datetime)

### Sample request (create)

```json
{
  "year": "2026/2027"
}
```

### Sample response (created)

```json
{
  "academic_year_id": "d3b5a8e1-1111-4a2c-9c7d-0a1b2c3d4e5f",
  "year": "2026/2027",
  "created_at": "2026-06-25T08:00:00Z"
}
```
