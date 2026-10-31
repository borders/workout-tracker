# One-time imported bench classification repair

**Codex / operator: DO NOT MERGE OR RUN ON PRODUCTION UNTIL REVIEWED.** This migration is not part of normal deployment. It does not auto-run. The reviewed branch has been updated with current `main`, including the PWA CSRF session fix; no force-push/rewrite was used.

The scan evaluates whole imported sessions. It flags sessions where at least two barbell-labelled bench sets are all between 35 and 100 lb, or sessions mixing explicit dumbbell and barbell labels. Any session containing a bench set over 110 lb is excluded from proposed dumbbell conversions (the user's stated historical maximum is at most 110 lb per dumbbell). Isolated 45-lb warm-ups beside heavier barbell sets are not flagged. These are candidates only, never automatic corrections; review all sets and original notes. Dumbbell weights retain their recorded per-dumbbell convention.

## Review and validation
1. Review the PHP script for CLI-only access, JSON preservation, revision-aware writes, validation, backup paths, and repeated-run behavior.
2. Run `php -l scripts/migrations/reclassify-bench.php`, `npm test`, `npm run build:hosted`, and `python scripts/test-deploy.py`.
3. Exercise the script with a **disposable local MariaDB database** with synthetic records and confirm scan does not mutate; apply touches only approved set IDs; reruns reject revision mismatch; local sync clients receive the updated records. Do not run tests on production.
4. Apply uses one InnoDB transaction for the entire approval list. Verify the failure/interruption tests below; do not replay blindly if commit confirmation is lost.

## Manual production procedure (only after Codex review)
1. Confirm all devices are synced, export an app JSON backup and take an independent MySQL database backup. Pause edits while applying.
2. Deploy the reviewed script to a **non-public directory** on the server (e.g. `~/.fieldwork/tools`) via a reviewed secure copy procedure; do not deploy PHP migration scripts inside the webroot.
3. From the directory containing the script, run a CLI scan: `php reclassify-bench.php scan /absolute/private/candidates.json` (adjust script's relative bootstrap to match deployment placement or invoke it from a trusted repository checkout **outside webroot**). Review the full sessions and source notes. The script uses the same `FIELDWORK_CONFIG` resolution as the backend, so set that environment variable to the existing private config path when running from a separate checkout.
4. Prepare an approval JSON with exact workout IDs, their current revisions, and selected set IDs. Example:

```json
{"changes":[{"workoutId":"import-example","revision":17,"setIds":["set-example"]}]}
```

5. Apply once: `FIELDWORK_CONFIG="$HOME/.fieldwork/sync-config.json" php scripts/migrations/reclassify-bench.php apply /absolute/private/approvals.json /absolute/private/bench-backup-unique.json` from a server-side repository checkout that contains `server/api/lib.php`. Backup file must not exist beforehand and is created with restricted permissions. **The script is NOT executed by `npm run deploy:dreamhost`.**
6. Verify corrected exercises in both Safari and the installed PWA after synchronization; resolve conflicts manually. Preserve the before-state backup and logs.

## Limits
The scan does not have access to the actual production workouts until invoked on the server. There are no preapproved classifications in this PR. The script does not automatically correct low-weight workouts, and does not modify original import text. It uses `pushOperationInTransaction` to retain the same revision and audit rules while one caller-owned transaction covers all approved workouts. Normal API sync still uses the original per-operation transaction wrapper.

Do not promise one-command rollback: restoring a database backup while active clients sync can reintroduce conflicts. Rollback requires a planned, revision-aware reverse migration or coordinated full DB restoration with clients offline.

## Regression checks for the review fixes

Workouts are decoded as JSON objects during apply, preserving empty objects, nested objects, numeric object keys, arrays, and unknown attributes. Only the explicitly approved exercise labels are changed. Candidate reports and backups use exclusive file creation with mode 0600 from the first byte, reject symlink targets, and require a private parent directory (mode 0700). Existing output files are never overwritten; failed writes stop before migration writes. Use `mkdir -m 700` for a new private output directory, or restrict an existing intended private directory with `chmod 700`.

Run the automated regression suite with a **local disposable MySQL admin configuration** (not the DreamHost production configuration):

```sh
PHP_BINARY=php FIELDWORK_MIGRATION_TEST_CONFIG=/absolute/path/local-test-config.json python scripts/migrations/test-reclassify-bench.py
```

The configuration uses the backend JSON format, points only to localhost/127.0.0.1 (or a local socket), and must permit creating and dropping test databases. The suite creates a uniquely named database and removes it afterward, and uses owner-only temporary config/output directories. It verifies candidate selection, read-only scanning, exact approved changes, JSON type preservation, original backups, restrictive report permissions even under umask 022, existing-file and symlink rejection, concurrent scan exclusivity, stale-revision rejection, and invalid approvals.

## Atomic apply and interruptions

All three sync tables must use InnoDB; apply checks this before starting. The migration acquires the same global writer lock as sync, locks and checks every approved workout revision, validates every operation, and persists the private before-state backup before performing any updates. It then updates all approved workouts, allocates their revisions, and records all operation receipts inside one transaction. Success messages are printed only after the single commit.

Errors, stale approvals, and process/connection loss before commit roll back the whole batch, including allocated revisions and operation receipts. A surviving backup after an aborted run is expected and does not mean the batch committed. Use a new backup path for a reviewed retry. Normal sync writes may wait while the transaction is active; pause editing and keep the approval batch focused. Scan remains read-only.

An interruption cannot be prevented. If it occurs during/after commit, the database still commits everything or nothing, but the terminal may not receive confirmation. The backup includes the exact `operationIds`. Inspect those IDs in `fw_operations` and compare current workout revisions before considering another apply; do not assume failure just because the terminal disconnected. Do not restore a whole database while devices are actively syncing.

The disposable-database suite also injects a second-write SQL failure, tests stale second approvals, kills a CLI and its database connection mid-batch, verifies concurrent readers see no uncommitted changes, verifies complete success and repeated-run rejection, and checks that revisions and audit receipts roll back with the workouts. No production classifications have been approved or executed.
