# Architecture and decisions

The browser is the immediate write target. IndexedDB transactions atomically persist journal imports and workouts. Original import documents are retained independently of structured, editable sessions. React renders data only after asynchronous reads and acknowledges writes only after persistence.

Workout IDs generated for new sessions are UUIDs. Imported session IDs are deterministic hashes of the inferred date and original entry. Identical imports are idempotent; modified source entries may produce new sessions and should be reviewed before reimporting. The current non-cryptographic hash is not a global identity guarantee and must be upgraded before server synchronization or adversarial imports.

Dates use local calendar strings, not UTC timestamps, to prevent an iPhone timezone change from moving the workout to another day. Modification times use UTC ISO timestamps. An unknown date has an empty sortable date and a separate uncertainty label. Decimal and unknown repetitions retain their original representation and review flags. Holds remain distinct from completed repetitions.

A future server will be the shared durable store, not a prerequisite for entering a set. Synchronization requires durable client operations, per-record server revisions, deletion tombstones, and explicit conflict handling. An imported source document must remain immutable. Backend authentication and synchronization are not implemented in this milestone.

The frontend is a static Vite build, compatible with PHP shared hosting. The service worker caches same-origin successful GET responses, excluding API routes. Deployment needs an asset/version strategy and tested offline upgrades before release. A network indicator is not a synchronization indicator; the UI reports local storage rather than claiming cloud sync.
