import { localStore, type LocalStore, type Operation, type RemoteRecord } from './db';
export type SyncReport={ phase:'idle'|'syncing'|'offline'|'error'; message:string; pending:number; conflicts:number; lastSync?:string };
export function createSync(store:LocalStore, endpoint:string, request:typeof fetch=fetch){
 let current:Promise<SyncReport>|undefined;
 let report:SyncReport={phase:'idle',message:'Not synced yet',pending:0,conflicts:0};
 const listeners=new Set<(r:SyncReport)=>void>();
 function emit(r:SyncReport){report=r;listeners.forEach(fn=>fn(r));}
 async function api(action:string,body?:unknown,csrf?:string){
   const response=await request(`${endpoint}?action=${action}`,{method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',headers:body?{'Content-Type':'application/json','X-CSRF-Token':csrf!}:{},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(30000)});
   let value;try{value=await response.json();}catch{throw new Error('Sync API unavailable. Deploy the PHP backend and configure its database.');}
   if(!response.ok)throw new Error(value.error??`Sync failed (${response.status})`);
   return value;
 }
 async function work():Promise<SyncReport>{
   if(typeof navigator!=='undefined'&&navigator.onLine===false){const states=await store.states();emit({...report,phase:'offline',message:'Offline · changes stay on this device',pending:states.filter(s=>s.dirty&&!s.conflict).length,conflicts:states.filter(s=>s.conflict).length});return report;}
   emit({...report,phase:'syncing',message:'Syncing…'});
   try{
     await store.initialize();
     const hello=await api('handshake');
     const existing=await store.meta<string>('serverInstance');
     if(existing&&existing!==hello.instance)throw new Error('Server database identity changed. Export a backup before reconnecting; sync is paused.');
     await store.setMeta('serverInstance',hello.instance);
     async function pull(){let cursor=await store.meta<number>('cursor')??0;for(;;){const page=await api(`pull&since=${cursor}`);for(const record of page.records as RemoteRecord[])await store.receive(record);if(page.cursor<cursor)throw new Error('Server revision moved backward; sync is paused.');cursor=page.cursor;await store.setMeta('cursor',cursor);if(!page.more)break;}}
     await pull();
     // Snapshot immutable operations; edits during a request remain queued for next sync.
     const operations=await store.pending();
     while(operations.length){
       const batch:Operation[]=[];let size=0;
       while(operations.length&&batch.length<25){const n=JSON.stringify(operations[0]).length;if(batch.length&&size+n>2000000)break;size+=n;batch.push(operations.shift()!);}
       const result=await api('push',{operations:batch},hello.csrf);
       for(let i=0;i<batch.length;i++){const item=result.results[i];if(!item)throw new Error('Incomplete sync response; retry safely.');if(item.conflict)await store.acceptConflict(item.record,batch[i]);else await store.receive(item.record,batch[i]);}
     }
     await pull();
     const states=await store.states();const pending=states.filter(s=>s.dirty&&!s.conflict).length,conflicts=states.filter(s=>s.conflict).length;
     const lastSync=new Date().toISOString();await store.setMeta('lastSync',lastSync);
     emit({phase:'idle',message:conflicts?`${conflicts} conflict${conflicts===1?'':'s'} need review`:pending?'New changes queued':'Synced with server',pending,conflicts,lastSync});
   }catch(e){const states=await store.states();emit({...report,phase:'error',message:e instanceof Error?e.message:'Sync failed; local changes are preserved',pending:states.filter(s=>s.dirty).length,conflicts:states.filter(s=>s.conflict).length});}
   return report;
 }
 return {run(){if(!current){const task=async()=>work();current=(typeof navigator!=='undefined'&&navigator.locks?navigator.locks.request('fieldwork-sync',task):task()).finally(()=>{current=undefined;});}return current;},subscribe(fn:(r:SyncReport)=>void){listeners.add(fn);fn(report);return()=>{listeners.delete(fn);};},getReport:()=>report};
}
export const sync=createSync(localStore,`${import.meta.env.BASE_URL}api/sync.php`);
