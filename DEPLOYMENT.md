# DreamHost deployment

Target: `https://borderseng.com/workouts/`. HTTPS is required for offline/PWA support and the private journal login. This is the static frontend deployment; MySQL synchronization is not implemented. Browser data from localhost is a different origin and is not automatically transferred. Export local changes first; the bundled historical journal loads independently on each browser.

The direct cloud deployment attempt was blocked by SSH DNS/network access. No remote files have been changed. A network draft allowing `borderseng.com` has been saved, but that does not enable runtime SSH or authenticate the connection.

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
- `https://borderseng.com/workouts/` requests website credentials; use username `fieldwork`.
- HTML, JS, CSS, manifest, and service worker require authentication. A logged-out browser must not receive the journal bundle.
- HTTP requests are denied (403); access the HTTPS URL directly. This intentionally does not rely on an HTTP auth challenge or the existing site redirect rules.
- The app loads all 401 historical sessions, saves a new test session, survives reload, and can reopen after going offline.
- On iPhone, test using Safari before adding to the Home Screen. Confirm authentication and offline behavior on the physical phone; neither has been validated on DreamHost yet.

Basic authentication controls server access; it does not encrypt browser IndexedDB or remove cached personal data after the browser forgets the website password. Use a trusted device/browser profile.

## Rollback

The deploy command reports the previous release’s absolute path. To roll back, connect via SSH, create a temporary symlink to that exact retained release, and atomically replace only `~/borderseng.com/workouts` with it. Never delete or change the main document root. Inspect the existing link and release paths before doing this.
