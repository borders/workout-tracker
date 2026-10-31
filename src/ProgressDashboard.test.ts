import { describe, expect, it } from 'vitest';
import { calculateProgress, boundary, filterProgress, formatMetric, validDay, localDay } from './ProgressDashboard';
import type { Workout } from './domain';
const workout=(id:string,date:string,sets:Array<{exercise:string;weight:number;reps:number|null;kind?:'hold'|'reps'}>):Workout=>({
 id,date,dateLabel:date,location:'Hampton',notes:'',raw:'',flags:[],updatedAt:'2026-10-30',
 sets:sets.map((s,i)=>({id:id+'-'+i,exercise:s.exercise,weight:s.weight,reps:s.reps,kind:s.kind??'reps',notes:'',raw:'',flags:[]})),
});
describe('progress per workout',()=>{
 it('counts reps, weighted volume, averages, and threshold inclusively',()=>{
  const [point]=calculateProgress([workout('w','2026-10-01',[
   {exercise:'Barbell bench press',weight:45,reps:10},
   {exercise:'Barbell bench press',weight:225,reps:5},
   {exercise:'Barbell bench press',weight:235,reps:3},
   {exercise:'Dumbbell bench press',weight:75,reps:10},
  ])],'Barbell bench press',225);
  expect(point.reps).toBe(18);
  expect(point.above).toBe(8);
  expect(point.volume).toBe(2280);
  expect(point.heaviest).toBe(235);
  expect(point.averageRep).toBeCloseTo(2280/18);
  expect(point.averageSet).toBeCloseTo((45+225+235)/3);
  expect(point.estimated).toBeCloseTo(225*(1+5/30));
 });
 it('excludes unknown reps and holds, and leaves non-Epley sessions without estimate',()=>{
  const p=calculateProgress([workout('w','2026-10-01',[
   {exercise:'Barbell bench press',weight:250,reps:null},
   {exercise:'Barbell bench press',weight:270,reps:1,kind:'hold'},
   {exercise:'Barbell bench press',weight:100,reps:12},
  ])],'Barbell bench press',100);
  expect(p[0].reps).toBe(12);
  expect(p[0].estimated).toBeNull();
  expect(p[0].above).toBe(12);
 });
 it('retains same-day workouts as separate points and sorts them',()=>{
  const p=calculateProgress([workout('b','2026-10-02',[{exercise:'Barbell bench press',weight:200,reps:2}]),workout('a','2026-10-01',[{exercise:'Barbell bench press',weight:150,reps:2}]),workout('c','2026-10-02',[{exercise:'Barbell bench press',weight:175,reps:2}])],'Barbell bench press',200);
  expect(p.map(x=>x.workoutId)).toEqual(['a','b','c']);
 });
});


describe('calendar ranges and precision',()=>{
 it('clamps month ends and leap years',()=>{expect(boundary('1M',new Date(2026,2,31))).toBe('2026-02-28');expect(boundary('1M',new Date(2024,2,31))).toBe('2024-02-29');expect(boundary('3M',new Date(2026,4,31))).toBe('2026-02-28');expect(boundary('6M',new Date(2026,7,31))).toBe('2026-02-28');expect(boundary('1Y',new Date(2024,1,29))).toBe('2023-02-28');});
 it('has inclusive local date boundaries and excludes future dates except ALL',()=>{const now=new Date(2026,2,31,23,30);const dates=['2026-02-27','2026-02-28','2026-03-24','2026-03-25','2026-03-31','2026-04-01'];const points=calculateProgress(dates.map(date=>workout(date,date,[{exercise:'bench',weight:100,reps:1}])),'bench',100);expect(filterProgress(points,'1W',now).map(p=>p.date)).toEqual(['2026-03-25','2026-03-31']);expect(filterProgress(points,'1M',now).map(p=>p.date)).toEqual(dates.slice(1,-1));expect(filterProgress(points,'ALL',now)).toHaveLength(6);});
 it('retains partial reps in calculations and display',()=>{const [point]=calculateProgress([workout('partial','2026-03-31',[{exercise:'bench',weight:100,reps:4.8}])],'bench',100);expect(point.reps).toBe(4.8);expect(point.above).toBe(4.8);expect(point.volume).toBe(480);expect(formatMetric(point.reps,'reps')).toBe((4.8).toLocaleString());expect(formatMetric(point.above,'above')).toBe((4.8).toLocaleString());});
 it('rejects nonexistent dates',()=>{expect(validDay('2026-02-29')).toBe(false);expect(validDay('2024-02-29')).toBe(true);expect(validDay('2026-04-31')).toBe(false);expect(validDay('2026-00-12')).toBe(false);});
});

it('bounds every quick range on both ends, including all same-day sessions',()=>{const now=new Date(2026,9,31,9);for(const range of ['1W','1M','3M','6M','1Y'] as const){const start=boundary(range,now);const before=new Date(start+'T12:00:00');before.setDate(before.getDate()-1);const dates=[localDay(before),start,'2026-10-31','2026-10-31','2026-11-01'];const points=calculateProgress(dates.map((date,i)=>workout(String(i),date,[{exercise:'bench',weight:100,reps:1}])),'bench',100);expect(filterProgress(points,range,now).map(p=>p.workoutId)).toEqual(['1','2','3']);}});
