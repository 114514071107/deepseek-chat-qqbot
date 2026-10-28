// Synthetic HTTP failures and delayed responses against the actual page.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict'),{chromium}=require('playwright');
const {seed}=require('../console/tests/workbench-fixture'),{createConsoleServer}=require('../console/server');
(async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-memory-failure-')),f=seed(root),token='synthetic-memory-failure-0123456789',checks=[];
 const server=createConsoleServer({dsh:root,port:0,token,lifecycle:{status:async()=>({running:false,status:'succeeded'})}});await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({httpCredentials:{username:'dsh',password:token},viewport:{width:390,height:844}}),page=await context.newPage();
  const base='http://127.0.0.1:'+server.address().port,list=await(await context.request.get(base+'/api/people')).json();
  const person=uid=>list.people.find(p=>p.sources.some(o=>o.uid===uid)).id,a=person('p1'),b=person('other'),c=person('g2');
  await page.goto(base);await page.locator('#auto-ref').uncheck();await page.locator('[data-t="memory"]').click();await page.locator('#m-uid').waitFor();
  await page.selectOption('#m-uid',a);await page.waitForFunction(()=>document.querySelector('#m-history')?.textContent.includes('SYNTHETIC-p1'));
  await page.route('**/api/people/memory?*',r=>r.fulfill({status:503,json:{ok:false,error:'synthetic 503'}}));
  await page.selectOption('#m-uid',b);await page.locator('#view [role=alert]').waitFor({timeout:2500});
  assert.equal(await page.locator('#m-uid').inputValue(),b);assert.doesNotMatch(await page.locator('#view').innerText(),/SYNTHETIC-p1/);
  assert.doesNotMatch(await page.locator('#view [role=alert]').innerText(),/自动重试/);assert.doesNotMatch(await page.locator('#hdr-status').innerText(),/自动重试/);checks.push('503 selection B never displays A and auto-off offers explicit retry');
  await page.locator('#auto-ref').check();assert.match(await page.locator('#view [role=alert]').innerText(),/自动刷新已开启/);
  await page.locator('#auto-ref').uncheck();assert.match(await page.locator('#view [role=alert]').innerText(),/自动刷新已关闭/);checks.push('changing auto refresh updates the pending error promise');
  await page.unroute('**/api/people/memory?*');await page.getByRole('button',{name:'重试',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#m-history')?.textContent.includes('SYNTHETIC-other'));checks.push('inline retry recovers B');
  let release,entered;const held=new Promise(r=>release=r),started=new Promise(r=>entered=r);let once=true;
  await page.route('**/api/people/memory?*',async r=>{if(once){once=false;const response=await r.fetch();entered();await held;await r.fulfill({response});}else await r.continue();});
  await page.selectOption('#m-uid',a);await started;await page.selectOption('#m-uid',b);await page.selectOption('#m-uid',c);
  await page.waitForFunction(()=>document.querySelector('#m-history')?.textContent.includes('SYNTHETIC-g2'));release();await page.waitForTimeout(150);
  assert.equal(await page.locator('#m-uid').inputValue(),c);assert.doesNotMatch(await page.locator('#m-history').innerText(),/SYNTHETIC-p1|SYNTHETIC-other/);checks.push('A B C out-of-order response commits C only');
  await page.unroute('**/api/people/memory?*');
  f.save('names_all.json',{g2:'长'.repeat(128)});await page.locator('#m-load').click();
  for(const width of [320,390]){await page.setViewportSize({width,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}
  await page.locator('#m-load').focus();await page.keyboard.press('Enter');await page.waitForFunction(()=>document.querySelector('#m-feedback')?.textContent==='');assert.doesNotMatch(await page.locator('#hdr-status').innerText(),/失败/);checks.push('320/390 long names reflow and keyboard refresh');
  const output=process.env.DSH_MEMORY_EVIDENCE;if(output){fs.mkdirSync(output,{recursive:true});await page.screenshot({path:path.join(output,'memory-390.png'),fullPage:true});}
  console.log(JSON.stringify({passed:checks.length,checks}));
 }finally{if(browser)await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
