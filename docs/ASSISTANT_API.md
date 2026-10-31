# Assistant API (PR #5, experimental)

**Do not deploy until Codex reviews and runs the disposable-database tests.**
No ChatGPT connector exists yet; this is a server endpoint, not voice logging from ChatGPT.

## Routes
- `GET /workouts/api/assistant.php?action=recent&limit=5`: returns recent workouts and up to 15 sets per workout.
- `POST /workouts/api/assistant.php?action=append_set`: appends one repetitions set to an **existing explicit workout ID**. JSON example:
  `{"workoutId":"existing-id","idempotencyKey":"unique-random-identifier","exercise":"Barbell bench press","weight":225,"reps":5,"notes":"","details":{"buttFlat":true}}`
- Both routes require `Authorization: Bearer <secret>`. The assistant API **does not accept website cookies as authentication**.
- It never deletes workouts or edits existing sets. It cannot create a new workout yet.
- Repeat an equivalent request with the same idempotency key to retrieve the original receipt without creating a duplicate. Request field order and technique-property order do not matter; changed values still return 400.

## Credential provisioning (not done automatically)
Before enabling the feature in a controlled environment, provision a cryptographically random URL-safe secret of at least 40 characters into `assistant-token` inside `FIELDWORK_PRIVATE_DIR`, outside the website document root. Keep the token file owner-only (0600) outside the webroot. Do not change an existing shared `~/.fieldwork` directory to 0700: Apache may need its current traversal permissions to serve release assets. Dedicated private test directories use 0700. Do **not** put this token in JavaScript, in git, or into a chat transcript. If the file is missing, calls fail closed with 401. Rotate/revoke it by replacing/removing this file. Ensure TLS is enforced.

A cross-origin ChatGPT plugin with secure credential storage and access to this API has **not** been configured; suitability for live voice remains unverified. Avoid enabling credentials on production until connector capability, abuse limits, and token lifecycle are reviewed.

## Tests
Run PHP syntax checks, `npm test`, `npm run build:hosted`, browser/sync regression tests, and `scripts/test-assistant-api.py` using a **disposable** local MariaDB database, test-only PHP server with `FIELDWORK_TESTING=1`, a temporary `FIELDWORK_PRIVATE_DIR`, and `ASSISTANT_TEST_TOKEN` matching that test-only token file. The integration test adds a synthetic workout; never run it on production.

Review checklist:
- Denied request without token, invalid token, wrong method and malformed payload.
- Read recent workouts, append one set, repeat request and verify exactly one set, reject same key with altered values.
- Verify sync to another browser, concurrent edits, DB interruption/retry, request size, error logging, token revocation, and large-database read performance.
- Verify no deployed browser sync behavior changed. Do not merge until the remaining tests and operational controls are complete.

## Reviewed append semantics

Appending reads the latest workout inside the shared InnoDB writer transaction. The whole document and existing sets retain JSON object/array types, unknown metadata, notes, and original source. Only the appended set and workout `updatedAt` are added/changed. The read endpoint also retains JSON object/array types.

Every newly accepted set receives server-generated UTC `loggedAt` and `completedAt`, both set to its initial server acceptance time. This assumes the set was just completed; delayed/historical entries can be corrected in the app. Both timestamps are returned in the receipt. They are generated only after the idempotency lookup and are not part of the request fingerprint. Retrying later therefore returns the original set ID, revision, and timestamps, rather than logging another set or changing its recorded time.

## Reproducible local regression suite

```sh
PHP_BINARY=php FIELDWORK_ASSISTANT_TEST_CONFIG=/absolute/path/local-test-config.json python scripts/run-assistant-tests.py
```

The admin configuration must target localhost/127.0.0.1 and permit creating/dropping disposable databases. The runner creates a uniquely named database, a private temporary credential file/token, and a loopback-only PHP server; it removes them afterward. No production access or existing workout fixtures are needed. The test client retains the ordinary sync session cookie when seeding synthetic data.

Checks cover token rejection and actual gate routing; preserved workout/session and existing-set metadata (including nested empty objects/arrays); timestamps stable across delayed and reordered retries; rejection of changed key reuse; ordinary sync pull of the appended workout; browser edits before append being retained; and stale browser edits after append conflicting instead of dropping the new set.

Rate limiting, bounded large-database reads, token lifecycle tooling, and an actual ChatGPT voice connector remain separate unfinished work. Passing these regressions does not make the API ready for production enablement or prove that ChatGPT voice can call it.
