# Review Logs API Documentation

Base URL: `/api/`

## Model

`ReviewLog` contains each status change made to a submission, including who changed it and the reviewer comment.

## Endpoints

### List review logs

- `GET /api/review-logs/`
- Permission: Authenticated
- Notes:
  - admins and staff can see all review logs
  - students only see logs tied to the submissions they created
  - default filtering keeps only the last 24 hours unless a specific `submission_id` is requested

### Retrieve a review log

- `GET /api/review-logs/{log_id}/`
- Permission: Authenticated

## Object schema

- `log_id` (UUID)
- `submission_id` (UUID)
- `changed_by` (UUID or null)
- `remarks_text` (string)
- `old_status` (string)
- `new_status` (string)
- `changed_at` (datetime)

## Example response

```json
{
  "log_id": "a1b2c3d4-5555-4a2b-8c7d-0e1f2a3b4c5d",
  "submission_id": "8f9a0b1c-3456-4d7e-9f8a-3b4c5d6e7f8a",
  "changed_by": "4c0e5f4b-1234-4d6f-9f8a-1a2b3c4d5e6f",
  "remarks_text": "Looks good",
  "old_status": "under_review",
  "new_status": "approved",
  "changed_at": "2026-06-25T10:15:00Z"
}
```
