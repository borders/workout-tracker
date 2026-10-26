import { openDB } from 'idb';
import type { Workout, JournalImport } from './domain';
export type Kind = 'workouts' | 'imports';
export type Document = Workout | JournalImport;
export type RemoteRecord = { kind: Kind; id: string; revision: number; deleted: boolean; document: Document | null };
export type SyncState = { key: string; kind: Kind; id: string; revision: number; dirty: boolean; mutation: string; deleted: boolean; conflict?: RemoteRecord };
export type Operation = { operationId: string; kind: Kind; id: string; baseRevision: number; deleted: boolean; document: Document | null };
const keyOf = (kind: Kind, id: string) => `${kind}/${id}`;
// Imported set IDs were generated independently on older devices. Compare their
// contents, retaining all notes, attributes, ordering, and deletions.
export function sameDocument(kind: Kind, a: Document | null, b: Document | null): boolean {
  function canonical(doc: Document | null) {
    if (doc === null) return null;
    const copy = structuredClone(doc) as unknown as Record<string, unknown>;
    delete copy[kind === 'workouts' ? 'updatedAt' : 'importedAt'];
    if (kind === 'workouts' && String(copy.id).startsWith('import-') && Array.isArray(copy.sets)) {
      copy.sets = copy.sets.map(s => { const c = { ...s }; delete c.id; return c; });
    }
    return JSON.stringify(copy, function(_key, value) {
      return value && typeof value === 'object' && !Array.isArray(value)
        ? Object.fromEntries(Object.keys(value).sort().map(k => [k, value[k]])) : value;
    });
  }
  return canonical(a) === canonical(b);
}
export function createLocalStore(name = 'fieldwork') {
  const db = openDB(name, 2, { upgrade(d) {
    if (!d.objectStoreNames.contains('workouts')) d.createObjectStore('workouts', { keyPath: 'id' });
    if (!d.objectStoreNames.contains('imports')) d.createObjectStore('imports', { keyPath: 'id' });
    if (!d.objectStoreNames.contains('syncState')) d.createObjectStore('syncState', { keyPath: 'key' });
    if (!d.objectStoreNames.contains('syncMeta')) d.createObjectStore('syncMeta');
  }});
  const stateFor = (kind: Kind, id: string, old?: SyncState): SyncState => ({ key: keyOf(kind,id),kind,id,revision:old?.revision??0,dirty:true,mutation:crypto.randomUUID(),deleted:false,...(old?.conflict?{conflict:old.conflict}:{}) });
  async function initialize() {
    const tx=(await db).transaction(['workouts','imports','syncState'],'readwrite');
    for (const kind of ['workouts','imports'] as Kind[]) {
      for (const doc of await tx.objectStore(kind).getAll()) {
        const key=keyOf(kind,doc.id);
        if (!await tx.objectStore('syncState').get(key)) await tx.objectStore('syncState').put(stateFor(kind,doc.id));
      }
    }
    await tx.done;
  }
  async function saveWorkout(w: Workout) {
    const tx=(await db).transaction(['workouts','syncState'],'readwrite');
    await tx.objectStore('workouts').put(w);
    const old=await tx.objectStore('syncState').get(keyOf('workouts',w.id));
    await tx.objectStore('syncState').put(stateFor('workouts',w.id,old));await tx.done;
    windowChanged();
  }
  async function importBatch(ws: Workout[], source: JournalImport, once: boolean) {
    const tx=(await db).transaction(['workouts','imports','syncState'],'readwrite');
    if (once && (await tx.objectStore('imports').get(source.id) || (await tx.objectStore('syncState').get(keyOf('imports',source.id)))?.deleted)) {await tx.done;return 0;}
    let added=0;
    for(const w of ws)if(!await tx.objectStore('workouts').get(w.id) && !(await tx.objectStore('syncState').get(keyOf('workouts',w.id)))?.deleted){
      await tx.objectStore('workouts').put(w);await tx.objectStore('syncState').put(stateFor('workouts',w.id));added++;
    }
    if(!await tx.objectStore('imports').get(source.id)){
      await tx.objectStore('imports').put(source);await tx.objectStore('syncState').put(stateFor('imports',source.id));
    }
    await tx.done;windowChanged();return added;
  }
  async function pending(): Promise<Operation[]> {
    await initialize();
    const tx=(await db).transaction(['workouts','imports','syncState']);const result: Operation[]=[];
    for(const s of await tx.objectStore('syncState').getAll() as SyncState[]) if(s.dirty&&!s.conflict){
      const document=s.deleted?null:await tx.objectStore(s.kind).get(s.id);
      result.push({operationId:s.mutation,kind:s.kind,id:s.id,baseRevision:s.revision,deleted:s.deleted,document});
    }
    await tx.done;return result;
  }
  async function receive(record: RemoteRecord, ack?: Operation) {
    const tx=(await db).transaction([record.kind,'syncState'],'readwrite');
    const key=keyOf(record.kind,record.id);const store=tx.objectStore(record.kind);
    const local=await store.get(record.id) as Document | undefined;
    const state=await tx.objectStore('syncState').get(key) as SyncState | undefined;
    // Never let an older replay or pull response roll revisions backward.
    if(state && (state.revision>record.revision || (state.conflict?.revision??0)>record.revision)){await tx.done;return;}
    if(ack && state?.mutation!==ack.operationId){
      // A local edit happened during upload. Its base now includes our accepted upload.
      if(state)await tx.objectStore('syncState').put({...state,revision:record.revision});
    } else if(!state?.dirty || (ack && state?.mutation===ack.operationId) ||
        ((!record.deleted && local && sameDocument(record.kind,local,record.document)) || (record.deleted && !local))) {
      if(record.deleted)await store.delete(record.id);else await store.put(record.document);
      await tx.objectStore('syncState').put({key,kind:record.kind,id:record.id,revision:record.revision,dirty:false,mutation:state?.mutation??crypto.randomUUID(),deleted:record.deleted});
    } else if(record.revision!==state.revision || state.conflict){
      await tx.objectStore('syncState').put({...state,conflict:record});
    }
    await tx.done;
  }
  async function acceptConflict(record: RemoteRecord, operation: Operation) {
    // If equal, reconciliation is safe even when another device uploaded first.
    const tx=(await db).transaction([record.kind,'syncState'],'readwrite');
    const state=await tx.objectStore('syncState').get(keyOf(record.kind,record.id)) as SyncState;
    const local=state.deleted?null:await tx.objectStore(record.kind).get(record.id);
    if(state.revision>record.revision || (state.conflict?.revision??0)>record.revision){await tx.done;return;}
    if(state.mutation===operation.operationId && state.deleted===record.deleted && sameDocument(record.kind,local??null,record.document)){
      if(record.deleted)await tx.objectStore(record.kind).delete(record.id);else await tx.objectStore(record.kind).put(record.document);
      await tx.objectStore('syncState').put({...state,revision:record.revision,dirty:false,conflict:undefined});
    }else await tx.objectStore('syncState').put({...state,conflict:record});
    await tx.done;
  }
  async function resolveConflict(key: string, choice: 'local'|'server'|'both') {
    const d=await db;const tx=d.transaction(['workouts','imports','syncState'],'readwrite');
    const state=await tx.objectStore('syncState').get(key) as SyncState;const remote=state?.conflict;
    if(!remote)throw new Error('This conflict has already been resolved.');
    const local=await tx.objectStore(state.kind).get(state.id) as Document|undefined;
    if(choice==='both' && local && !state.deleted){
      const copy={...local,id:crypto.randomUUID()} as Document;
      if(state.kind==='workouts') (copy as Workout).notes=`${(copy as Workout).notes}\nCopy retained during sync conflict resolution.`.trim();
      await tx.objectStore(state.kind).put(copy);await tx.objectStore('syncState').put(stateFor(state.kind,copy.id));
    }
    if(choice==='local')await tx.objectStore('syncState').put({...state,revision:remote.revision,dirty:true,mutation:crypto.randomUUID(),conflict:undefined});
    else{
      if(remote.deleted)await tx.objectStore(state.kind).delete(state.id);else await tx.objectStore(state.kind).put(remote.document);
      await tx.objectStore('syncState').put({...state,revision:remote.revision,dirty:false,deleted:remote.deleted,conflict:undefined});
    }
    await tx.done;windowChanged();
  }
  return { db, initialize, saveWorkout, pending, receive, acceptConflict, resolveConflict,
    allWorkouts:async():Promise<Workout[]> => (await db).getAll('workouts'),
    importWorkouts:(ws:Workout[],source:JournalImport)=>importBatch(ws,source,false),
    importWorkoutsOnce:(ws:Workout[],source:JournalImport)=>importBatch(ws,source,true),
    states:async():Promise<SyncState[]> => {await initialize();return(await db).getAll('syncState');},
    meta:async<T>(key:string):Promise<T|undefined> => (await db).get('syncMeta',key),
    setMeta:async(key:string,value:unknown)=>{await(await db).put('syncMeta',value,key);},
    exportData:async()=>{const d=await db;const tx=d.transaction(['workouts','imports','syncState','syncMeta']);return {version:2,exportedAt:new Date().toISOString(),workouts:await tx.objectStore('workouts').getAll(),imports:await tx.objectStore('imports').getAll(),syncState:await tx.objectStore('syncState').getAll()};},
    close:async()=>{(await db).close();},
  };
}
function windowChanged(){if(typeof window!=='undefined')window.dispatchEvent(new Event('fieldwork-change'));}
export const localStore=createLocalStore();
export const {allWorkouts,saveWorkout,importWorkouts,importWorkoutsOnce,exportData}=localStore;
export type LocalStore=ReturnType<typeof createLocalStore>;
