# Student organization visibility — local verification, 2026-10-30

## Approved behavior

Students can read submissions belonging to their current organization, including
status, priority, remarks, review history and submission-related audit updates.
Existing access to their own submissions remains available, including legacy
entries without an organization. Students without an organization see only their
own entries; unrelated null organizations are never treated as a shared group.

The owner explicitly chose to keep system inbox, email and Android push alerts
limited to the original submitter. Recipient selection and dispatch code were not
changed. Peers gain read access, not editing, status-change, priority or deletion
authority. Existing staff-only attachment and Drive access remains protected.

## GitHub comparison

GitHub `main` was checked directly through the connector:

- Backend: `7cebe547d87ad413103f19564ccc8519ffab4c9f`.
- Web: `57032e82b95e59c72164a50abd236ceacdb45da5`.
- Mobile: `edb852a33a0d6928c4962a119f8236dc380898bb`.

The latest backend still filters submission and review-log reads by the individual
submitter. Organization sharing is the owner's new requirement, not a feature
already implemented by that commit. Local backend HEAD is `deadd641`, web HEAD is
`9d22d53`, and mobile HEAD matches the checked remote. Remote differences were
inspected; no pull, merge, reset or replacement of local work was performed.

## Scoped files

- `vista/submissions/visibility.py`: common owner-or-organization read predicate.
- `vista/submissions/views.py`: apply it to submission querysets.
- `vista/submissions/permissions.py`: allow same-organization detail reads only.
- `vista/review_logs/views.py`: apply the same read boundary to status history.
- `vista/audit_logs/views.py`: share matching submission updates, preserving private
  account actions and the existing staff/admin rules.
- `vista/submissions/test_organization_visibility.py`: eight API regression tests.
- Sibling mobile `scripts/run-push-tests.ps1`: include the new regression module.

Both existing frontends already consume the authenticated submission/review APIs
without an owner filter. Their UI and API contracts did not need modification.

## Verification

- 49 targeted backend tests passed using in-memory SQLite, cache, channel layer,
  broker and captured/mocked external delivery. This includes eight new tests for
  shared lists/counts/priority, details, freshly retrieved saved status/remarks,
  cross-organization isolation, write restrictions, null organizations, membership
  changes, audit privacy and submitter-only alerts on creation/status/priority.
- 54 web tests and 14 mobile tests passed. Web production build passed, with the
  existing large-chunk advisory.
- A broader audit test expects staff to see two logs although its unchanged Git
  view returns one. The same assertion failure was reproduced with the baseline
  method loaded in memory. That unrelated staff rule/test was left unchanged.
- No test mutated Railway data or sent real email/push. No migrations are required.

## Separate local web outage

The screenshot's login failure was HTTP 502. Local Django and the Railway database
tunnel were absent after a reboot; the first reopened tunnel was also stale.
The PostgreSQL/Redis tunnels, Django and Vite were restarted. A direct read-only
`SELECT 1` passed. Fresh unauthenticated `/api/auth/me/` requests return 401 both
directly and through Vite, and a login probe using a nonexistent identity returns
400 rather than 502. Real sign-in and authenticated browser navigation still need
an interactive check.

The earlier React invalid-hook crash also has a local web `vite.config.js` change
to deduplicate React and pre-bundle common dependencies. Vite was restarted with
`--force`. Existing attachment-preview tests retain their separate Vite cache.

The local notification worker was not started; approval to process real queued
deliveries remains pending. Physical Android testing was deferred by the owner.
No commits, pushes, PRs, deployments, production migrations, Railway setting
changes or live submission edits were made.
