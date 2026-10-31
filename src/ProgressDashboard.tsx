import { useMemo, useState } from 'react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine } from 'recharts';
import { estimatedMax, type Workout } from './domain';

export type Metric = 'heaviest'|'estimated'|'volume'|'reps'|'above'|'averageRep'|'averageSet';
const metrics: {id:Metric; title:string; unit:string; description:string}[] = [
 {id:'heaviest',title:'Heaviest lift',unit:'lb',description:'Highest weight in a completed-repetition set'},
 {id:'estimated',title:'Estimated 1RM',unit:'lb',description:'Best Epley estimate from sets of 1–10 repetitions'},
 {id:'volume',title:'Workout volume',unit:'lb · reps',description:'Sum of weight × repetitions'},
 {id:'reps',title:'Total repetitions',unit:'reps',description:'All known completed repetitions'},
 {id:'above',title:'Reps at or above threshold',unit:'reps',description:'Number of reps at or above the selected weight'},
 {id:'averageRep',title:'Average weight per rep',unit:'lb',description:'Total volume divided by total repetitions'},
 {id:'averageSet',title:'Average weight per set',unit:'lb',description:'Mean weight across completed-repetition sets'},
];
const ranges = ['1W','1M','3M','6M','1Y','ALL'] as const;
type Range = typeof ranges[number];
type Point = {date:string; workoutId:string; location:string; heaviest:number|null; estimated:number|null; volume:number; reps:number; above:number; averageRep:number|null; averageSet:number|null};
function boundary(range:Range, now:Date):string {
 const d = new Date(now.getFullYear(),now.getMonth(),now.getDate());
 if(range==='1W')d.setDate(d.getDate()-6);
 if(range==='1M')d.setMonth(d.getMonth()-1);
 if(range==='3M')d.setMonth(d.getMonth()-3);
 if(range==='6M')d.setMonth(d.getMonth()-6);
 if(range==='1Y')d.setFullYear(d.getFullYear()-1);
 return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
}
export function calculateProgress(workouts:Workout[], exercise:string, threshold:number):Point[] {
 return workouts.flatMap(w=>{
  if(!/^\d{4}-\d{2}-\d{2}$/.test(w.date))return [];
  const sets=w.sets.filter(s=>s.exercise===exercise&&s.kind==='reps'&&s.reps!==null&&Number.isFinite(s.reps)&&s.reps>0&&Number.isFinite(s.weight));
  if(!sets.length)return [];
  const reps=sets.reduce((n,s)=>n+s.reps!,0);
  const volume=sets.reduce((n,s)=>n+s.weight*s.reps!,0);
  const estimates=sets.map(estimatedMax).filter((n):n is number=>n!==null);
  return [{date:w.date,workoutId:w.id,location:w.location,
   heaviest:Math.max(...sets.map(s=>s.weight)),
   estimated:estimates.length?Math.max(...estimates):null,
   volume,reps,above:sets.filter(s=>s.weight>=threshold).reduce((n,s)=>n+s.reps!,0),
   averageRep:reps?volume/reps:null,averageSet:sets.reduce((n,s)=>n+s.weight,0)/sets.length}];
 }).sort((a,b)=>a.date.localeCompare(b.date)||a.workoutId.localeCompare(b.workoutId));
}
export function ProgressDashboard({workouts,exercises,onOpenWorkout}:{workouts:Workout[];exercises:string[];onOpenWorkout:(id:string)=>void}) {
 const [exercise,setExercise]=useState(exercises[0]??'Barbell bench press');
 const [range,setRange]=useState<Range>('3M');
 const [threshold,setThreshold]=useState(200);
 const [enabled,setEnabled]=useState<Metric[]>(['heaviest','estimated','volume','above']);
 const points=useMemo(()=>calculateProgress(workouts,exercise,threshold),[workouts,exercise,threshold]);
 const start=boundary(range,new Date());
 const visible=range==='ALL'?points:points.filter(p=>p.date>=start);
 const toggle=(id:Metric)=>setEnabled(old=>old.includes(id)?old.filter(x=>x!==id):[...old,id]);
 const format=(v:number,metric:Metric)=>metric==='reps'||metric==='above'?Math.round(v).toLocaleString():v.toLocaleString(undefined,{maximumFractionDigits:1});
 return <section className="card progress-dashboard">
  <div className="section-head"><h2>Training analysis</h2><label className="progress-exercise">Exercise<select aria-label="Exercise" value={exercise} onChange={e=>setExercise(e.target.value)}>{exercises.map(x=><option key={x}>{x}</option>)}</select></label></div>
  <div className="progress-ranges" role="group" aria-label="Date range">{ranges.map(r=><button type="button" key={r} aria-pressed={range===r} onClick={()=>setRange(r)}>{r}</button>)}</div>
  <div className="progress-configuration"><fieldset><legend>Graphs to show</legend><div className="metric-picker">{metrics.map(m=><label key={m.id}><input type="checkbox" checked={enabled.includes(m.id)} onChange={()=>toggle(m.id)}/>{m.title}</label>)}</div></fieldset><label className="threshold-label">Weight threshold (lb)<input type="number" min="0" max="1000" step="5" value={threshold} onChange={e=>setThreshold(Math.max(0,Math.min(1000,Number(e.target.value)||0)))}/></label></div>
  <p className="hint">Each point represents one workout. Tap a point or its detail link to open the Journal. Only known completed reps count; holds and unknown reps are excluded. Exercise names are tracked separately.</p>
  <p className="progress-coverage">{visible.length} sessions · {range==='ALL'?'All recorded dates':`Since ${start}`}</p>
  {visible.length===0?<div className="empty">No completed-repetition sets for this exercise and date range.</div>:enabled.length===0?<div className="empty">Select a graph above to view your progress.</div>:null}
  {metrics.filter(m=>enabled.includes(m.id)).map(metric=><section className="metric-chart" key={metric.id}><div className="metric-heading"><div><h3>{metric.title}</h3><p>{metric.description}</p></div><span>{metric.unit}</span></div>{visible.length>0&&<div className="metric-chart-frame"><ResponsiveContainer width="100%" height="100%"><LineChart data={visible} margin={{top:8,right:14,left:0,bottom:8}}><CartesianGrid vertical={false} strokeDasharray="3 3"/><XAxis dataKey="date" tick={{fontSize:10}} minTickGap={24}/><YAxis width={58} domain={['auto','auto']} tick={{fontSize:11}} tickFormatter={v=>Number(v).toLocaleString()}/><Tooltip content={({active,payload})=>{if(!active||!payload?.length)return null;const p=payload[0].payload as Point;const v=p[metric.id];return <div className="progress-tooltip"><strong>{p.date}</strong><div>{p.location||'Workout'}</div><div>{v===null?'No estimate':`${format(v,metric.id)} ${metric.unit}`}</div><button type="button" onClick={()=>onOpenWorkout(p.workoutId)}>Open workout →</button></div>;}}/><Line type="monotone" dataKey={metric.id} name={metric.title} stroke="#426852" strokeWidth={2.5} connectNulls={false} activeDot={{r:7,onClick:(_e:any,event:any)=>{const p=event?.payload as Point|undefined;if(p?.workoutId)onOpenWorkout(p.workoutId);}}} dot={{r:3}} isAnimationActive={false}/>{metric.id==='above'&&<ReferenceLine y={0} stroke="#9baa96"/>}</LineChart></ResponsiveContainer></div>}</section>)}
 </section>;
}
