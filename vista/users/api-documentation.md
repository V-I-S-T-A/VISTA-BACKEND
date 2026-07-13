# Users API Documentation

Base URL: `/api/`

## Authentication Endpoints

### Login

- `POST /api/auth/login/`
- Permission: AllowAny
- Request body:
  - `email` (string, required)
  - `password` (string, required)
- Response:
  - `user`: user object
  - `tokens`: `{ "refresh": string, "access": string }`

#### Sample request

```json
{
  "email": "admin@gmail.com",
  "password": "AdminPass123"
}
```

#### Sample response

```json
{
  "user": {
    "user_id": "4c0e5f4b-1234-4d6f-9f8a-1a2b3c4d5e6f",
    "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
    "first_name": "Admin",
    "last_name": "User",
    "email": "admin@example.com",
    "role": "admin",
    "image_url": "https://res.cloudinary.com/demo/image/upload/v1/vista/users/abc123.jpg",
    "is_active": true,
    "created_at": "2026-06-17T12:00:00Z",
    "updated_at": "2026-06-17T12:00:00Z"
  },
  "tokens": {
    "refresh": "<refresh_token>",
    "access": "<access_token>"
  }
}
```

### Logout

- `POST /api/auth/logout/`
- Permission: Authenticated
- Request body:
  - `refresh` (string, required)
- Response:
  - `detail`: success message

#### Sample request

```json
{
  "refresh": "<refresh_token>"
}
```

#### Sample response

```json
{
  "detail": "Successfully logged out."
}
```

### Refresh Token

- `POST /api/auth/token/refresh/`
- Permission: AllowAny
- Request body:
  - `refresh` (string, required)
- Response:
  - `access`: string

#### Sample request

```json
{
  "refresh": "<refresh_token>"
}
```

#### Sample response

```json
{
  "access": "<new_access_token>"
}
```

### Current User

- `GET /api/auth/me/`
- Permission: Authenticated
- Response: current authenticated user object

#### Sample response

```json
{
  "user_id": "4c0e5f4b-1234-4d6f-9f8a-1a2b3c4d5e6f",
  "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
  "first_name": "Admin",
  "last_name": "User",
  "email": "admin@example.com",
  "role": "admin",
  "image_url": "https://res.cloudinary.com/demo/image/upload/v1/vista/users/abc123.jpg",
  "is_active": true,
  "created_at": "2026-06-17T12:00:00Z",
  "updated_at": "2026-06-17T12:00:00Z"
}
```

### Update Current User

- `PATCH /api/auth/me/`
- Permission: Authenticated
- Content-Type: `application/json` for text-only updates, or `multipart/form-data` if updating `image`
- Request body: any subset of fields allowed by `UserUpdateSerializer`
  - `first_name` (string)
  - `last_name` (string)
  - `org_id` (UUID or null)
  - `image` (file, optional — write-only, uploaded to Cloudinary as-is with no resize/crop; response returns `image_url`)
- Response: updated user object

#### Sample request

```json
{
  "first_name": "Administrator",
  "last_name": "User",
  "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d"
}
```

#### Sample response

```json
{
  "user_id": "4c0e5f4b-1234-4d6f-9f8a-1a2b3c4d5e6f",
  "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
  "first_name": "Administrator",
  "last_name": "User",
  "email": "admin@example.com",
  "role": "admin",
  "image_url": "https://res.cloudinary.com/demo/image/upload/v1/vista/users/abc123.jpg",
  "is_active": true,
  "created_at": "2026-06-17T12:00:00Z",
  "updated_at": "2026-06-17T12:15:00Z"
}
```

### Change Password

- `POST /api/auth/change-password/`
- Permission: Authenticated
- Request body:
  - `old_password` (string, required)
  - `new_password` (string, required, min 8 chars)
- Response:
  - `detail`: success message

#### Sample request

```json
{
  "old_password": "AdminPass123",
  "new_password": "NewAdminPass456"
}
```

#### Sample response

```json
{
  "detail": "Password updated successfully."
}
```

## User CRUD Endpoints

The main user endpoints are exposed via the registered router with `basename="user"` and lookup field `user_id`.

### List Users

- `GET /api/users/`
- Permission: Authenticated, Admin only
- Response: list of user objects

#### Sample response

```json
[
  {
    "user_id": "4c0e5f4b-1234-4d6f-9f8a-1a2b3c4d5e6f",
    "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
    "first_name": "Admin",
    "last_name": "User",
    "email": "admin@example.com",
    "role": "admin",
    "image_url": "https://res.cloudinary.com/demo/image/upload/v1/vista/users/abc123.jpg",
    "is_active": true,
    "created_at": "2026-06-17T12:00:00Z",
    "updated_at": "2026-06-17T12:00:00Z"
  },
  {
    "user_id": "6d7e8f9a-2345-4b6c-8d7e-2f3a4b5c6d7e",
    "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
    "first_name": "Staff",
    "last_name": "Member",
    "email": "staff@example.com",
    "role": "staff",
    "image_url": null,
    "is_active": true,
    "created_at": "2026-06-16T09:00:00Z",
    "updated_at": "2026-06-16T09:00:00Z"
  }
]
```

