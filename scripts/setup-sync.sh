#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
host=jborders@borderseng.com
socket_dir=$(mktemp -d)
cleanup(){ ssh -S "$socket_dir/control" -O exit "$host" >/dev/null 2>&1 || true; rm -rf "$socket_dir"; }
trap cleanup EXIT
ssh -M -S "$socket_dir/control" -o ControlPersist=120 -fN "$host"
setup_id=$(node -e 'console.log(require("node:crypto").randomBytes(8).toString("hex"))')
# Setup code stays outside the public document root. Database passwords are typed on the remote terminal.
ssh -S "$socket_dir/control" "$host" "set -eu; umask 077; mkdir -p \"\$HOME/.fieldwork/setup-$setup_id\""
tar -C server/api -cf - lib.php setup.php | ssh -S "$socket_dir/control" "$host" "tar -xf - -C \"\$HOME/.fieldwork/setup-$setup_id\""
ssh -t -S "$socket_dir/control" "$host" "FIELDWORK_CONFIG=\"\$HOME/.fieldwork/sync-config.json\" php \"\$HOME/.fieldwork/setup-$setup_id/setup.php\""
echo 'Database setup finished. Run npm run deploy:dreamhost, then Enable server sync on each device.'
