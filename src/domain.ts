export type SetEntry = { id: string; reps: number | null; weight: number; exercise: string; notes: string; raw: string; kind: 'reps' | 'hold'; flags: string[] };
export type Workout = { id: string; date: string; dateLabel: string; location: string; notes: string; sets: SetEntry[]; raw: string; flags: string[]; updatedAt: string };
export type JournalImport = { id: string; text: string; importedAt: string };
const hash = (s: string) => { let h = 2166136261; for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return (h >>> 0).toString(16); };
export function parseSet(raw: string, exercise = 'Barbell bench press'): SetEntry | null {
  const m = raw.trim().match(/^(\?|\d+(?:\.\d+)?)\s*([xz])?\s+(\d+(?:\.\d+)?)\s*(?:lb[s]?)?\s*(.*)$/i);
  if (!m) return null;
  const notes = m[4]; const flags: string[] = [];
  const reps = m[1] === '?' ? null : Number(m[1]);
  if (reps === null) flags.push('Unknown repetitions');
  if (reps !== null && !Number.isInteger(reps)) flags.push('Partial repetition');
  if (m[2]?.toLowerCase() === 'z' || !m[2]) flags.push('Check set notation');
  if (/db|dumbbell/i.test(notes)) exercise = /op\b|overhead/i.test(notes) ? 'Dumbbell overhead press' : 'Dumbbell bench press';
  else if (/leg press/i.test(notes)) exercise = 'Leg press';
  else if (/eagle row/i.test(notes)) exercise = 'Eagle row';
  else if (/chest press|bench machine/i.test(notes)) exercise = 'Machine chest press';
  else if (/\bbench\b/i.test(notes)) exercise = 'Barbell bench press';
  return { id: crypto.randomUUID(), reps, weight: Number(m[3]), exercise, notes, raw, kind: /static hold/i.test(notes) ? 'hold' : 'reps', flags };
}
export function parseJournal(text: string, newestYear = 2026): Workout[] {
  const workouts: Workout[] = []; let current: Workout | undefined; let year = newestYear; let previousMonth = 13; let defaultExercise = 'Barbell bench press';
  for (const line of text.replace(/\r/g, '').split('\n')) {
    const date = line.trim().match(/^(\d{1,2})\/(\d{1,2}|\?\??)(?:\s+(.*))?$/);
    if (date) {
      const month = Number(date[1]); if (month > previousMonth) year--; previousMonth = month;
      const day = /^\d+$/.test(date[2]) ? Number(date[2]) : null;
      const valid = day !== null && month >= 1 && month <= 12 && day >= 1 && day <= new Date(Date.UTC(year, month, 0)).getUTCDate();
      const label = `${year}-${date[1].padStart(2, '0')}-${valid ? String(day).padStart(2, '0') : '??'}`;
      const context = date[3] || '';
      defaultExercise = /db|dumbbell/i.test(context) ? 'Dumbbell bench press' : /decline/i.test(context) ? 'Decline barbell bench press' : 'Barbell bench press';
      current = { id: '', date: valid ? label : '', dateLabel: label, location: context, notes: '', sets: [], raw: line, flags: valid ? [] : ['Unknown or invalid date'], updatedAt: new Date().toISOString() };
      workouts.push(current); continue;
    }
    if (!current) continue;
    current.raw += '\n' + line;
    const set = parseSet(line, defaultExercise);
    if (set) current.sets.push(set);
    else if (line.trim()) current.notes += (current.notes ? '\n' : '') + line;
  }
  for (const w of workouts) w.id = 'import-' + hash(w.dateLabel + '\n' + w.raw.trim());
  return workouts;
}
export function volume(w: Workout, exercise?: string) { return w.sets.filter(s => s.kind === 'reps' && (!exercise || s.exercise === exercise)).reduce((n, s) => n + (s.reps ?? 0) * s.weight, 0); }
export function estimatedMax(s: SetEntry) { return s.kind === 'reps' && s.reps !== null && s.reps > 0 && s.reps <= 10 ? s.reps === 1 ? s.weight : s.weight * (1 + s.reps / 30) : null; }
