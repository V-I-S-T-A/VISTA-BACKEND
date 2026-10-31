# VISTA real-time review updates

This feature starts from `main` and adds submission-scoped, read-only WebSocket events. Existing REST endpoints remain responsible for writing replies and status changes.

## Railway configuration

- Build context/root directory: `vista/`. The Dockerfile installs `requirements.txt` and starts Daphne through the existing `entrypoint.sh`.
- Keep the database variables and Google Drive, email, and Celery variables unchanged.
- Configure `CORS_ALLOWED_ORIGINS` to include the **exact** production web origin (e.g. `https://your-frontend.example`). WebSocket handshakes reject untrusted origins.
- Configure `NOTIFICATION_REDIS_URL` for a reachable Redis instance (or ensure `CELERY_BROKER_URL` points to one). Redis channels must be shared by all server processes.
- Ensure `ALLOWED_HOSTS` includes the backend hostname and Railway supports WebSocket upgrade.
- Do not merge both repository PRs until the backend is deployed and `POST /api/realtime/submissions/<uuid>/ticket/` is available.

## How it works

1. The authorized browser POSTs to the ticket REST endpoint with its existing JWT.
2. A short-lived (45-second), signed ticket is returned, scoped to one user and submission.
3. The browser opens `wss://<backend>/ws/submissions/<uuid>/?ticket=...`.
4. The WebSocket consumer checks that the user is active and can read the submission using `submissions.visibility.can_read_submission`.
5. After the database transaction commits, Django broadcasts an event for new ReviewLog or ReviewReply objects.
6. Clients refetch the affected content using the original permission-checked REST APIs. Events carry no reply body.

The existing student reply restrictions still apply: organization members can only read eligible submissions, whereas only the submitter and authorized staff can post replies.

## Local verification

```bash
python -m pip install -r requirements.txt
python manage.py check
python manage.py test vista.test_realtime review_logs.test_replies
daphne -b 0.0.0.0 -p 8000 vista.asgi:application
```

For local development, set `CORS_ALLOWED_ORIGINS=http://localhost:5173` and start Redis. Connect with two browser sessions to the same submission and confirm new remarks, replies, and status history appear without refresh. Verify nonmembers get 403 from ticket issuance, and that changing membership revokes REST access.

## Operational notes

- Existing Celery workers must continue running separately.
- During deployment, coordinate backend and frontend releases. Keep the two PRs unmerged until smoke tests pass.
- The frontend uses a 30-second fallback poll for individual reply threads, with immediate refetch on reconnect.
- A running WebSocket session needs explicit revocation checks for sensitive real-time payloads; this implementation sends only event types and submission identifiers, never document content.
