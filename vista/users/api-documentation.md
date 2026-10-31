# Users API Documentation

## Verified organization joining dates (local feature revision, 2026-10-31)

User/profile responses add read-only `org_joined_at`. Legacy accounts remain NULL
until their latest actual joining time is verified. NULL never grants shared
organization access. New assignments, transfers and rejoining record server time;
leaving clears it. Saving the same organization or unrelated profile details leaves
it unchanged. Assignments through the API remain administrator-controlled; student
self-service organization changes are rejected. Submissions retain their stored
organization after a submitter transfers.

An administrator with documentary evidence can correct the CURRENT membership via
`POST /api/users/{user_id}/verify-organization-joining/`:

```json
{
  "org_id": "b7a1d5e7-7890-4c2f-8d6b-3e4f5a6b7c8d",
  "expected_joined_at": null,
  "joined_at": "2026-08-15T09:00:00+08:00",
  "evidence": "Verified membership register, signed entry reference"
}
```

Use the current profile's date (or NULL) for `expected_joined_at`; stale membership
periods/organizations return 409. `joined_at` requires an explicit timezone and must
not be in the future. Evidence is mandatory, limited to 2,000 characters. Keep
references to verified records; do not use account/deployment dates or inferred
dates. A successful correction and its actor, evidence, old/new date and organization
are stored atomically in `OrganizationMembershipAudit`. Identical retries do not
add another event. Administrators can inspect the immutable audit entries in Django
admin. There is no ordinary profile/backdating field for clients.

Bulk/raw assignment writes bypass model hooks and are not a supported membership
workflow. Existing supported API and Django-admin assignments use the guarded model
save. Apply the new migrations only in an explicitly authorized environment; no
historical dates are invented by the migration.

Base URL: `/api/`

## Model

`User` is the primary auth/account model. It stores the account, profile, organization linkage, role, and Cloudinary image URL.

## Authentication endpoints

### Login

- `POST /api/auth/login/`
- Permission: AllowAny
- Request body:
  - `email` (string, required)
  - `password` (string, required)
- Response:
  - `user`: serialized user object
  - `tokens`: `{ "refresh": string, "access": string }`

### Logout

- `POST /api/auth/logout/`
- Permission: Authenticated
- Request body:
  - `refresh` (string, required)

### Refresh token

- `POST /api/auth/token/refresh/`
- Permission: AllowAny
- Request body:
  - `refresh` (string, required)

### Current user

- `GET /api/auth/me/`
- `PATCH /api/auth/me/`
- Permission: Authenticated
- `PATCH` allows updating `first_name`, `last_name`, `org_id`, `role`, `is_active`, `image`, and `remove_image`

### Change password

- `POST /api/auth/change-password/`
- Permission: Authenticated
- Request body:
  - `old_password` (string, required)
  - `new_password` (string, required, minimum 8 characters)

### Password reset request

- `POST /api/auth/password-reset/request/`
- Permission: AllowAny
- Request body:
  - `email` (string, required)

### Password reset confirm

- `POST /api/auth/password-reset/confirm/`
- Permission: AllowAny
- Request body:
  - `email` (string, required)
  - `code` (string, required, 6 digits)
  - `new_password` (string, required, minimum 8 characters)

## User CRUD endpoints

### List users

- `GET /api/users/`
- Permission: Authenticated, Admin only
- Response: list of users

### Create user

- `POST /api/users/`
- Permission: Authenticated, Admin only
- Content-Type: `application/json` or `multipart/form-data` if including `image`
- Request body:
  - `org_id` (UUID or null)
  - `first_name` (string, required)
  - `last_name` (string, required)
  - `email` (string, required)
  - `role` (string, required; one of `student`, `staff`, `admin`)
  - `password` (string, required, minimum 8 characters)
  - `password_confirm` (string, required, must match `password`)
  - `image` (file, optional)

### Retrieve / update / delete a user

- `GET /api/users/{user_id}/`
- `PUT /api/users/{user_id}/`
- `PATCH /api/users/{user_id}/`
- `DELETE /api/users/{user_id}/`
- Permissions: `retrieve` and `update` require the user or an admin; `destroy` requires an admin and permanently deletes the user

## Object schema

- `user_id` (UUID)
- `org_id` (UUID or null)
- `first_name` (string)
- `last_name` (string)
- `email` (string)
- `role` (string)
- `image_url` (string or null)
- `is_active` (boolean)
- `last_login` (datetime or null)
- `department` (string, read-only alias of `org_id.name` in serializer responses)
- `created_at` (datetime)
- `updated_at` (datetime)

## Example login response

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
    "last_login": null,
    "department": "Vista Academy",
    "created_at": "2026-06-17T12:00:00Z",
    "updated_at": "2026-06-17T12:00:00Z"
  },
  "tokens": {
    "refresh": "<refresh_token>",
    "access": "<access_token>"
  }
}
```

## Example user creation request

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

## Example user creation response

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

## Example password update

```json
{
  "old_password": "AdminPass123",
  "new_password": "NewAdminPass456"
}
```

```json
{
  "detail": "Password updated successfully."
}
```

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
- Behavior: permanently deletes the user. Related notifications, password-change codes, and Google Drive connection are cascade-deleted; submission/review history is retained with user references cleared.
- Response: no content (HTTP 204)

#### Sample response

```json
No response body (HTTP 204).
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
