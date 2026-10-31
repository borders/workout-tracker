# Architecture and decisions

The browser is the immediate write target. IndexedDB transactions atomically persist journal imports and workouts. Original import documents are retained independently of structured, editable sessions. React renders data only after asynchronous reads and acknowledges writes only after persistence.

Workout IDs generated for new sessions are UUIDs. Imported session IDs are deterministic hashes of the inferred date and original entry. Identical imports are idempotent; modified source entries may produce new sessions and should be reviewed before reimporting. The current non-cryptographic hash is not a global identity guarantee and must be upgraded before server synchronization or adversarial imports.

Dates use local calendar strings, not UTC timestamps, to prevent an iPhone timezone change from moving the workout to another day. Modification times use UTC ISO timestamps. An unknown date has an empty sortable date and a separate uncertainty label. Decimal and unknown repetitions retain their original representation and review flags. Holds remain distinct from completed repetitions.

A future server will be the shared durable store, not a prerequisite for entering a set. Synchronization requires durable client operations, per-record server revisions, deletion tombstones, and explicit conflict handling. An imported source document must remain immutable. The backend now reuses Apache Basic authentication and adds session CSRF protection. See the sync implementation below.

The frontend is a static Vite build, compatible with PHP shared hosting. The service worker caches same-origin successful GET responses, excluding API routes. Deployment needs an asset/version strategy and tested offline upgrades before release. A network indicator is not a synchronization indicator; the UI reports local storage rather than claiming cloud sync.

## Structured logging and timing

New optional set fields hold technique, difficulty, logged/completed ISO timestamps, and an entered rest duration in seconds. Session context is an optional workout object. The original imported text remains immutable and existing IndexedDB records require no destructive migration. Saving edits spreads existing records, retaining unknown future fields. Imported sets without recorded timestamps stay untimed unless the user enters a completion time.

The rest timer persists an absolute deadline in localStorage. Rendering derives remaining seconds from wall time rather than decrementing a counter, so suspension does not reset the timer. Pause stores remaining seconds; resume constructs a new deadline. Sound is enabled via user gesture using Web Audio, resets after reload, and is only best-effort while foregrounded. Timer durations are preferences, not measurements of actual rest. Completion-to-completion intervals include performance of the next set and are never substituted for an entered rest duration.

## Synchronization implementation

IndexedDB v2 adds `syncState` and `syncMeta` without clearing v1 data. A write and its dirty-state mutation ID commit atomically. Sync captures immutable operations; acknowledgement of an older mutation advances its base revision without clearing a newer local edit. Pulls compare semantic imported contents (ignoring old per-browser set IDs and import/update timestamps), while preserving every substantive set field and ordering. Changed records retain both local data and the received server record until explicit resolution. Tombstones and source markers prevent seeded reloads from resurrecting server deletions.

The PHP/MySQL side stores versioned workout/import aggregates, a global revision allocator, and durable request/response receipts. A row lock serializes writes, avoiding cursor gaps from out-of-order transaction commits. Every operation is idempotent, including conflicts. Reusing an operation ID with different content fails. Request documents and server JSON preserve empty objects, empty arrays, and unknown fields. Data and conflict receipts live outside the static bundle in MySQL.

Sync is opt-in per browser. It runs on edits, online/visibility events, and a 30-second interval while open. Web Locks serialize cooperating tabs; server revision checks remain authoritative. The API is same-origin and service workers exclude API requests. Configuration remains an owner-only JSON file outside the document root, loaded server-side. See SYNC.md for deployment, security boundaries, validation, and pending live activation.

## Home Screen authentication

Apache rewrites all `/workouts/` requests through `gate.php`. It verifies the existing htpasswd bcrypt hash on a CSRF-protected sign-in form, rotates the session ID on successful login, and remembers login for up to 30 days with a Secure/HttpOnly/SameSite cookie. Failed attempts are rate-limited per hashed client IP outside the cookie session. Sessions and counters live outside the document root. The gate only serves an explicit static asset allowlist or dispatches the authenticated sync endpoint; PHP/config/source files cannot be downloaded through it. Service workers reject unauthenticated installation fetches and never cache sign-in HTML.

## Gate/API CSRF session regression

API calls routed through the form-login gate resume the already-authenticated login session for their CSRF token. They do not clear its session ID or switch session cookies mid-request. Legacy direct Basic-auth API access still uses its separate sync session. Regression checks exercise the full gate login, multiple handshakes/pull, successful push with the original token, and rejection with an invalid token. Origin checks are unchanged.
