const { chromium }=require('playwright');
const portable=require('@sparticuz/chromium').default;
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:await portable.executablePath(),args:portable.args});
 try{
  const page=await browser.newPage({viewport:{width:320,height:844}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.clock.install({time:new Date('2026-03-31T12:00:00Z')});
  await page.goto(process.env.APP_URL||'http://localhost:5173');
  await page.getByText('401',{exact:true}).waitFor();
  const writeFixtures=async(dense=false)=>page.evaluate(async dense=>{
   const db=await new Promise(resolve=>{const r=indexedDB.open('fieldwork');r.onsuccess=()=>resolve(r.result);});
   const tx=db.transaction(['workouts','syncState'],'readwrite');tx.objectStore('workouts').clear();tx.objectStore('syncState').clear();
   const put=(id,date,reps,weight,exercise='Barbell bench press',kind='reps')=>tx.objectStore('workouts').put({id,date,dateLabel:date,location:'fixture '+id,notes:'',raw:'',flags:[],updatedAt:new Date().toISOString(),sets:[{id:'set-'+id,exercise,reps,weight,kind,notes:'',raw:'',flags:[]}]});
   if(dense){for(let i=0;i<240;i++)put('dense-'+i,'2026-03-'+String(i%31+1).padStart(2,'0'),3,100+i%20);}
   else{put('a','2026-02-28',4.8,100);put('b','2026-03-03',2,110);put('c','2026-03-31',3,120);put('d','2026-03-31',1,130);put('future','2026-04-01',2,140);put('hold','2026-03-30',1,999,'Barbell bench press','hold');put('unknown','2026-03-30',null,999);put('zero','2026-03-30',0,999);put('invalid','2026-02-31',2,999);put('db','2026-03-31',5,75,'Dumbbell bench press');put('high-reps','2026-03-31',12,100,'Leg press');}
   await new Promise(resolve=>tx.oncomplete=resolve);
  },dense);
  const snapshot=()=>page.evaluate(async()=>{const db=await new Promise(resolve=>{const r=indexedDB.open('fieldwork');r.onsuccess=()=>resolve(r.result);});return new Promise(resolve=>{const r=db.transaction('workouts').objectStore('workouts').getAll();r.onsuccess=()=>resolve(JSON.stringify(r.result));});});
  await writeFixtures();await page.reload();const before=await snapshot();
  await page.getByRole('button',{name:'Progress',exact:true}).click();
  assert.equal(await page.locator('.metric-chart').count(),4);
  await page.getByRole('button',{name:'1M',exact:true}).click();assert.equal(await page.locator('.progress-coverage').innerText(),'4 sessions · Since 2026-02-28');
  await page.getByRole('button',{name:'1W',exact:true}).click();assert.equal(await page.locator('.progress-coverage').innerText(),'2 sessions · Since 2026-03-25');
  await page.getByRole('button',{name:'ALL',exact:true}).click();assert.equal(await page.getByLabel('Choose workout',{exact:true}).locator('option').count(),6);
  await page.getByLabel('Total repetitions',{exact:true}).check();await page.getByLabel('Weight threshold (lb)',{exact:true}).fill('100');
  await page.getByLabel('Choose workout',{exact:true}).selectOption('a');const selected=page.getByRole('region',{name:'Selected workout'});
  assert.ok((await selected.innerText()).includes('Total repetitions: 4.8 reps'));assert.ok((await selected.innerText()).includes('Reps at or above threshold: 4.8 reps'));
  await page.getByLabel('Weight threshold (lb)',{exact:true}).fill('101');assert.ok((await selected.innerText()).includes('Reps at or above threshold: 0 reps'));
  await selected.getByRole('button',{name:'Open workout in Journal'}).click();assert.equal(await page.locator('[aria-controls="sets-a"]').getAttribute('aria-expanded'),'true');
  await page.getByRole('button',{name:'Progress',exact:true}).click();await page.getByRole('button',{name:'ALL',exact:true}).click();
  const point=page.locator('.metric-chart').first().getByRole('button',{name:'Select workout 2026-02-28 fixture a',exact:true});await point.click();await selected.waitFor();
  assert.ok((await selected.innerText()).includes('fixture a'));
  const second=page.locator('.metric-chart').first().getByRole('button',{name:'Select workout 2026-03-03 fixture b',exact:true});await second.focus();await page.keyboard.press('Enter');assert.ok((await selected.innerText()).includes('fixture b'));
  await page.getByLabel('Choose workout',{exact:true}).selectOption('d');await selected.getByRole('button',{name:'Open workout in Journal'}).click();assert.equal(await page.locator('[aria-controls="sets-d"]').getAttribute('aria-expanded'),'true');
  await page.getByRole('button',{name:'Progress',exact:true}).click();await page.getByLabel('Exercise',{exact:true}).selectOption('Dumbbell bench press');assert.ok((await page.locator('.progress-coverage').innerText()).startsWith('1 sessions'));
  await page.getByLabel('Exercise',{exact:true}).selectOption('Leg press');await page.getByText('No estimate from completed sets of 1–10 repetitions in this range.').waitFor();
  await page.getByLabel('Exercise',{exact:true}).selectOption('Eagle row');await page.getByText('No completed-repetition sets for this exercise and date range.').waitFor();assert.equal(await page.locator('.metric-chart').count(),0);
  assert.equal(await snapshot(),before,'Chart interactions mutated workout data');
  await writeFixtures(true);await page.reload();await page.getByRole('button',{name:'Progress',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.progress-coverage')?.textContent?.startsWith('240 sessions'));
  assert.equal(await page.locator('.metric-chart').first().locator('circle[tabindex="0"]').count(),240);
  await page.getByLabel('Choose workout',{exact:true}).selectOption('dense-239');await selected.getByRole('button',{name:'Open workout in Journal'}).click();assert.equal(await page.locator('[aria-controls="sets-dense-239"]').getAttribute('aria-expanded'),'true');
  assert.deepEqual(errors,[]);
  console.log('PASS: calendar ranges, future/invalid-date and hold/unknown/zero-rep exclusion, fractional reps, thresholds, exercise changes, null/empty charts, mouse/keyboard/dropdown selection, same-day Journal links, 240-point dense charts, and read-only chart interactions');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
