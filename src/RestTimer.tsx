import { useEffect, useRef, useState } from 'react';
import { formatDuration } from './domain';
type TimerState = { deadline: number | null; remaining: number; running: boolean; started: boolean };
const empty: TimerState = { deadline: null, remaining: 180, running: false, started: false };
function readTimer(): TimerState {
  try { const v = JSON.parse(localStorage.getItem('fieldwork-timer') || 'null');
    if (v && Number.isFinite(v.remaining) && v.remaining >= 0 && typeof v.running === 'boolean' && typeof v.started === 'boolean' && (v.deadline === null || Number.isFinite(v.deadline))) return v;
  } catch { /* Browser storage is optional for the timer. */ }
  return empty;
}
export function RestTimer({ trigger }: { trigger: number }) {
  const [timer, setTimer] = useState<TimerState>(readTimer);
  const [duration, setDuration] = useState(()=>localStorage.getItem('fieldwork-rest-minutes') || '3');
  const [auto, setAuto] = useState(()=>localStorage.getItem('fieldwork-rest-auto') !== 'false');
  const [sound, setSound] = useState(false), [soundError, setSoundError] = useState('');
  const [now, setNow] = useState(Date.now());
  const audio = useRef<AudioContext | null>(null), notified = useRef(false), previousTrigger = useRef(trigger);
  const remaining = timer.running && timer.deadline !== null ? (timer.deadline - now) / 1000 : timer.remaining;
  function start() { const seconds=Number(duration)*60; if(!Number.isFinite(seconds)||seconds<=0||seconds>86400)return; notified.current=false; setNow(Date.now()); setTimer({deadline:Date.now()+seconds*1000,remaining:seconds,running:true,started:true}); }
  useEffect(()=>{ const id=window.setInterval(()=>setNow(Date.now()),250); const update=()=>setNow(Date.now()); document.addEventListener('visibilitychange',update); return ()=>{clearInterval(id);document.removeEventListener('visibilitychange',update);};},[]);
  useEffect(()=>{try {localStorage.setItem('fieldwork-timer',JSON.stringify(timer));}catch{}},[timer]);
  useEffect(()=>{localStorage.setItem('fieldwork-rest-minutes',duration);},[duration]);
  useEffect(()=>{localStorage.setItem('fieldwork-rest-auto',String(auto));},[auto]);
  useEffect(()=>{if(trigger!==previousTrigger.current){previousTrigger.current=trigger;if(auto)start();}},[trigger]);
  function beep() { const ctx=audio.current;if(!ctx||ctx.state!=='running')return; for(let i=0;i<3;i++){ const osc=ctx.createOscillator(),gain=ctx.createGain();osc.connect(gain);gain.connect(ctx.destination);osc.frequency.value=880;gain.gain.value=.15;const at=ctx.currentTime+i*.35;osc.start(at);osc.stop(at+.18); } }
  useEffect(()=>{if(timer.started&&timer.running&&remaining<=0&&!notified.current){notified.current=true;if(sound)beep();}},[remaining,timer.started,timer.running,sound]);
  async function enableSound(){try{if(!audio.current)audio.current=new AudioContext();await audio.current.resume();setSound(true);setSoundError('');beep();}catch{setSoundError('Sound is unavailable in this browser.');}}
  return <section className="rest-timer" aria-label="Rest timer"><div className="section-head"><h2>Rest & recovery</h2><label className="check-label"><input type="checkbox" checked={auto} onChange={e=>setAuto(e.target.checked)}/>Auto-start after saving</label></div>
    <div className={'timer-display '+(remaining<=0&&timer.started?'complete':'')} role="timer" aria-label="Rest countdown">{timer.started&&remaining<=0?'Rest complete':formatDuration(Math.ceil(remaining))}</div>
    {timer.started&&remaining<0&&<p className="timer-over">+{formatDuration(-remaining)} over</p>}
    <div className="timer-presets">{[2,3,4,5].map(n=><button type="button" key={n} aria-pressed={duration===String(n)} onClick={()=>setDuration(String(n))}>{n} min</button>)}</div>
    <label>Rest duration (minutes)<input type="number" min="0.05" max="1440" step="0.05" value={duration} onChange={e=>setDuration(e.target.value)}/></label>
    <div className="timer-actions"><button type="button" onClick={start} disabled={!(Number(duration)>0&&Number(duration)<=1440)}>Start</button><button type="button" disabled={!timer.started||remaining<=0} onClick={()=>{if(timer.running)setTimer({...timer,deadline:null,remaining:Math.max(0,remaining),running:false});else {setNow(Date.now());setTimer({...timer,deadline:Date.now()+timer.remaining*1000,running:true});}}}>{timer.running?'Pause':'Resume'}</button><button type="button" disabled={!timer.started} onClick={()=>{notified.current=false;setNow(Date.now());setTimer({...timer,remaining:Math.max(0,remaining)+30,deadline:timer.running?Date.now()+(Math.max(0,remaining)+30)*1000:null});}}>+30 sec</button><button type="button" onClick={()=>setTimer({...empty,remaining:Number(duration)*60||180})}>Skip</button></div>
    <button type="button" className="text-button" onClick={()=>sound?setSound(false):void enableSound()}>{sound?'Sound on · turn off':'Enable sound (plays a test tone)'}</button>
    <p className="hint timer-hint">Countdown survives switching apps and reloads. Keep this app open for sound; locked-screen alerts aren’t reliable. Enable sound again after reloading.</p>{soundError&&<p role="alert">{soundError}</p>}
  </section>;
}
