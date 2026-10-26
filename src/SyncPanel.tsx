import { useEffect, useState } from 'react';
import { localStore, type SyncState, type Document } from './db';
import { sync, type SyncReport } from './sync';
import type { Workout as WorkoutDocument } from './domain';
// Conflict views are plain text; original versions remain in local backups.
function describe(doc:Document|null){if(!doc)return 'Deleted on this device/server';if('sets' in doc){const w=doc as WorkoutDocument;return `${w.dateLabel} · ${w.location}\n${w.sets.map(s=>`${s.reps??'?'} × ${s.weight} ${s.exercise} · ${[s.details?.pause,s.details?.buttFlat?'Butt flat':'',s.details?.feetUp?'Feet up':'',s.details?.difficulty,s.notes].filter(Boolean).join(' · ')}`).join('\n')}\n${w.notes}\nSession context: ${JSON.stringify(w.context??{})}\nCompleted times / entered rest: ${JSON.stringify(w.sets.map(s=>({completedAt:s.completedAt,restBeforeSeconds:s.restBeforeSeconds})))}`;}return doc.text;}
export function SyncPanel({onChanged}:{onChanged:()=>Promise<void>}){
 const [enabled,setEnabled]=useState(()=>localStorage.getItem('fieldwork-sync-enabled')==='true');
 const [report,setReport]=useState<SyncReport>(sync.getReport),[conflicts,setConflicts]=useState<SyncState[]>([]),[docs,setDocs]=useState<Map<string,Document>>(new Map()),[error,setError]=useState('');
 useEffect(()=>sync.subscribe(r=>{setReport(r);if(r.phase==='idle'||r.phase==='error'){void refresh();}}),[]);
 async function refresh(){try{setConflicts((await localStore.states()).filter(s=>s.conflict));const exported=await localStore.exportData();setDocs(new Map([...exported.workouts,...exported.imports].map(d=>[d.id,d])));await onChanged();}catch(e){setError(String(e));}}
 useEffect(()=>{
   localStorage.setItem('fieldwork-sync-enabled',String(enabled));if(!enabled)return;
   let queued:ReturnType<typeof setTimeout>|undefined;
   const run=()=>{void sync.run();};const changed=()=>{clearTimeout(queued);queued=setTimeout(run,800);};
   const visible=()=>{if(document.visibilityState==='visible')run();};
   window.addEventListener('fieldwork-change',changed);window.addEventListener('online',run);document.addEventListener('visibilitychange',visible);
   const interval=setInterval(run,30000);run();return()=>{clearTimeout(queued);clearInterval(interval);window.removeEventListener('fieldwork-change',changed);window.removeEventListener('online',run);document.removeEventListener('visibilitychange',visible);};
 },[enabled]);
 async function resolve(key:string,choice:'local'|'server'|'both'){setError('');try{await localStore.resolveConflict(key,choice);await refresh();if(enabled)void sync.run();}catch(e){setError(String(e));}}
 return <section className="sync-panel" aria-label="Server synchronization"><div className="section-head"><div><h2>Server sync</h2><p className="sync-message" role="status">{enabled?report.message:'Off · saved only in this browser'}</p>{enabled&&report.lastSync&&<p className="hint">Last completed sync: {new Date(report.lastSync).toLocaleString()}</p>}</div><div className="sync-buttons"><button type="button" onClick={()=>setEnabled(!enabled)}>{enabled?'Pause sync':'Enable server sync'}</button>{enabled&&<button type="button" disabled={report.phase==='syncing'} onClick={()=>void sync.run()}>Sync now</button>}</div></div><p className="hint">Offline edits stay on this device until synced. Export a backup before syncing an existing browser for the first time.</p>{enabled&&report.pending>0&&<p className="sync-message">{report.pending} pending record(s)</p>}{error&&<p role="alert">{error}</p>}
 {conflicts.map(state=><details className="sync-conflict" key={state.key}><summary>Review conflict: {state.kind==='workouts'?(docs.get(state.id) as WorkoutDocument|undefined)?.dateLabel??state.id:'Original journal source'}</summary><p>Both versions are preserved. Keep both to retain the local version as a separate copy and adopt the server version.</p><div className="conflict-columns"><div><h3>This device</h3><pre>{describe(docs.get(state.id)??null)}</pre></div><div><h3>Server</h3><pre>{describe(state.conflict!.document)}</pre></div></div><div className="sync-buttons"><button type="button" onClick={()=>void resolve(state.key,'both')}>Keep both</button><button type="button" onClick={()=>void resolve(state.key,'local')}>Use this device</button><button type="button" onClick={()=>void resolve(state.key,'server')}>Use server</button></div></details>)}
 </section>;
}
