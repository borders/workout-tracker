# Voice workout integration — PR #5 design and safety contract

## Goal
During a ChatGPT voice conversation, support: (1) reading recent workouts and sets, (2) adding one set to a specified or current workout with minimal spoken input, and (3) reporting the saved result. This is a design first: **no external voice/API access is enabled by this document**.

## Existing system
The app saves to IndexedDB first and synchronizes revisioned whole-workout JSON records via `/workouts/api/sync.php?action=handshake|pull|push`. The deployed PHP gate requires a website session; writes require session CSRF and same-origin Origin. The current API should not be exposed to a cross-origin plugin, nor should its CSRF/origin checks be relaxed. See `SYNC.md`.

## Proposed separate assistant API
- A separate `/workouts/api/assistant.php` endpoint behind the same HTTPS host, **never** a public unauthenticated route.
- Read operations for recent workouts and set details. Responses minimize private data and exclude original journal documents unless requested.
- A narrow **append_set** command: explicit workout ID or a separately resolved current-session ID, exercise, weight, units, reps (including handling unknown reps), technique flags and optional note. The server validates values and creates one set with server-generated stable ID and timestamp.
- Use a scoped, revocable secret or OAuth-style authorization for the ChatGPT integration, stored **outside webroot**, never hardcoded into the PWA, committed to Git, or pasted into chat. Credential storage, app connection method, and whether the ChatGPT voice environment can invoke it must be confirmed before implementation. No credential means no API access.
- Rate limiting, request-size limits, no CORS wildcard, no data deletion capability, logging that does not contain credentials, and a permission boundary limiting access to workout read/append.
- Unique **idempotency key** per requested set; retries return the same receipt and never duplicate a set. Atomically append the set against the latest stored workout, preserving concurrent browser edits. Use InnoDB transactions and the existing revision / operation audit machinery; do not reuse stale full-workout snapshots.
- Report only a verified server commit as “logged”; on timeouts or ambiguous outcomes, query by idempotency key before retrying, and never claim success on an uncertain write.
- Preserve ordinary website session gate and the existing sync endpoint behavior. No schema changes without migration and backup testing.

## Voice workflow
1. User: “What was my last set?” -> authenticated read, return actual recent set and date.
2. User: “I just did five at 225, flat.” -> resolve current workout context, confirm ambiguous exercise/session if necessary; append exactly one set, return weight/reps and recorded workout.
3. If integration is unconnected or unavailable, explicitly say the set was **not** saved and offer a manual record.
4. Never act on an unverified voice transcript as an authorization to delete/change old sessions.
5. Explicit test for whether the integration is available during a live ChatGPT voice conversation; browser-only access is not sufficient for the goal.

## Implementation milestones / required tests
- Determine plugin/MCP interface available for this user and authentication requirements **before** building the server route.
- Add API and authentication with separate permissions and abuse tests.
- Synthetic disposable local MySQL tests: auth rejection, input validation, append, repeated idempotency key, ambiguous retry, concurrent edits, revision/operation persistence, and absence of deletions.
- Verify mobile PWA sync sees the newly appended set, without a conflict, from a different browser; keep private production workout records untouched during tests.
- Review by Codex before merging. No deployment or production database mutations in this PR without explicit user direction.