### Create User

- `POST /api/users/`
- Permission: Authenticated, Admin only
- Content-Type: `application/json`, or `multipart/form-data` if including `image`
- Request body:
  - `org_id` (UUID or null)
  - `first_name` (string, required)
  - `last_name` (string, required)
  - `email` (string, required)
  - `role` (string, required; one of `student`, `staff`, `admin`)
  - `password` (string, required, min 8 chars)
  - `password_confirm` (string, required, must match `password`)
  - `image` (file, optional — write-only, uploaded to Cloudinary as-is with no resize/crop; response returns `image_url`)
- Response: created user object

#### Sample request

```json
{
  "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
  "first_name": "New",
  "last_name": "Student",
  "email": "student@example.com",
  "role": "student",
  "password": "StudentPass123",
  "password_confirm": "StudentPass123"
}
```

#### Sample response

```json
{
  "user_id": "8f9a0b1c-3456-4d7e-9f8a-3b4c5d6e7f8a",
  "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
  "first_name": "New",
  "last_name": "Student",
  "email": "student@example.com",
  "role": "student",
  "image_url": null,
  "is_active": true,
  "created_at": "2026-06-17T12:30:00Z",
  "updated_at": "2026-06-17T12:30:00Z"
}
```

### Retrieve User

- `GET /api/users/{user_id}/`
- Permission: Authenticated, self or admin
- Response: single user object

#### Sample response

```json
{
  "user_id": "8f9a0b1c-3456-4d7e-9f8a-3b4c5d6e7f8a",
  "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
  "first_name": "New",
  "last_name": "Student",
  "email": "student@example.com",
  "role": "student",
  "image_url": null,
  "is_active": true,
  "created_at": "2026-06-17T12:30:00Z",
  "updated_at": "2026-06-17T12:30:00Z"
}
```

### Update User

- `PUT /api/users/{user_id}/`
- `PATCH /api/users/{user_id}/`
- Permission: Authenticated, self or admin
- Content-Type: `application/json`, or `multipart/form-data` if including `image`
- Request body: subset of fields allowed by `UserUpdateSerializer`
  - `first_name` (string)
  - `last_name` (string)
  - `org_id` (UUID or null)
  - `role` (string; admin only)
  - `is_active` (boolean; admin only)
  - `image` (file, optional — write-only, uploaded to Cloudinary as-is with no resize/crop; response returns `image_url`)
- Response: updated user object

#### Sample request

```json
{
  "first_name": "Updated",
  "last_name": "Student Name",
  "role": "staff",
  "is_active": true
}
```

#### Sample response

```json
{
  "user_id": "8f9a0b1c-3456-4d7e-9f8a-3b4c5d6e7f8a",
  "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
  "first_name": "Updated",
  "last_name": "Student Name",
  "email": "student@example.com",
  "role": "staff",
  "image_url": null,
  "is_active": true,
  "created_at": "2026-06-17T12:30:00Z",
  "updated_at": "2026-06-17T12:45:00Z"
}
```

### Delete User

- `DELETE /api/users/{user_id}/`
- Permission: Authenticated, Admin only
- Behavior: marks the user as inactive (`is_active = false`), does not hard delete
- Response: no content or standard DRF delete response

#### Sample response

```json
{
  "detail": "User deleted successfully."
}
```

## User Object Schema

All user responses use `UserSerializer`:

- `user_id` (UUID)
- `org_id` (UUID or null)
- `first_name` (string)
- `last_name` (string)
- `email` (string)
- `role` (string)
- `image_url` (string URL or null) — Cloudinary `secure_url`, populated only when an `image` file was uploaded
- `is_active` (boolean)
- `created_at` (datetime)
- `updated_at` (datetime)

## Permissions Summary

- `AllowAny`: login, token refresh
- `IsAuthenticated`: current user, password change, auth logout, and all user endpoints
- `IsAdmin`: user list, create, delete, and admin-only role/active changes
- `IsSelfOrAdmin`: retrieve and update self or admin access

## Notes

- The project base API path is mounted at `/api/` in `vista/urls.py`.
- User lookup uses `user_id` UUID values.
- `full_name` has been replaced with separate `first_name` / `last_name` fields across the model, serializers, admin, and views.
- `UserCreateSerializer` enforces password confirmation and admin-only role assignment.
- `UserUpdateSerializer` allows role and active status changes only by admin.
- `image_url` is never set directly by the client. Both `UserCreateSerializer` and `UserUpdateSerializer` accept a write-only `image` file field; on save, the file is uploaded to Cloudinary via `cloudinary.uploader.upload()` with no transformation/crop/resize parameters, so the original uploaded resolution and size are preserved. The resulting `secure_url` is stored in `image_url`.
- Requests that include `image` must use `multipart/form-data`; JSON-only requests (no image) continue to work as before.
- Requires the `cloudinary` package and a configured `CLOUDINARY_URL` environment variable (or `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET`), plus `"cloudinary"` added to `INSTALLED_APPS`.