#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command=${1:-}
case "$command" in enable|show|disable) ;; *) echo 'Usage: npm run diagnose:sync -- enable|show|disable' >&2;exit 1;; esac
host=jborders@borderseng.com
socket_dir=$(mktemp -d)
cleanup(){ ssh -S "$socket_dir/control" -O exit "$host" >/dev/null 2>&1 || true; rm -rf "$socket_dir"; }
trap cleanup EXIT
ssh -M -S "$socket_dir/control" -o ControlPersist=120 -fN "$host"
# One-shot CLI helper stays outside the public website. No application/database changes.
ssh -S "$socket_dir/control" "$host" 'set -eu; umask 077; mkdir -p "$HOME/.fieldwork/diagnostic-tools"; cat > "$HOME/.fieldwork/diagnostic-tools/diagnostics.php"' < server/api/diagnostics.php
ssh -S "$socket_dir/control" "$host" "FIELDWORK_DIAGNOSTICS_DIR=\"\$HOME/.fieldwork/sync-diagnostics\" php \"\$HOME/.fieldwork/diagnostic-tools/diagnostics.php\" '$command'"
