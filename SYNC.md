# Server synchronization

The app continues to save locally first. The PHP API stores revisioned workout and original-journal documents in MySQL. It reuses the website’s existing `fieldwork` password through the PHP sign-in page; there is no second application password or public write endpoint.

## Activate on DreamHost

1. Export a JSON backup from every browser containing workouts you care about. Keep those browsers’ data; do not clear site storage.
2. In DreamHost’s **MySQL Databases** section, create a dedicated database, for example `borders_workouts`, and a dedicated database user. Choose a MySQL hostname such as `mysql.borderseng.com` using the panel. Use the actual hostname shown there, not `localhost`, the website IP, or the SSH IP. Allow the new hostname/database to finish provisioning.
3. Download the latest repository (or pull if using a Git clone). In the local project folder run:

   ```sh
   npm ci
   npm run setup:sync
   npm run deploy:dreamhost
   ```

   The setup command connects over SSH, then prompts for the MySQL hostname, database name, username, and password. The password input is hidden. Do not paste the password into chat or Git. Credentials are stored at `~/.fieldwork/sync-config.json` on DreamHost with owner-only permissions, outside the web directory. PHP 8.1+ with PDO MySQL is required; check the PHP version for both the website and CLI.
4. Open `https://borderseng.com/workouts/`, refresh, and choose **Enable server sync**. Wait for **Synced with server**. Enable it separately in Safari on your phone and in your desktop browser.
5. Log a test set on one device. Use **Sync now** on the other and confirm it appears. On each device, confirm its pending count clears and there are no unresolved conflicts.

The setup script creates only `fw_meta`, `fw_records`, and `fw_operations` in the selected database. It does not change the rest of your site or unrelated tables. Existing configuration is verified and reused; it is not overwritten. Deployment checks the database before switching releases if configuration exists. If a setup command fails, paste its error without credentials; do not remove authentication or disable TLS checks.

The browser enables background polling every 30 seconds while the page is running, plus sync on saves, connectivity restoration, and returning to the foreground. An iPhone can suspend the page; it resumes synchronization when reopened. **Paused sync** leaves changes local until enabled again. Your website login session must still be valid when syncing.

## Initial data and conflicts

Existing IndexedDB data is migrated in place and queued for sync; workouts and original import documents are preserved. Independently loaded copies of the bundled journal reconcile even though older browsers assigned different set IDs and import timestamps. Changed notes, sets, session context, and attributes are compared; they are not silently overwritten. Two independently created workouts with different IDs remain two sessions even if their dates match.

Conflicts appear under **Server sync** with the local and server versions:

- **Keep both** adopts the server record and queues a separate copy of the local workout. This is the safest choice when unsure.
- **Use this device** keeps the local version and submits it against the reviewed server revision. Another intervening server change causes another conflict instead of overwriting it.
- **Use server** replaces the current local record with the reviewed server version.

All rejected operations that reached the server retain their submitted document in `fw_operations`, and server versions remain in the local conflict record until resolution. App JSON exports include local conflict records. This audit history is recovery support, not an independently scheduled database backup. Arrange DreamHost/database backups as well.

Workouts stored on `localhost` are a different browser origin from `borderseng.com`. This release syncs browsers using the hosted app, not a local dev app to a remote server via CORS. JSON exports are portable backups; a JSON restore UI is not implemented yet. Keep local data and exports rather than assuming it was uploaded from localhost.

The current app has no whole-workout deletion UI. Server tombstones are supported so future deletion features cannot resurrect records during normal pulls or seeded imports. Set removal is a revisioned workout edit.

## API and security

API path: `/workouts/api/sync.php`. Apache routes HTML, scripts, and API requests through the PHP session gate. PHP requires HTTPS and a valid server-side login session. The sync endpoint accepts a trusted in-process authentication marker set only by that gate (and retains compatibility with Apache REMOTE_USER on older Basic-auth deployments). It does not trust client-supplied username headers. Mutation requests require a same-origin Origin header and a per-session CSRF token; cookies are HttpOnly, Secure, and SameSite Strict. API responses are never cached. No CORS access is granted.

Writes use compare-and-swap revisions and durable operation IDs. A single InnoDB transaction serializes revision allocation, the document update, and the operation receipt. Batches validate up front; if a later operation fails after earlier ones commit, retrying is safe. Pulls paginate the latest records by a global monotonic revision, including tombstones. A different server database identity pauses sync instead of treating a reset database as authoritative.

Maximum one document: 1 MB. Maximum push batch: 25 operations / 8 MB request. The original journal and individual current workouts are comfortably below these limits. Tables store entire workout aggregates as JSON text so optional/future attributes are retained without destructive schema changes. Relational reporting tables can be added later; current charts use the synchronized browser records.

## Validation

```sh
npm test
npm run build:hosted
python scripts/test-deploy.py
```

Browser logging/offline regression tests remain in `scripts/smoke.cjs` and `scripts/logging-smoke.cjs`. Real API integration tests in `scripts/test-api.py` need a dedicated disposable local MySQL/MariaDB database and local PHP test server. Two-browser checks in `scripts/sync-smoke.cjs` need a separate empty disposable database. Both refuse non-local test URLs.

For local PHP HTTP tests only, `FIELDWORK_TESTING=1` bypasses HTTPS/Apache authentication **only** under PHP’s `cli-server` SAPI. CSRF and Origin validation remain enabled. Never run a public test server or set that flag in production. Configure the local test server with `FIELDWORK_CONFIG` pointing to an owner-only JSON configuration file outside the checkout/webroot. This switch is not usable through an HTTP request and does not bypass authentication under production PHP-FPM/CGI.

Current evidence: 19 passing unit tests; local PHP 8.4 + MariaDB 11 API checks (CSRF/origin rejection, retry idempotency, conflicts/resolution, 500-record pagination, and tombstones); and two independent browser profiles reconciling all 401 journal sessions, transferring new sets, conflicting offline edits, and retaining both versions. Browser regression checks also cover mobile logging and production offline reload/saving. DreamHost activation must still be verified after the user creates the database and runs the two setup/deployment commands; source-code tests do not establish live server readiness.
