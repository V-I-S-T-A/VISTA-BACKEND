# Google Drive Integration API Documentation

Base URL: `/api/`

## Overview

These endpoints allow staff/admin users to connect their Google account, select or create a Drive folder, and archive approved submissions to Google Drive.

## Authentication and connection

### Get Drive connection status

- `GET /api/drive/connection/`
- Permission: Authenticated, staff/admin only
- Response:
  - `{"connected": false}` when nothing is configured
  - `{"connected": true, ...}` with the stored connection details

### Start Google OAuth flow

- `GET /api/drive/auth/start/?mode=existing|created&client_type=web|mobile`
- Permission: Authenticated, staff/admin only
- Response:
  - `{"authorization_url": "https://accounts.google.com/..."}`
- Notes:
  - `mode=existing` requests the full Drive scope
  - `mode=created` requests narrower create-only permissions

### OAuth callback

- `GET /api/drive/auth/callback/`
- Permission: AllowAny
- This is the redirect endpoint used by Google after consent.
- On success it redirects back to:
  - web: `http://localhost:5173/staff/gdrive-sync/callback`
  - mobile: `vista-app://drive-callback`

### Disconnect Google Drive

- `POST /api/drive/disconnect/`
- Permission: Authenticated, staff/admin only
- Response:
  - `{"detail": "Google Drive disconnected."}`

## Folder selection

### List folders

- `GET /api/drive/folders/?search=<term>`
- Permission: Authenticated, staff/admin only
- Response:
  - `{"folders": [...]}`

### Select an existing folder

- `POST /api/drive/folders/select/`
- Permission: Authenticated, staff/admin only
- Request body:
  - `folder_id` (string, required)
  - `folder_name` (string, required)
- Response: updated Drive connection payload

### Create a folder

- `POST /api/drive/folders/create/`
- Permission: Authenticated, staff/admin only
- Request body:
  - `folder_name` (string, required)
- Response: updated Drive connection payload with the newly created folder metadata

### Preview folder path

- `GET /api/drive/folder-path-preview/?submission_id=<uuid>`
- Permission: Authenticated, staff/admin only
- Response:
  - `{"path_segments": [...], "suggested_file_name": "..."}`

## Upload and archive endpoints

### Upload approved submission to Drive

- `POST /api/drive/upload/`
- Permission: Authenticated, staff/admin only
- Content-Type: `multipart/form-data`
- Request body:
  - `submission_id` (UUID, required)
  - `file` (file, required)
  - `file_name` (string, optional)
  - `folder_id` (string, optional)
  - `use_auto_folder` (boolean, optional, default `true`)
- Behavior:
  - validates the connected Drive account and approved submission status
  - queues the upload via Celery
  - returns `202 Accepted` with a `task_id`

### Upload status poll

- `GET /api/drive/upload/status/<task_id>/`
- Permission: Authenticated, staff/admin only
- Response formats:
  - `{"status": "pending"}`
  - `{"status": "success", ...}`
  - `{"status": "error", "detail": "..."}`

## Connection object schema

- `connection_id` (UUID)
- `google_account_email` (string)
- `folder_mode` (string; `existing` or `created`)
- `folder_id` (string)
- `folder_name` (string)
- `is_active` (boolean)
- `last_synced_at` (datetime or null)
- `created_at` (datetime)
- `updated_at` (datetime)

## Example success response

```json
{
  "connected": true,
  "connection_id": "c6d3eb8d-1d44-4a0c-9112-1142cb7d6210",
  "google_account_email": "staff@example.com",
  "folder_mode": "existing",
  "folder_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz",
  "folder_name": "OSA Archive",
  "is_active": true,
  "last_synced_at": "2026-09-19T12:00:00Z",
  "created_at": "2026-09-18T10:00:00Z",
  "updated_at": "2026-09-19T12:00:00Z"
}
```

## Example upload accepted response

```json
{
  "detail": "Upload started.",
  "task_id": "2c8d7d24-7a52-4ac4-a7c4-4714d9c57d2d",
  "status": "queued"
}
```
