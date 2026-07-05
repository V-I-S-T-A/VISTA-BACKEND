# Review Logs API Documentation

Base URL: `/api/`

## Review Log Endpoints

### List Review Logs

- `GET /api/review-logs/`
- Permission: Authenticated
- Notes: `admin` and `staff` see all logs; normal users see logs only for submissions they created

### Retrieve Review Log

- `GET /api/review-logs/{log_id}/`
- Permission: Authenticated

### Review Log Object Schema

- `log_id` (UUID)
- `submission_id` (UUID)
- `submission_title` (string)
- `changed_by` (UUID)
- `changed_by_name` (string)
- `remarks_text` (string)
- `old_status` (string)
- `new_status` (string)
- `changed_at` (datetime)

### Sample response (list item)

```json
{
  "log_id": "a1b2c3d4-5555-4a2b-8c7d-0e1f2a3b4c5d",
  "submission_id": "8f9a0b1c-3456-4d7e-9f8a-3b4c5d6e7f8a",
  "submission_title": "My Transcript Submission",
  "changed_by": "4c0e5f4b-1234-4d6f-9f8a-1a2b3c4d5e6f",
  "changed_by_name": "Reviewer Name",
  "remarks_text": "Looks good",
  "old_status": "under_review",
  "new_status": "approved",
  "changed_at": "2026-06-25T10:15:00Z"
}
```
