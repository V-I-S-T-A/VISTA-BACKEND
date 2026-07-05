# Categories API Documentation

Base URL: `/api/`

## Category Endpoints

### List Categories

- `GET /api/categories/`
- Permission: Authenticated
- Response: list of category objects

### Create Category

- `POST /api/categories/`
- Permission: Authenticated, Admin only
- Request body:
  - `name` (string, required)
- Response: created category object

### Retrieve / Update / Delete

- `GET /api/categories/{category_id}/`
- `PUT /api/categories/{category_id}/`
- `PATCH /api/categories/{category_id}/`
- `DELETE /api/categories/{category_id}/`
- Permissions: `retrieve` — Authenticated; `update`/`partial_update`/`destroy` — Authenticated, Admin only

### Category Object Schema

- `category_id` (UUID)
- `name` (string)

### Sample request (create)

```json
{
  "name": "Research Papers"
}
```

### Sample response (created)

```json
{
  "category_id": "b1c2d3e4-2222-4f5a-9b8c-1d2e3f4a5b6c",
  "name": "Research Papers"
}
```
