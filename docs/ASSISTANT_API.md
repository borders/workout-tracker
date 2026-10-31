# Assistant API (PR #5, experimental)

**Do not deploy until Codex reviews and runs the disposable-database tests.**
No ChatGPT connector exists yet; this is a server endpoint, not voice logging from ChatGPT.

## Routes
- `GET /workouts/api/assistant.php?action=recent&limit=5`: returns recent workouts and up to 15 sets per workout.
- `POST /workouts/api/assistant.php?action=append_set`: appends one repetitions set to an **existing explicit workout ID**. JSON example:
  `{"workoutId":"existing-id","idempotencyKey":"unique-random-identifier","exercise":"Barbell bench press","weight":225,"reps":5,"notes":"","details":{"buttFlat":true}}`
- Both routes require `Authorization: Bearer <secret>`. The assistant API **does not accept website cookies as authentication**.
- It never deletes workouts or edits existing sets. It cannot create a new workout yet.
- Repeat the same request with the same idempotency key to retrieve the original receipt without creating a duplicate.

## Credential provisioning (not done automatically)
Before enabling the feature in a controlled environment, provision a cryptographically random URL-safe secret of at least 40 characters into `assistant-token` inside `FIELDWORK_PRIVATE_DIR`, outside the website document root. Protect the directory (0700) and file (0600). Do **not** put this token in JavaScript, in git, or into a chat transcript. If the file is missing, calls fail closed with 401. Rotate/revoke it by replacing/removing this file. Ensure TLS is enforced.

A cross-origin ChatGPT plugin with secure credential storage and access to this API has **not** been configured; suitability for live voice remains unverified. Avoid enabling credentials on production until connector capability, abuse limits, and token lifecycle are reviewed.

## Tests
Run PHP syntax checks, `npm test`, `npm run build:hosted`, browser/sync regression tests, and `scripts/test-assistant-api.py` using a **disposable** local MariaDB database, test-only PHP server with `FIELDWORK_TESTING=1`, a temporary `FIELDWORK_PRIVATE_DIR`, and `ASSISTANT_TEST_TOKEN` matching that test-only token file. The integration test adds a synthetic workout; never run it on production.

Review checklist:
- Denied request without token, invalid token, wrong method and malformed payload.
- Read recent workouts, append one set, repeat request and verify exactly one set, reject same key with altered values.
- Verify sync to another browser, concurrent edits, DB interruption/retry, request size, error logging, token revocation, and large-database read performance.
- Verify no deployed browser sync behavior changed. Do not merge until the remaining tests and operational controls are complete.
