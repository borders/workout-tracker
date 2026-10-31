import { describe, expect, it } from 'vitest';
import { calculateProgress } from './ProgressDashboard';
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
  expect(point.estimated).toBeCloseTo(235*(1+3/30));
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
