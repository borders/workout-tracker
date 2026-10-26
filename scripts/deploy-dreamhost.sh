#!/usr/bin/env bash
# Run from your own computer. SSH and site passwords are entered interactively.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v ssh >/dev/null
command -v tar >/dev/null
if [[ ! -f dist/index.html ]] || ! node --input-type=module -e 'import{readFileSync}from"node:fs";if(!readFileSync("dist/index.html","utf8").includes("/workouts/assets/"))process.exit(1)'; then
  echo 'First run npm run build:hosted.' >&2; exit 1
fi
host=jborders@borderseng.com
# Reuse one authenticated SSH connection. Nothing stores your SSH password.
socket_dir=$(mktemp -d)
cleanup() { ssh -S "$socket_dir/control" -O exit "$host" >/dev/null 2>&1 || true; rm -rf "$socket_dir"; }
trap cleanup EXIT
ssh -M -S "$socket_dir/control" -o ControlPersist=120 -fN "$host"
remote=(ssh -S "$socket_dir/control" "$host")
# Preflight before creating any release or changing web content.
"${remote[@]}" 'set -eu
  test -d "$HOME/borderseng.com" || { echo "Expected document root ~/borderseng.com not found. Stop and confirm the DreamHost web directory." >&2; exit 1; }
  test ! -L "$HOME/borderseng.com" || { echo "Document root is a symlink; inspect it before deployment." >&2; exit 1; }
  command -v htpasswd >/dev/null || { echo "htpasswd is required for private site access." >&2; exit 1; }
  target="$HOME/borderseng.com/workouts"
  if [ -e "$target" ] || [ -L "$target" ]; then
    test -L "$target" || { echo "An existing /workouts directory was found. Nothing was changed; inspect it first." >&2; exit 1; }
    case "$(readlink "$target")" in "$HOME"/.fieldwork/releases/*) ;; *) echo "Existing /workouts link is not managed by this deployer. Stopping." >&2; exit 1;; esac
  fi
  mkdir -p "$HOME/.fieldwork/releases"
  # Apache needs traversal, but directory contents need not be listable.
  chmod 711 "$HOME/.fieldwork"
  chmod 755 "$HOME/.fieldwork/releases"
'
# Site login is separate from your DreamHost/SSH account and never enters Git.
ssh -t -S "$socket_dir/control" "$host" 'set -eu
  if [ ! -s "$HOME/.fieldwork/htpasswd" ]; then
    echo "Choose a NEW password for the workout website login (username: fieldwork)."
    umask 077
    htpasswd -Bc "$HOME/.fieldwork/htpasswd" fieldwork
  fi
  # Apache must read the bcrypt hashes; this file is outside every web directory.
  chmod 644 "$HOME/.fieldwork/htpasswd"
'
release=$(date -u +%Y%m%dT%H%M%SZ)-$(node -e 'console.log(require("node:crypto").randomBytes(4).toString("hex"))')
# Only the newly named release receives files; no --delete and no root .htaccess edits.
tar -C dist -cf - . | "${remote[@]}" "set -eu; umask 022; mkdir \"\$HOME/.fieldwork/releases/$release\"; tar -xf - -C \"\$HOME/.fieldwork/releases/$release\""
"${remote[@]}" "bash -s -- '$release'" <<'REMOTE'
set -euo pipefail
release="$HOME/.fieldwork/releases/$1"
root="$HOME/borderseng.com"
test -f "$release/index.html"
if [ -f "$HOME/.fieldwork/sync-config.json" ]; then
  php "$release/api/setup.php" --check
fi
test -s "$HOME/.fieldwork/htpasswd"
# Fail closed over HTTP: no Basic auth challenge or personal data on plaintext HTTP.
cat > "$release/.htaccess" <<HTACCESS
Options -Indexes
DirectoryIndex index.html
SSLRequireSSL
AuthType Basic
AuthName "Private workout journal"
AuthUserFile "$HOME/.fieldwork/htpasswd"
Require valid-user
<Files "sw.js">
  Header set Cache-Control "no-cache"
</Files>
HTACCESS
# Keep release directories traversable for the hosting account and its web server.
# The auth file and release store remain outside the public document root.
previous=$(readlink "$root/workouts" 2>/dev/null || true)
next="$root/.workouts-next-$1"
ln -s "$release" "$next"
mv -Tf "$next" "$root/workouts"
printf 'Deployed %s\n' "$release"
printf 'Previous release: %s\n' "${previous:-none}"
printf 'Open https://borderseng.com/workouts/ (website username: fieldwork).\n'
printf 'HTTP is denied; use HTTPS. Prior releases are retained for rollback.\n'
REMOTE
echo 'Upload complete. Verify HTTPS login and the existing homepage in your browser.'
echo 'Enable server sync in each browser after configuring MySQL with npm run setup:sync. Export a backup before first sync.'
