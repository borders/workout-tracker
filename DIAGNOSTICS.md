# Temporary PWA sync diagnostics

This diagnostic build leaves the existing Origin/CSRF authorization rule unchanged. PR #2 is not required to collect evidence. No production changes are made by the cloud agent.

Update your local checkout from main, then:

```sh
npm ci
npm run deploy:dreamhost
npm run diagnose:sync -- enable
```

With the existing Home Screen app installed, reopen it online and try **Sync now**. Do the same in Safari, noting which attempt was at which time. Do not clear app/site storage, remove the Home Screen app, or discard the pending workout. A newly loaded app tags requests as `standalone` or `browser`; an absent tag can mean an older cached app or a stripped header, so timestamps remain useful.

Then collect the output:

```sh
npm run diagnose:sync -- show
```

Copy the JSON lines into this chat. Once copied, disable logging and delete the captured records:

```sh
npm run diagnose:sync -- disable
```

The SSH command prompts locally if needed; do not put passwords in chat or command arguments. The CLI helper is uploaded outside the webroot. Enabling diagnostics does not modify MySQL, browser records, or application authorization. `enable` starts a fresh one-hour window and clears older captured diagnostics. It does not deploy the app; deploy first.

## Captured fields

- UTC timestamp, API action, method, response status.
- Display-mode tag (`standalone` or `browser`), informational only. It is reported by the client via display-mode media queries or iOS navigator.standalone; the server cannot independently verify it. It may be missing, outdated, stripped, or spoofed and is never used for authorization. Sec-Fetch-Site describes origin relationships, not PWA versus Safari. Use separate, timestamped attempts to corroborate the tag.
- Origin: an exact bare HTTP(S) origin, literal `null`, or a marker for absent, empty, or invalid/redacted input. Arbitrary strings, userinfo, URL paths, query strings, fragments, and control characters are never retained.
- Allowlisted Sec-Fetch-Site, Sec-Fetch-Mode, and Sec-Fetch-Dest values, with markers for missing/unknown values.
- Booleans indicating presence of the login cookie, sync cookie, and CSRF header; boolean result of CSRF comparison on pushes (`null` if comparison was not performed).

Cookie/header token values, Authorization, passwords, IP addresses, user agents, query strings, and workout request/response bodies are never logged. Only API responses are instrumented; this is not general HTTP logging.

Records and the enable flag live under `~/.fieldwork/sync-diagnostics/`, outside the website directory, with directory mode 0700 and file mode 0600. Writes stop after one hour and at 256 KB. Captured records remain available for inspection until `disable` deletes them; expiry stops writes rather than destroying the evidence. Logging failures are ignored so synchronization can continue. No publicly accessible log viewer is installed.

`csrf_matches: false` with a valid Origin points toward session/token state rather than the Origin check. `csrf_matches: true` with missing/null Origin and a 403 establishes the header-based rejection. A 401 from the gate points toward an expired/missing login session. Missing Fetch Metadata must not be treated as proof of same-origin context.

## Test

```sh
PHP_BINARY=php python scripts/test-diagnostics.py
```

This uses a private temporary directory and synthetic sentinels, with no database or production access. It checks the allowlist/redaction, expiry, disabled default, size cap, and purge behavior. Physical iPhone header behavior remains to be observed from the captured requests.
