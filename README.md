# Fieldwork

A personal workout journal. React + TypeScript, IndexedDB, and a production service worker. The current milestone runs entirely on the device; it does not send workout data to a server.

## Develop

Use the existing checkout at `/workspace/workout-tracker`. Each cloud task already has an isolated workspace; do not create another worktree unless requested.

```sh
cd /workspace/workout-tracker
npm ci
npm run dev
```

## Validate

```sh
npm test
npm run build
npm run test:browser
node scripts/logging-smoke.cjs
# For production offline checks, first serve dist on port 4173:
# npx vite preview --host 0.0.0.0 --port 4173
APP_URL=http://localhost:4173 TEST_OFFLINE=1 npm run test:browser
```

The browser smoke test uses its own temporary browser profile and synthetic fixtures, not personal journal data. It exercises mobile logging, IndexedDB persistence, import deduplication, search, and charts.

## Current capabilities

- Separate weight and reps inputs, pause selection, butt-flat and feet-up toggles, difficulty, and set notes. Reps, weight, pause, and position carry forward within an exercise; difficulty and notes reset after saving. Journal text imports still support decimal and unknown repetitions.
- Optional session context: body weight (lb/kg), sleep hours and quality, fueling, readiness, and session notes. Save separately or along with a set. Each session starts with its own context.
- Rest timer with optional auto-start, presets/custom duration, pause/resume, +30 seconds, skip, overtime display, and opt-in foreground sound. Timer deadlines persist across reloads; sound must be re-enabled by a tap after reload. Background/locked-screen alarms are not guaranteed.
- Actual logging timestamps and editable completion timestamps. Completion intervals and explicitly entered rest durations remain separate. Existing imported timestamps are not invented.
- Multiple exercise types, editable historical sessions (add/edit/remove sets).
- Searchable history, source text inspection, and JSON export including full import sources.
- Text import with newest-year anchoring, year rollover inference, invalid-date flags, stable session IDs, and exact repeat deduplication.
- Per-exercise estimated 1RM chart. Singles use actual weight; Epley applies to 2–10 reps. Holds and failed/unknown reps are excluded.
- Production PWA manifest and service worker. The browser must first load online; HTTPS is required away from localhost. Runtime-loaded same-origin assets are cached for offline use.

## Important limits

Personal journal source files can be bundled in `src/seed/*.txt` with the owner’s approval. On startup, the app imports each source exactly once per browser database. Existing sessions and edited sets are preserved; the complete original source is included in JSON backups. No personal source is published without approval. The prepared journal is also retained in ignored `private-data/journal.txt` on the cloud machine.

With the personal journal available, `node scripts/journal-smoke.cjs` validates all 401 sessions and 2,854 sets, the April 22 PR, unknown dates, and preservation of edits after reload. General browser checks use temporary profiles and never change your computer’s browser database.

The importer deliberately does not infer equipment from hotel names or load magnitudes. Ambiguous sessions require classification review. Notes preserve technique but the initial chart does not filter technique variations. Dumbbell weights retain their recorded value; total two-dumbbell tonnage is not inferred. Unknown reps contribute zero to recorded volume; this is incomplete rather than an estimate. The original source is retained separately when imported, so manual edits do not overwrite it.

Production offline reload and offline set entry passed Chromium browser validation. Installation on a physical iPhone, JSON restore, and cross-device synchronization still need validation/implementation. Export backups before clearing browser data. There is no login or server backup yet. Do not deploy this as a shared authenticated service until the backend is implemented.

## Next backend milestone

DreamHost-compatible PHP 8 and MySQL, with a single user and password-hashed login, secure HttpOnly SameSite sessions, CSRF protection, UUID records, revisions, tombstones, and an operation outbox. Sync uses compare-and-swap revisions and records conflicts for explicit resolution, retaining both versions. Never use silent last-write-wins. Store server secrets outside the public document root. Static frontend builds deploy to the web root; a PHP API runs alongside them. No database credentials are needed for local frontend development.

## Privacy

Personal imports and exports should stay outside Git (use ignored `private-data/`). No telemetry or hosted data service is configured. Fonts use the system font stack; no remote font requests are made.

## Updating your local ZIP checkout

Stop Vite with Ctrl+C, download a fresh ZIP from GitHub, extract it, and run `npm ci` and `npm run dev` in the new directory. Use the same browser profile, hostname, and port to retain local IndexedDB data. Export a backup first. The bundled journal is imported once and does not replace your edits.

If you cloned with Git instead, stop Vite and use `git pull --ff-only`, `npm ci`, and `npm run dev`.

## Hosting on DreamHost

See [DEPLOYMENT.md](DEPLOYMENT.md) for the protected `/workouts/` deployment. Use `npm run deploy:dreamhost` from your computer after updating this checkout. This builds a subdirectory-aware bundle and prompts for SSH authentication and a separate website password. Direct deployment from the cloud workspace is currently blocked by network access; no DreamHost files have been changed by the cloud setup.
