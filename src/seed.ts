import { importWorkoutsOnce } from './db';
import { parseJournal } from './domain';

// Empty for general builds. Personal source files are included only with owner approval.
const sources = import.meta.glob('./seed/*.txt', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

export async function loadBundledJournal(): Promise<number> {
  let added = 0;
  for (const text of Object.values(sources)) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
    const id = 'bundled-' + Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
    added += await importWorkoutsOnce(parseJournal(text, 2026), {
      id,
      text,
      importedAt: new Date().toISOString(),
    });
  }
  return added;
}
