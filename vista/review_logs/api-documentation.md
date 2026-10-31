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
  - students see their own submissions and eligible organization submissions on/after their verified latest joining date
  - default filtering keeps only the last 24 hours unless a specific `submission_id` is requested

### Retrieve a review log

- `GET /api/review-logs/{log_id}/`
- Permission: Authenticated

Detail reads (including reply reads) have no 24-hour cutoff. The submission read
boundary applies to every guessed log ID. Reply creation has no current-status
restriction; it requires a nonempty staff/admin remark on the selected entry.

### Read or create replies under one status-history entry

- `GET /api/review-logs/{log_id}/replies/?page=1&page_size=20`
- `POST /api/review-logs/{log_id}/replies/`
- Reads use the submission's owner-or-verified-organization visibility.
- Creates are restricted to the original student submitter and staff/admin under
  existing submission-access rules. Eligible organization viewers cannot post.
- Author is always derived from authentication; client author fields are ignored.
- No edit/delete reply routes are provided.

POST body:

```json
{
  "message": "The event date is confirmed.",
  "parent_reply": null,
  "client_request_id": "fa5e9911-a403-4c90-b279-04e59d411216"
}
```

Messages are trimmed, nonempty, and at most **4,000 Unicode characters**, matching
Web. `parent_reply` is optional; a supplied UUID must identify a reply in this exact
history entry. Keep the request UUID for a retry of the same draft/target. First
creation returns 201; an identical retry returns 200 with the existing reply. A
different payload using the same author/request UUID returns 409. Database uniqueness
and an author-row lock protect concurrent retries.

GET uses the existing pagination envelope (`count`, `current_page`, `total_pages`,
`next`, `previous`, `results`), chronological order by `created_at, reply_id`, default
20 and maximum 100 rows. Replies include author ID/name/role/photo, target ID/name,
message, request UUID, and timestamp. Deleted authors have a fallback identity.

ReviewLog responses add `reply_count` and `can_reply`. Existing fields, timeline
ordering, original remarks and status records stay intact. When an authorized student
submitter posts a threaded reply, an in-app system notification (`review_reply_created`)
is created targeted solely to the responsible OSA staff reviewer. Reply writes do
NOT alter submission status, create review logs, send emails, or run OCR/Drive background jobs.

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

---

## Web Integration Contract: Student Reply Staff Notifications

### 1. Polling Endpoint and Cadence

Staff clients in `VISTA-WEB` poll the authenticated notification endpoint every 15–30 seconds:

- **Endpoint:** `GET /api/notifications/`
- **Headers:** `Authorization: Bearer <access_token>`
- **Query / Frequency:** Poll every 15–30 seconds while the web browser tab is active. Back off to 60s when the document is hidden/backgrounded (`document.hidden`).
- **Unread Count Shortcut:** `GET /api/notifications/unread-count/` can alternatively be used for lightweight bell polling.

### 2. Response Schema

```json
{
  "results": [
    {
      "notification_id": "70000000-0000-4000-8000-000000000001",
      "submission_id": "8f9a0b1c-3456-4d7e-9f8a-3b4c5d6e7f8a",
      "submission_title": "Annual Activity Report 2026",
      "submission_status": "under_review",
      "type": "review_reply_created",
      "message": "Alice Test replied to your remark on \"Annual Activity Report 2026\".",
      "is_read": false,
      "created_at": "2026-10-31T12:00:00Z",
      "actor_name": "Alice Test",
      "actor_image_url": "https://example.test/alice.webp",
      "is_priority": false
    }
  ],
  "unread_count": 1
}
```

### 3. Toast Display and Deduplication Rules

To display a bottom-right toast for new student replies without replaying old notifications or displaying duplicate popups:

1. **Initial Mount / Login:**
   - On the first fetch after login/mount, record all received `notification_id` values into an in-memory `seenNotificationIds` `Set<string>`.
   - Set `sessionStartTime = new Date()`.
   - Update the notification bell count from `data.unread_count`, but **do not display toasts for notifications created prior to `sessionStartTime`**.
2. **Subsequent Polls (every 15–30s):**
   - For each item in `data.results`:
     - If `item.type === 'review_reply_created'`, `!item.is_read`, `!seenNotificationIds.has(item.notification_id)`, and `new Date(item.created_at) >= sessionStartTime`:
       - Add `item.notification_id` to `seenNotificationIds`.
       - Render a bottom-right toast:
         - **Title:** `New Student Reply`
         - **Body:** `item.message` (e.g. `Alice Test replied to your remark on "Annual Activity Report 2026".`)
         - **Avatar:** `item.actor_image_url`
3. **Toast Click Action:**
   - When the user clicks the toast:
     - Navigate directly to `/submissions/${item.submission_id}`.
     - Call `POST /api/notifications/${item.notification_id}/read/` with Bearer token.
     - Decrement local `unread_count` on success.
4. **Mark as Read Endpoint:**
   - **Endpoint:** `POST /api/notifications/{notification_id}/read/`
   - Returns the updated notification object with `"is_read": true`.
