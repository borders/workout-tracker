const { chromium } = require('playwright');
const portable = require('@sparticuz/chromium').default;
const assert = require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:await portable.executablePath(),args:portable.args});
 try {
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.APP_URL || 'http://localhost:5173');
  await page.getByRole('status').filter({hasText:'Loaded 401 sessions'}).waitFor();
  const inspect=()=>page.evaluate(async()=>{const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('fieldwork');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});const tx=db.transaction(['workouts','imports']);const read=store=>new Promise((resolve,reject)=>{const r=tx.objectStore(store).getAll();r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});return {workouts:await read('workouts'),imports:await read('imports')};});
  let data=await inspect();
  assert.equal(data.workouts.length,401);
  assert.equal(data.workouts.reduce((n,w)=>n+w.sets.length,0),2854);
  assert.equal(data.imports.length,1);
  assert.ok(data.imports[0].text.startsWith('Bench'));
  assert.ok(data.imports[0].text.includes('- [ ]'));
  const pr=data.workouts.find(w=>w.date==='2026-04-22');
  assert.ok(pr.sets.some(s=>s.weight===275 && s.reps===1 && s.notes.includes('PR')));
  assert.equal(data.workouts.filter(w=>!w.date).length,2);
  await page.getByPlaceholder('Search notes, exercise, location…').fill('2026-04-22');
  assert.equal(await page.locator('article.workout').count(),1);
  await page.getByRole('button',{name:'Edit 2026-04-22',exact:true}).click();
  await page.getByRole('button',{name:'Remove set 8',exact:true}).click();
  await page.waitForFunction(async()=>{const db=await new Promise(resolve=>{const r=indexedDB.open('fieldwork');r.onsuccess=()=>resolve(r.result);});return await new Promise(resolve=>{const r=db.transaction('workouts').objectStore('workouts').getAll();r.onsuccess=()=>resolve(r.result.find(w=>w.date==='2026-04-22').sets.length===7);});});
  await page.reload();
  await page.getByText('401', {exact:true}).waitFor();
  data=await inspect();
  assert.equal(data.workouts.length,401);
  assert.equal(data.workouts.find(w=>w.date==='2026-04-22').sets.length,7);
  assert.equal(data.imports.length,1);
  await page.getByRole('button',{name:'Progress',exact:true}).click();
  await page.locator('.recharts-line').waitFor();
  assert.deepEqual(errors,[]);
  console.log('PASS: 401 journal sessions, 2854 sets, original source, PR, unknown dates, chart, reload deduplication, and preservation of edits');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
