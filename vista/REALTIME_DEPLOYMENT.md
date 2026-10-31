# Shared realtime infrastructure / Railway deployment

This draft implements the shared VISTA `/ws/notifications/` contract specified in the Production Recovery and Shared WebSocket Real-Time Infrastructure Report.

## Railway
- Keep build context rooted at `vista/`. `Dockerfile` installs UTF-8 `requirements.txt` and starts Daphne with `PORT`; `entrypoint.sh` retains database checks, migrations, and static collection.
- Keep PostgreSQL, Gmail API, Google Drive, Celery and Expo push settings intact.
- Configure `ALLOWED_HOSTS` with the backend hostname.
- Configure `CORS_ALLOWED_ORIGINS` with the VISTA-WEB HTTPS origin, e.g. `https://vista-ustp.up.railway.app`. WebSocket origins use this allow-list.
- Set `NOTIFICATION_REDIS_URL`, `REDIS_URL` or `CELERY_BROKER_URL` to shared, reachable Redis. Do not clear Redis or Celery queues.

## WebSocket contract
- URL: `wss://<backend-host>/ws/notifications/`
- Browser or mobile sends `{"token":"<JWT>"}` within 10 seconds of opening, or a signed `{"ticket":"..."}` from `POST /api/notifications/ws-ticket/`.
- An authenticated Django session is also accepted. Successful authentication returns `{"type":"ready","user_id":"...","role":"..."}`.
- Optional `{"type":"ping"}` returns `{"type":"pong"}`.
- JWT connections close on JWT expiry. Clients reconnect with backoff and refetch missed data.
- User connections join `notifications.<user_id>`; staff/admin also join `staff_users`.
- Events: `submission.created`, `submission.updated`, `review_log.created`, `review_reply.created`, `notification.created`, `notification.read`. Every event has version 1, event_id, occurred_at, and relevant IDs. Legacy `notification.changed` remains for mobile.
- All event content is metadata only. REST remains authoritative for reply text, documents, personal data, and permissions.

## Verification before merging
```bash
python -m pip install -r requirements.txt
python manage.py check
python manage.py test notifications.test_realtime review_logs.test_replies
daphne -b 0.0.0.0 -p 8000 vista.asgi:application
```
Run the full Django regression suite on isolated test DB, plus `npm run build` and frontend tests for VISTA-WEB. Test two independent browser sessions, mobile notification runtime, membership changes, unknown JWTs, reconnects, status changes, and reply events. Verify Railway staging before releasing both PRs.

**Not yet verified:** the 12 integration test / 131 regression test results described in the reference report are not claims about this PR. These new changes need independent CI and runtime validation.
