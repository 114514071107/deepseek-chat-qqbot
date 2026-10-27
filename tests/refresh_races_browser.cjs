// Delayed real timer requests and synthetic committed admin results, never production.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require('playwright'),{createConsoleServer}=require('../console/server'),{seedTriage}=require('../console/tests/triage-fixture');
(async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-refresh-races-')),f=seedTriage(root),token='synthetic-refresh-races-token-1234567890',checks=[];
 f.save('thoughts_v2.json',{pA:[{text:'THOUGHT-A',t:1},{text:'THOUGHT-B',t:2}]});
 const server=createConsoleServer({dsh:root,port:0,token});await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({httpCredentials:{username:'dsh',password:token}}),page=await context.newPage();
  const base='http://127.0.0.1:'+server.address().port;
  const catalog=await (await context.request.get(base+'/api/people')).json(),personA=catalog.people.find(p=>p.sources.some(s=>s.uid==='pA'));
  page.on('dialog',d=>d.accept());
  await page.goto(base);await page.locator('#auto-ref').uncheck();await page.getByRole('button',{name:'记忆',exact:true}).click();await page.locator('#m-uid').selectOption(personA.id);await page.getByText('THOUGHT-B',{exact:false}).waitFor();
  let release,entered;const held=new Promise(r=>release=r),started=new Promise(r=>entered=r);let block=true;
  await page.route('**/api/people/memory?*',async route=>{if(block){block=false;const response=await route.fetch();entered();await held;await route.fulfill({response});}else await route.continue();});
  await page.route('**/api/thought/del',async route=>{assert.equal(route.request().postDataJSON().index,1);assert.equal(route.request().postDataJSON().uid,'pA');f.save('thoughts_v2.json',{pA:[{text:'THOUGHT-A',t:1}]});await route.fulfill({json:{ok:true}});});
  await page.locator('#auto-ref').check();await page.locator('#view h3').first().click();await Promise.race([started,new Promise((_,reject)=>setTimeout(()=>reject(Error('timer did not start')),8000))]);
  await page.getByText('THOUGHT-B',{exact:false}).locator('..').getByRole('button',{name:'删',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#view')?.textContent.includes('THOUGHT-B'));
  release();await page.waitForTimeout(400);assert.doesNotMatch(await page.locator('#view').innerText(),/THOUGHT-B/,'late timer resurrected deleted thought');assert.equal(await page.locator('[data-memory-delete]').count(),1);checks.push('late timer cannot overwrite committed delete or restore stale action indices');
  await page.locator('#auto-ref').uncheck();await page.getByRole('button',{name:'用户',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#people-range')?.textContent.includes('本页'));
  let fail,enteredPeople;const failedGate=new Promise(r=>fail=r),peopleStarted=new Promise(r=>enteredPeople=r);let holdPeople=true;
  await page.route('**/api/people?*',async route=>{if(holdPeople){holdPeople=false;enteredPeople();await failedGate;await route.fulfill({status:503,json:{ok:false,error:'synthetic temporary error'}});}else await route.continue();});
  await page.locator('#auto-ref').check();await page.locator('#people-detail h3').click();await Promise.race([peopleStarted,new Promise((_,reject)=>setTimeout(()=>reject(Error('people timer did not start')),8000))]);
  await page.locator('#people-search').fill('KEEP DRAFT ON FAILED REFRESH');fail();await page.waitForTimeout(300);
  assert.equal(await page.locator('#people-search').inputValue(),'KEEP DRAFT ON FAILED REFRESH');assert.equal(await page.locator('#people-search').evaluate(e=>e===document.activeElement),true);checks.push('failed timer preserves draft, focus and live controls');
  await page.locator('#people-search').fill('');await page.getByRole('button',{name:'查找用户',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#people-range')?.textContent.includes('本页'));
  let failHistory,historyEntered;const historyGate=new Promise(r=>failHistory=r),historyStarted=new Promise(r=>historyEntered=r);let holdHistory=true;
  await page.route('**/api/people/history*',async route=>{if(holdHistory){holdHistory=false;historyEntered();await historyGate;await route.fulfill({status:503,json:{ok:false,error:'synthetic history failure'}});}else await route.continue();});
  await page.locator('#people-detail h3').click();await Promise.race([historyStarted,new Promise((_,reject)=>setTimeout(()=>reject(Error('history timer did not start')),8000))]);
  const mapping=fs.readFileSync(path.join(f.data,'console_people_v1.json'),'utf8');await page.locator('#people-associations summary').click();await page.locator('#people-associate').selectOption({index:1});await page.locator('#people-link').click();failHistory();await page.waitForTimeout(300);
  assert.equal(await page.locator('#people-review').count(),1);await page.keyboard.press('Escape');assert.equal(fs.readFileSync(path.join(f.data,'console_people_v1.json'),'utf8'),mapping);assert.equal(await page.locator('#people-associate').count(),1);checks.push('failed in-flight history refresh preserves a newly opened confirmation and cancel context');
  console.log(JSON.stringify({passed:checks.length,checks}));
 }finally{if(browser)await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
