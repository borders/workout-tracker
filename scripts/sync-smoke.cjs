// Run against the local PHP server with a dedicated disposable MySQL database.
const { chromium }=require('playwright');const portable=require('@sparticuz/chromium').default;const assert=require('node:assert/strict');
(async()=>{
 const url=process.env.SYNC_TEST_APP_URL||'http://127.0.0.1:8088/workouts/';assert.ok(['127.0.0.1','localhost'].includes(new URL(url).hostname),'Use a disposable local backend, never production');
 const browser=await chromium.launch({headless:true,executablePath:await portable.executablePath(),args:portable.args.filter(arg=>!['--disable-web-security','--single-process'].includes(arg)),env:{...process.env,XDG_CACHE_HOME:'/workspace/.setup/browser-cache'}});
 try{
  const a=await browser.newContext({viewport:{width:390,height:844}}),b=await browser.newContext({viewport:{width:390,height:844}});
  const pa=await a.newPage(),pb=await b.newPage();const errors=[];pa.on('pageerror',e=>errors.push(e.message));pb.on('pageerror',e=>errors.push(e.message));
  await pa.goto(url);await pa.getByText('401',{exact:true}).waitFor();
  await pa.getByRole('button',{name:'Enable server sync',exact:true}).click();await pa.getByRole('status').filter({hasText:'Synced with server'}).waitFor({timeout:120000});
  await pa.getByLabel('Set notes',{exact:true}).fill('shared set');await pa.getByRole('button',{name:'Save set',exact:true}).click();await pa.getByRole('status').filter({hasText:'Set saved'}).waitFor();
  await pa.waitForFunction(async()=>{const data=await(await fetch('./api/sync.php?action=pull&since=0')).json();return data.records.some(r=>r.kind==='workouts'&&r.document.sets.some(s=>s.notes==='shared set'));},{},{timeout:60000});
  await pb.goto(url);await pb.getByText('401',{exact:true}).waitFor();await pb.getByRole('button',{name:'Enable server sync',exact:true}).click();await pb.getByRole('status').filter({hasText:'Synced with server'}).waitFor({timeout:120000});
  await pb.getByText('1 SETS THIS SESSION',{exact:true}).waitFor();
  await b.setOffline(true);
  await pb.getByRole('button',{name:'Edit set 1',exact:true}).click();await pb.getByLabel('Set notes',{exact:true}).fill('device B offline edit');await pb.getByRole('button',{name:'Update set',exact:true}).click();await pb.getByRole('status').filter({hasText:'Set updated'}).waitFor();
  await pa.getByRole('button',{name:'Edit set 1',exact:true}).click();await pa.getByLabel('Set notes',{exact:true}).fill('device A online edit');await pa.getByRole('button',{name:'Update set',exact:true}).click();
  await pa.waitForFunction(async()=>{const data=await(await fetch('./api/sync.php?action=pull&since=0')).json();return data.records.some(r=>r.kind==='workouts'&&r.document.sets.some(s=>s.notes==='device A online edit'));},{},{timeout:60000});
  await b.setOffline(false);await pb.getByRole('status').filter({hasText:'conflict'}).waitFor({timeout:60000});
  await pb.locator('.sync-conflict summary').click();await pb.getByRole('button',{name:'Keep both',exact:true}).click();
  await pb.waitForFunction(async()=>{const data=await(await fetch('./api/sync.php?action=pull&since=0')).json();return data.records.some(r=>r.kind==='workouts'&&r.document.sets.some(s=>s.notes==='device B offline edit'));},{},{timeout:60000});
  await pa.getByRole('button',{name:'Sync now',exact:true}).click();
  await pa.waitForFunction(async()=>{const db=await new Promise(resolve=>{const q=indexedDB.open('fieldwork');q.onsuccess=()=>resolve(q.result);});return await new Promise(resolve=>{const q=db.transaction('workouts').objectStore('workouts').getAll();q.onsuccess=()=>resolve(q.result.some(w=>w.sets.some(s=>s.notes==='device B offline edit')));});},{},{timeout:60000});
  const data=await pa.evaluate(async()=>await(await fetch('./api/sync.php?action=pull&since=0')).json());
  assert.equal(data.records.filter(r=>r.kind==='imports').length,1);assert.equal(data.records.filter(r=>r.kind==='workouts').length,403);
  assert.ok(data.records.some(r=>r.kind==='workouts'&&r.document.sets.some(s=>s.notes==='device A online edit')));assert.deepEqual(errors,[]);
  console.log('PASS: two independent browsers synchronize 401 seeded sessions without duplicates, new sets transfer, offline edits conflict safely, Keep both preserves each version, and original source synchronizes');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
