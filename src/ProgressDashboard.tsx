import { useEffect, useMemo, useRef, useState } from 'react';
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
export function localDay(now:Date):string {
 return [now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');
}
export function boundary(range:Range, now:Date):string {
 const d=new Date(now.getFullYear(),now.getMonth(),now.getDate());
 if(range==='1W')d.setDate(d.getDate()-6);
 else if(range!=='ALL'){
  const day=d.getDate();const months={ '1M':1,'3M':3,'6M':6,'1Y':12 }[range];
  d.setDate(1);d.setMonth(d.getMonth()-months);
  d.setDate(Math.min(day,new Date(d.getFullYear(),d.getMonth()+1,0).getDate()));
 }
 return localDay(d);
}
export function validDay(value:string):boolean {
 const match=/^(\d{4})-(\d{2})-(\d{2})$/.exec(value);if(!match)return false;
 const [,year,month,day]=match.map(Number);const leap=year%4===0&&(year%100!==0||year%400===0);
 return year>0&&month>=1&&month<=12&&day>=1&&day<=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31][month-1];
}
export function filterProgress(points:Point[],range:Range,now:Date):Point[]{
 if(range==='ALL')return points;
 const start=boundary(range,now),end=localDay(now);
 return points.filter(p=>p.date>=start&&p.date<=end);
}
export function formatMetric(value:number,metric:Metric):string {
 return value.toLocaleString(undefined,{maximumFractionDigits:metric==='reps'||metric==='above'?10:1});
}
export function calculateProgress(workouts:Workout[], exercise:string, threshold:number):Point[] {
 return workouts.flatMap(w=>{
  if(!validDay(w.date))return [];
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
type PlotPointProps={cx?:number;cy?:number;payload?:Point;onSelect:(point:Point)=>void;active?:boolean};
function WorkoutPoint({cx,cy,payload,onSelect,active}:PlotPointProps){
 if(cx===undefined||cy===undefined||!payload)return <g/>;
 return <circle style={{pointerEvents:'all'}} cx={cx} cy={cy} r={active?7:4} fill="#426852" stroke="white" strokeWidth={2} role="button" tabIndex={0} aria-label={`Select workout ${payload.date} ${payload.location||payload.workoutId}`} onPointerDown={()=>onSelect(payload)} onClick={()=>onSelect(payload)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(payload);}}}/>;
}
export function ProgressDashboard({workouts,exercises,onOpenWorkout}:{workouts:Workout[];exercises:string[];onOpenWorkout:(id:string)=>void}) {
 const [exercise,setExercise]=useState(exercises[0]??'Barbell bench press');
 const [range,setRange]=useState<Range>('3M');
 const [threshold,setThreshold]=useState(200);
 const [enabled,setEnabled]=useState<Metric[]>(['heaviest','estimated','volume','above']);
 const [selected,setSelected]=useState<string|null>(null);
 const selectedPanel=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(selected)selectedPanel.current?.scrollIntoView({behavior:'smooth',block:'nearest'});},[selected]);
 const points=useMemo(()=>calculateProgress(workouts,exercise,threshold),[workouts,exercise,threshold]);
 const now=new Date(),start=boundary(range,now);
 const visible=filterProgress(points,range,now);
 const selectedPoint=visible.find(p=>p.workoutId===selected);
 const toggle=(id:Metric)=>setEnabled(old=>old.includes(id)?old.filter(x=>x!==id):[...old,id]);
 const selectPoint=(point:Point)=>setSelected(point.workoutId);
 return <section className="card progress-dashboard">
  <div className="section-head"><h2>Training analysis</h2><label className="progress-exercise">Exercise<select aria-label="Exercise" value={exercise} onChange={e=>{setExercise(e.target.value);setSelected(null);}}>{exercises.map(x=><option key={x}>{x}</option>)}</select></label></div>
  <div className="progress-ranges" role="group" aria-label="Date range">{ranges.map(r=><button type="button" key={r} aria-pressed={range===r} onClick={()=>{setRange(r);setSelected(null);}}>{r}</button>)}</div>
  <div className="progress-configuration"><fieldset><legend>Graphs to show</legend><div className="metric-picker">{metrics.map(m=><label key={m.id}><input type="checkbox" checked={enabled.includes(m.id)} onChange={()=>toggle(m.id)}/>{m.title}</label>)}</div></fieldset><label className="threshold-label">Weight threshold (lb)<input type="number" min="0" max="1000" step="5" value={threshold} onChange={e=>setThreshold(Math.max(0,Math.min(1000,Number(e.target.value)||0)))}/></label></div>
  <p className="hint">Each point represents one workout. Select a point or choose a workout below, then open it in the Journal. Only known completed reps count; holds and unknown reps are excluded. Exercise names are tracked separately.</p>
  <p className="progress-coverage">{visible.length} sessions · {range==='ALL'?'All recorded dates':`Since ${start}`}</p>
  {visible.length>0&&<label className="workout-choice">Choose workout<select aria-label="Choose workout" value={selectedPoint?.workoutId??''} onChange={e=>setSelected(e.target.value||null)}><option value="">Select a session…</option>{visible.map((p,index)=><option key={p.workoutId} value={p.workoutId}>{p.date} · {p.location||'Workout'} · Session {index+1}</option>)}</select></label>}
  {selectedPoint&&<div ref={selectedPanel} className="selected-workout" aria-label="Selected workout" role="region"><h3>{selectedPoint.date} · {selectedPoint.location||'Workout'}</h3><div className="selected-metrics">{metrics.filter(m=>enabled.includes(m.id)).map(m=><span key={m.id}>{m.title}: {selectedPoint[m.id]===null?'No estimate':`${formatMetric(selectedPoint[m.id]!,m.id)} ${m.unit}`}</span>)}</div><button type="button" onClick={()=>onOpenWorkout(selectedPoint.workoutId)}>Open workout in Journal</button></div>}
  {visible.length===0?<div className="empty">No completed-repetition sets for this exercise and date range.</div>:enabled.length===0?<div className="empty">Select a graph above to view your progress.</div>:null}
  {metrics.filter(m=>enabled.includes(m.id)&&visible.length>0).map(metric=><section className="metric-chart" key={metric.id}><div className="metric-heading"><div><h3>{metric.title}</h3><p>{metric.description}</p></div><span>{metric.unit}</span></div>{visible.length>0&&!visible.some(p=>p[metric.id]!==null)?<p className="metric-no-data">No estimate from completed sets of 1–10 repetitions in this range.</p>:visible.length>0&&<div className="metric-chart-frame"><ResponsiveContainer width="100%" height="100%"><LineChart accessibilityLayer={false} data={visible} margin={{top:8,right:14,left:0,bottom:8}}><CartesianGrid vertical={false} strokeDasharray="3 3"/><XAxis dataKey="date" tick={{fontSize:10}} minTickGap={24}/><YAxis width={58} domain={['auto','auto']} tick={{fontSize:11}} tickFormatter={v=>Number(v).toLocaleString()}/><Tooltip content={({active,payload})=>{if(!active||!payload?.length)return null;const p=payload[0].payload as Point;const v=p[metric.id];return <div className="progress-tooltip"><strong>{p.date}</strong><div>{p.location||'Workout'}</div><div>{v===null?'No estimate':`${formatMetric(v,metric.id)} ${metric.unit}`}</div></div>;}}/><Line type="monotone" dataKey={metric.id} name={metric.title} stroke="#426852" strokeWidth={2.5} connectNulls={false} activeDot={false} dot={props=><WorkoutPoint {...props} active={props.payload?.workoutId===selected} onSelect={selectPoint}/>} isAnimationActive={false}/>{metric.id==='above'&&<ReferenceLine y={0} stroke="#9baa96"/>}</LineChart></ResponsiveContainer></div>}</section>)}
 </section>;
}
