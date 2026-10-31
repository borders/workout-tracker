# Assistant API

No ChatGPT connector exists yet. These endpoints provide server access; they do not enable ChatGPT voice logging on their own. Deployment and production credential provisioning are separate operator actions.

## Routes and contract

- `GET /workouts/api/assistant.php?action=recent&limit=5`: 1–20 recent workouts, newest ISO calendar date then ID descending, with at most 15 sets each. Missing/unknown dates sort using their stored first ten characters; known app dates use `YYYY-MM-DD`.
- `POST /workouts/api/assistant.php?action=append_set`: append one repetitions set to an **existing explicit workout ID**. Example body: `{"workoutId":"existing-id","idempotencyKey":"unique-random-identifier","exercise":"Barbell bench press","weight":225,"reps":5,"notes":"","details":{"buttFlat":true}}`.
- Both require HTTPS and `Authorization: Bearer <secret>`. Website cookies, Basic auth, URL parameters, and proxy/client-IP headers cannot substitute for this credential. Never put tokens in URLs, JavaScript, Git, or chat transcripts.
- No workout creation, deletion, or editing existing sets. Weights retain the app’s units (pounds).
- Retry an equivalent request with the same idempotency key for the original receipt. Field/property order does not matter. Changed values return 400. Retries after credential rotation still use the same idempotency key.

## Bounded resource use

Authenticated requests share a fixed UTC-minute budget of 120 requests, with a separate maximum of 30 append attempts per minute (including invalid requests/retries). Failed authentication permits 20 requests per minute per hashed IP slot; 256 fixed slots cap storage. Colliding IPs share that failed-auth budget. Failed authentication never consumes the valid credential’s budget. Rate files are outside the webroot, locked across PHP workers, and never named with a token or raw IP. Only `REMOTE_ADDR` is used; reverse proxies would share a slot unless server-level trusted proxy handling is configured.

Limits return 429 and `Retry-After` seconds until the next minute. A fixed window can allow twice its budget across a boundary. This is application abuse protection, not network DDoS protection; hosting-level traffic/connection limits still apply. Storage/lock corruption or contention returns 503 rather than bypassing security. Keep a single shared private directory on one host; this file limiter is not a distributed deployment design.

Append requests require an exact `application/json` media type (optional parameters), a maximum 16 KiB body, and bounded set fields. Validation occurs before connecting to MySQL. Append lock waits are limited to five seconds. Recent reads use `assistant_recent(kind,deleted,workout_date,id)` and SQL `LIMIT`, decoding at most 20 documents instead of loading the whole history. Responses exceeding 1,000,000 bytes of workout JSON return 413; request fewer workouts. Each sync document already has a 1 MiB write limit. The stored generated date projection follows all browser/assistant writes and tombstones automatically.

## Operator setup (not run automatically)

Apply additive schema setup using the existing `npm run setup:sync` workflow **before** enabling Assistant credentials. The schema adds a generated date column and index, which can rebuild/lock a large table: schedule appropriately and take the normal backup. No existing workout JSON, revisions, or audit records are changed. HTTP requests never run DDL. A missing index produces 503 rather than an unbounded fallback. PHP 8.1+, MySQL 5.7+/8 or MariaDB with JSON/generated-column support, and InnoDB are required. The generated column/index were integration-tested on MariaDB; verify your host’s engine/version before rollout.

The deployer’s release `.htaccess` includes `CGIPassAuth On` to forward Authorization under CGI/FastCGI. That configuration needs a later deployment; no hosting configuration was changed by this PR.

Run the CLI tool from a private checkout on the server (the `scripts` directory is not deployed into the public release). Explicitly select the existing private root outside the document root:

```sh
export FIELDWORK_PRIVATE_DIR="$HOME/.fieldwork"
php scripts/assistant/token.php provision "$HOME/assistant-credential.txt" 30
php scripts/assistant/token.php status
# Supply a NEW, nonexistent absolute output filename:
php scripts/assistant/token.php rotate "$HOME/assistant-credential-next.txt" 30
php scripts/assistant/token.php revoke
```

The tool generates 384 random bits and writes the 64-character URL-safe bearer secret only into a new owner-only (0600) output file. No secret is accepted in command arguments or printed. Transfer it into the intended connector’s secure credential store, then securely remove the temporary output file according to the host’s storage policy. Provision refuses an existing credential; rotate replaces it immediately, without an overlap/grace period. Update the client to the new secret; already admitted in-flight requests can finish. Revoke disables future authentication. Status prints configuration/expiry only. Default lifetime is 30 days; permitted range 1–90 days. Expired tokens receive the same generic 401 as missing/invalid tokens.

Only a SHA-256 hash and expiry are kept in `assistant-private/credential.json`. This dedicated directory must be 0700, state files 0600, with no symlinks/hardlinks. Do not chmod the shared `.fieldwork` root to 0700: Apache may need traversal for releases. Private state changes use an exclusive lock. Interrupted writes fail closed (re-provision/rotate if necessary), never restoring an old token. Keep the directory on a local filesystem with reliable `flock` semantics. Preserve rate files during rotation so rotating cannot reset abuse budgets.

The old plaintext `assistant-token` file is **not accepted**. Existing experimental clients must receive a newly provisioned credential; remove the legacy secret file after switching. No credentials are provisioned or migrated automatically.

## Failures and observability

401 uses a Bearer challenge. Unsupported methods return 405 with `Allow`. Client validation returns generic 400; unexpected configuration/database/JSON failures return generic 503. Neither exception messages nor request headers/bodies/tokens/notes/IPs are logged by the Assistant endpoint; PHP display errors are disabled. Monitor hosting HTTP status counts (especially 429/503), with Authorization and body logging disabled. Never supply tokens in query strings, which hosting access logs may retain. Security testing bypasses HTTPS only under PHP’s local development server with explicit test flags; production web SAPIs cannot activate it.

The website login, CSRF checks, ordinary sync protocol, and sync rate behavior are unchanged. Assistant credentials have read/append authority over the single account’s journal; revoke a leaked credential promptly. This is not multi-user authorization.

## Append semantics

The shared InnoDB writer lock serializes Assistant and browser changes. The whole document and existing sets retain object/array types, unknown metadata, notes, and original source. Only the new set and workout `updatedAt` change. Each accepted set receives UTC `loggedAt` and `completedAt` at initial acceptance (assuming just completed); retries retain the original set ID, revision, timestamps, and receipt. Historical/delayed entries can be corrected in the app.

## Reproducible tests

```sh
npm test
npm run build:hosted
php scripts/assistant/test-security.php
PHP_BINARY=php FIELDWORK_ASSISTANT_TEST_CONFIG=/absolute/path/local-admin-config.json python scripts/run-assistant-tests.py
```

The runner requires PHP PDO MySQL, Node/browser dependencies, and an admin configuration targeting localhost/127.0.0.1 with create/drop-database permission. It creates a unique disposable database, private credentials and loopback servers, then removes them in `finally`. No production configuration/data is needed. Build the hosted app first for the browser test.

Coverage includes PHP locking/permissions; bearer-only auth; request/method bounds; separate rate budgets/reset; missing schema/corrupt state; indexed query plans over 500+ records; additive schema upgrade; rotation, expiry and revocation; response-size limits and date/tombstone projection updates; injected database failure/lock-timeout rollback and recovery; JSON preservation and stable idempotency; ordinary sync validation, CSRF/origin rejection, conflicts, pagination and tombstones; and real browser form login, stable session/CSRF writes, offline reopening, and expired-session cache protection. Browser tests simulate a phone viewport in Chromium; they do not replace physical iOS/PWA testing.
