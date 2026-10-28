# DreamHost deployment

Target: `https://borderseng.com/workouts/`. HTTPS is required for offline/PWA support and the private journal login. The release includes the frontend and PHP sync API. Activate MySQL using [SYNC.md](SYNC.md). Browser data from localhost is a different origin and is not automatically transferred. Export local changes first; the bundled historical journal loads independently on each browser.

HTTPS access from the cloud now reaches the protected application. SSH still fails (hostname DNS failure and direct-IP port 22 refusal), so deployments run from your computer. No deployment or remote configuration change has been made by the cloud agent.

## Deploy from your computer

Download the updated repository ZIP, extract it, then run:

```sh
npm ci
npm run deploy:dreamhost
```

Use Terminal on macOS/Linux, or Git Bash/WSL on Windows. The script requires OpenSSH, Bash, tar, Node, and a remote `htpasswd` command. It builds specifically for `/workouts/`, authenticates interactively to `jborders@borderseng.com`, and prompts for a separate website password on the first deployment. No password is written to Git or embedded in command arguments. Verify the SSH host fingerprint through DreamHost before accepting a new host key. Rotate the SSH password shared in chat before using it again.

The script expects DreamHost’s document root to be `~/borderseng.com`; if this differs, it stops before uploading. Check the actual Web directory in the DreamHost panel. It also stops for an existing unmanaged `/workouts` path. It never changes the homepage or the root `.htaccess`.

New releases live under `~/.fieldwork/releases/` outside the document root. A protected `.htaccess` is written before publishing via a `/workouts` symlink. Website credentials live in `~/.fieldwork/htpasswd`. Existing releases remain available for rollback. The private parent directory allows traversal without listing (0711), release directories are readable by Apache, and the bcrypt password file is readable by Apache (0644) outside the document root. No plaintext website password is stored. The setup assumes DreamHost Apache supports symlinks, SSLRequireSSL, Basic authentication, and mod_headers; remote compatibility has not been verified. If incompatible it should fail closed rather than publish an unprotected journal. Do not loosen authentication to resolve a hosting error.

## Verify after deployment

- The existing homepage still works.
- `https://borderseng.com/workouts/` displays a sign-in form; use username `fieldwork`.
- HTML, JS, CSS, manifest, and service worker require authentication. A logged-out browser must receive only the sign-in page or a 401 for protected assets/API.
- HTTP requests are denied (403); access the HTTPS URL directly. This intentionally does not rely on an HTTP auth challenge or the existing site redirect rules.
- The app loads all 401 historical sessions, saves a new test session, survives reload, and can reopen after going offline.
- On iPhone, test using Safari before adding to the Home Screen. Confirm authentication and offline behavior on the physical phone; neither has been validated on DreamHost yet.

Basic authentication controls server access; it does not encrypt browser IndexedDB or remove cached personal data after the browser forgets the website password. Use a trusted device/browser profile.

## Rollback

The deploy command reports the previous release’s absolute path. To roll back, connect via SSH, create a temporary symlink to that exact retained release, and atomically replace only `~/borderseng.com/workouts` with it. Never delete or change the main document root. Inspect the existing link and release paths before doing this.

## Database setup

Before enabling server synchronization, follow [SYNC.md](SYNC.md). Run `npm run setup:sync` once to enter database credentials securely over SSH, then deploy normally. Existing deployments without database configuration continue to save locally and display an actionable error if sync is enabled. No database credentials belong in this document or the public web tree.

## Home Screen sign-in update

The hosted deployment now uses a PHP sign-in page rather than the browser’s Basic authentication dialog, which is unreliable in iPhone Home Screen web apps. The same `fieldwork` website username and existing bcrypt password file are reused. Every app, asset, and API request passes through `gate.php` via Apache rewrite rules. No journal bundle is public without a valid login session. The root website is unchanged.

Sessions use a separate private server directory and a Secure, HttpOnly, SameSite Strict cookie scoped to `/workouts/`, with a 30-day maximum login lifetime. Login pages are marked no-store and are excluded from the service-worker cache. When a login expires, reopening the app shows the form rather than an Unauthorized page. Offline cached data remains accessible on the trusted device, as before.

After updating the local project, run `npm ci` and `npm run deploy:dreamhost`. Reopen the existing Home Screen icon while online and sign in using the website password. Do not delete site data or remove the app to troubleshoot login; export backups before any storage changes. A physical iPhone test is still needed after deployment.
