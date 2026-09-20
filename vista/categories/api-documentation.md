# Categories API Documentation

Base URL: `/api/`

## Model

`Category` is a simple classification used by submissions and the OCR autofill helper logic.

## Endpoints

### List categories

- `GET /api/categories/`
- Permission: Authenticated

### Create category

- `POST /api/categories/`
- Permission: Authenticated, Admin only
- Request body:
  - `name` (string, required, unique)

### Retrieve / update / delete

- `GET /api/categories/{category_id}/`
- `PUT /api/categories/{category_id}/`
- `PATCH /api/categories/{category_id}/`
- `DELETE /api/categories/{category_id}/`
- Permissions: `retrieve` — authenticated; `update`/`partial_update`/`destroy` — admin only

## Object schema

- `category_id` (UUID)
- `name` (string)

## Example request

```json
{
  "name": "Research Papers"
}
```

## Example response

```json
{
  "category_id": "b1c2d3e4-2222-4f5a-9b8c-1d2e3f4a5b6c",
  "name": "Research Papers"
}
```
