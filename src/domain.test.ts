import { describe, it, expect } from 'vitest';
import { parseJournal, parseSet, volume, estimatedMax, parseDuration, formatDuration, timeBetweenSets } from './domain';
describe('journal import',()=>{
 it('infers successive year rollovers and retains unknown days',()=>{const ws=parseJournal('10/21 home\n3x 225 paused\n1/1\n1x 205\n12/29\n4x 195\n1/03\n3x 225\n12/30\n4x 220\n9/??\n?x 210');expect(ws.map(w=>w.dateLabel)).toEqual(['2026-10-21','2026-01-01','2025-12-29','2025-01-03','2024-12-30','2024-09-??']);expect(ws[5].date).toBe('');expect(ws[5].sets[0].reps).toBe(null);});
 it('preserves text and creates repeatable identities',()=>{const text='4/22\n1x 275 flat-ish (crazy battle) PR';expect(parseJournal(text)[0].raw).toBe(text);expect(parseJournal(text)[0].id).toBe(parseJournal(text)[0].id);});
 it('separates explicit exercise types and holds from lifting volume',()=>{const w=parseJournal('5/21 home\n1x 255 static hold, 12 sec\n10x 20 db op\n20x 50 db bench')[0];expect(w.sets.map(s=>s.exercise)).toEqual(['Barbell bench press','Dumbbell overhead press','Dumbbell bench press']);expect(volume(w)).toBe(1200);expect(estimatedMax(w.sets[0])).toBe(null);});
 it('keeps failed lifts, partial reps, timestamps and unusual weights',()=>{expect(parseSet('0x 248 fail 7:45')?.reps).toBe(0);expect(estimatedMax(parseSet('0x 248 fail')!)).toBe(null);expect(parseSet('4.8x 206')?.flags).toContain('Partial repetition');expect(parseSet('4z 215 9:22')?.flags).toContain('Check set notation');expect(parseSet('6x 116')?.weight).toBe(116);});
 it('does not manufacture a valid date',()=>{expect(parseJournal('2/31 home\n3x 225')[0].date).toBe('');});
});

it('carries explicit equipment forward only within the same workout',()=>{const ws=parseJournal('10/2\n12x 50lb dumbbells\n10x 50lb\n10x 50 lb\n10/1\n3x 225');expect(ws[0].sets.every(s=>s.exercise==='Dumbbell bench press')).toBe(true);expect(ws[1].sets[0].exercise).toBe('Barbell bench press');});


describe('set timing',()=>{
 it('keeps manually entered rest distinct from completion intervals',()=>{const a={...parseSet('3x 225')!,completedAt:'2026-10-24T12:00:00Z'};const b={...parseSet('3x 225')!,completedAt:'2026-10-24T12:04:20Z',loggedAt:'2026-10-24T12:06:00Z',restBeforeSeconds:180};expect(timeBetweenSets(a,b)).toBe(260);expect(b.restBeforeSeconds).toBe(180);expect(formatDuration(260)).toBe('4:20');});
 it('does not invent intervals for imported, invalid, or out-of-order times',()=>{const a=parseSet('3x 225')!;expect(timeBetweenSets(a,a)).toBeUndefined();expect(timeBetweenSets({...a,completedAt:'2026-10-24T12:04:00Z'},{...a,completedAt:'2026-10-24T12:00:00Z'})).toBeUndefined();expect(timeBetweenSets({...a,completedAt:'invalid'},a)).toBeUndefined();});
 it('validates durations and distinguishes unspecified rest from zero',()=>{expect(parseDuration('')).toBeUndefined();expect(parseDuration('0:00')).toBe(0);expect(parseDuration('3:00')).toBe(180);expect(()=>parseDuration('3:99')).toThrow();expect(()=>parseDuration('-1:00')).toThrow();expect(()=>parseDuration('abc')).toThrow();});
});
