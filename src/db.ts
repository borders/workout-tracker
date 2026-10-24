import { openDB } from 'idb';
import type { Workout, JournalImport } from './domain';
const db = openDB('fieldwork', 1, { upgrade(db) { db.createObjectStore('workouts', { keyPath: 'id' }); db.createObjectStore('imports', { keyPath: 'id' }); } });
export async function allWorkouts(): Promise<Workout[]> { return (await db).getAll('workouts'); }
export async function saveWorkout(w: Workout) { await (await db).put('workouts', w); }
export async function importWorkouts(ws: Workout[], source: JournalImport) { const d = await db; const tx = d.transaction(['workouts', 'imports'], 'readwrite'); let added = 0; for (const w of ws) { if (!await tx.objectStore('workouts').get(w.id)) { await tx.objectStore('workouts').put(w); added++; } } await tx.objectStore('imports').put(source); await tx.done; return added; }
export async function exportData() { const d = await db; return { version: 1, exportedAt: new Date().toISOString(), workouts: await d.getAll('workouts'), imports: await d.getAll('imports') }; }
