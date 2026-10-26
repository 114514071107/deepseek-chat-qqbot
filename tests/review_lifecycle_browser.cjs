const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {chromium}=require('playwright'),{createConsoleServer}=require('../console/server'),{seedTriage}=require('../console/tests/triage-fixture');
(async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-life-browser-'));seedTriage(root);
 const token='synthetic-life-token-0123456789abcd',server=createConsoleServer({dsh:root,port:0,token,lifecycle:{status:async()=>({running:false,status:'succeeded'})}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({httpCredentials:{username:'dsh',password:token}}),page=await context.newPage();let pending=true,writes=0,changed=false,timers=0;
  page.on('dialog',d=>d.accept());
  await page.route('**/api/bot',async route=>{writes++;await route.fulfill({json:{id:'c'.repeat(32),status:'pending',ok:false,accepted:true}})});
  await page.route('**/api/lifecycle?*',async route=>route.fulfill({json:pending?{id:'c'.repeat(32),status:'running',ok:false}:{id:'c'.repeat(32),status:'failed',ok:false,error:'Synthetic AccessDenied'}}));
  await page.route('**/api/status',async route=>{const response=await route.fetch();const json=await response.json();if(changed){json.bot_running=true;timers++;}else{json.bot_running=false;json.bot_state={status:'unknown',running:null};}await route.fulfill({json})});
  await page.goto('http://127.0.0.1:'+server.address().port);await page.locator('#bot-start').waitFor();assert.equal(await page.locator('.stat .vl').first().innerText(),'状态未知');await page.locator('#bot-start').click();await page.locator('#view h3').first().click();
  await page.waitForFunction(()=>{const e=document.querySelector('#bot-saved');return e&&e.textContent.includes('进行中')&&Number(getComputedStyle(e).opacity)>0;});
  assert.ok(await page.locator('#bot-saved').evaluate(e=>Number(getComputedStyle(e).opacity)>0),'operation state must be visible');
  changed=true;await page.waitForTimeout(5600);assert.ok(timers>0,'actual automatic status refresh required');
  assert.ok(await page.locator('#bot-restart').isDisabled(),'new DOM must preserve in-flight state');assert.equal(writes,1);
  pending=false;await page.waitForFunction(()=>document.querySelector('#bot-saved')?.textContent.includes('Synthetic AccessDenied'));
  assert.ok(await page.locator('#bot-saved').evaluate(e=>Number(getComputedStyle(e).opacity)>0));
  await page.getByRole('button',{name:'记忆',exact:true}).click();await page.getByRole('button',{name:'状态',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#bot-saved')?.textContent.includes('Synthetic AccessDenied'));assert.equal(writes,1);
  console.log(JSON.stringify({checks:5,actual_timer_refreshes:timers,management_posts:writes,synthetic_only:true}));
 }finally{if(browser)await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1});
