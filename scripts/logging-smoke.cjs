const { chromium } = require('playwright');
const portable = require('@sparticuz/chromium').default;
const assert = require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:await portable.executablePath(),args:portable.args});
 try {
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.clock.install({time:new Date('2026-10-24T12:00:00Z')});
  await page.goto(process.env.APP_URL || 'http://localhost:5173');
  await page.getByText('401',{exact:true}).waitFor();
  await page.clock.pauseAt(new Date('2026-10-24T12:01:00Z'));
  const read=()=>page.evaluate(async()=>{const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('fieldwork');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});return new Promise(resolve=>{const r=db.transaction('workouts').objectStore('workouts').getAll();r.onsuccess=()=>resolve(r.result);});});
  const label=name=>page.getByLabel(name,{exact:true});
  await label('Reps').fill('3');await label('Weight (lb)').fill('225');
  await label('Pause').selectOption('Long paused');await label('Butt stayed flat').check();await label('Feet up').check();
  await label('Difficulty').selectOption('Near failure');await label('Set notes').fill('Last rep barely moved');
  await page.getByText('Session context · weight, sleep & fueling',{exact:true}).click();
  await label('Body weight').fill('185.5');await label('Sleep hours').fill('6.5');await label('Sleep quality').selectOption('Fair');await label('How well did you fuel today?').selectOption('Adequately');await label('Readiness').selectOption('Low');await label('Session notes').fill('Shoulder sore');
  await page.getByRole('button',{name:'Save set',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Set saved'}).waitFor();
  let ws=await read();let w=ws.find(w=>!w.id.startsWith('import-'));assert.equal(w.sets.length,1);
  assert.equal(w.context.bodyWeight,185.5);assert.equal(w.context.sleepHours,6.5);assert.equal(w.notes,'Shoulder sore');
  assert.deepEqual(w.sets[0].details,{pause:'Long paused',buttFlat:true,feetUp:true,difficulty:'Near failure'});assert.ok(w.sets[0].loggedAt);assert.ok(w.sets[0].completedAt);const loggedAt=w.sets[0].loggedAt;
  assert.equal(await label('Difficulty').inputValue(),'');assert.equal(await label('Set notes').inputValue(),'');assert.equal(await label('Pause').inputValue(),'Long paused');assert.equal(await label('Weight (lb)').inputValue(),'225');
  await page.clock.fastForward(60000);
  assert.equal(await page.getByRole('timer').innerText(),'2:00');
  await page.getByRole('button',{name:'Pause',exact:true}).click();await page.clock.fastForward(30000);assert.equal(await page.getByRole('timer').innerText(),'2:00');
  await page.getByRole('button',{name:'+30 sec',exact:true}).click();assert.equal(await page.getByRole('timer').innerText(),'2:30');
  await page.getByRole('button',{name:'Resume',exact:true}).click();await page.clock.fastForward(30000);await page.reload();await page.getByText('1 SETS THIS SESSION').waitFor();assert.equal(await page.getByRole('timer').innerText(),'2:00');
  await page.getByRole('button',{name:'Enable sound (plays a test tone)'}).click();await page.getByRole('button',{name:'Sound on · turn off'}).waitFor();
  await page.clock.fastForward(125000);await page.getByText('Rest complete',{exact:true}).waitFor();assert.ok((await page.locator('.timer-over').innerText()).includes('0:05'));
  await page.getByRole('button',{name:'Edit set 1',exact:true}).click();
  await page.getByText('Timing · adjust if you logged late',{exact:true}).click();
  await label('Completed at').fill('2026-10-24T11:58');await label('Rest before this set (m:ss)').fill('2:30');
  await page.getByRole('button',{name:'Update set',exact:true}).click();await page.getByRole('status').filter({hasText:'Set updated'}).waitFor();
  ws=await read();w=ws.find(w=>!w.id.startsWith('import-'));assert.equal(w.sets[0].loggedAt,loggedAt);assert.equal(w.sets[0].restBeforeSeconds,150);assert.equal(w.sets[0].completedAt,'2026-10-24T11:58:00.000Z');
  await label('Completed at').fill('2026-10-24T12:03');await label('Rest before this set (m:ss)').fill('3:00');await label('Reps').fill('2');await label('Difficulty').selectOption('Failed attempt');
  await page.getByRole('button',{name:'Save set',exact:true}).click();await page.getByRole('status').filter({hasText:'Set saved'}).waitFor();
  await page.getByText('Time between sets: 5:00',{exact:true}).waitFor();await page.getByText('Rest before set: 3:00 (entered)',{exact:true}).waitFor();
  // Invalid duration must not add a record.
  await label('Rest before this set (m:ss)').fill('2:99');await page.getByRole('button',{name:'Save set',exact:true}).click();await page.getByRole('alert').filter({hasText:'minutes:seconds'}).waitFor();
  ws=await read();assert.equal(ws.find(w=>!w.id.startsWith('import-')).sets.length,2);
  // Context changes are explicitly savable without adding a set.
  if(!await label('Body weight').isVisible())await page.getByText('Session context · weight, sleep & fueling',{exact:true}).click();
  await label('Body weight').fill('186');await page.getByRole('button',{name:'Save session context',exact:true}).click();await page.getByRole('status').filter({hasText:'Session context saved'}).waitFor();
  await page.reload();await page.getByText('2 SETS THIS SESSION').waitFor();
  await page.getByText('Session context · weight, sleep & fueling',{exact:true}).click();assert.equal(await label('Body weight').inputValue(),'186');
  await label('Date').fill('2026-10-25');assert.equal(await label('Body weight').inputValue(),'');assert.equal(await label('Sleep hours').inputValue(),'');
  assert.deepEqual(errors,[]);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:'/workspace/workout-tracker/logging-smoke.png',fullPage:true});
  console.log('PASS: structured entry, defaults, session context persistence/reset, timer start/pause/extend/resume/expiry/reload, sound activation, timestamp edits, separate rest, validation, and mobile layout');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
