// Existing Playwright + installed Edge, isolated root and synthetic admin replies.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {chromium}=require('playwright'),{createConsoleServer}=require('../console/server'),{seedTriage}=require('../console/tests/triage-fixture');
(async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-review-keyboard-'));seedTriage(root);
 const token='synthetic-keyboard-token-0123456789',server=createConsoleServer({dsh:root,token,port:0,lifecycle:{status:async()=>({running:false,status:'succeeded'})}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try {
  browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({httpCredentials:{username:'dsh',password:token}}),page=await context.newPage();
  const writes=[];page.on('dialog',d=>d.dismiss());
  page.on('pageerror',error=>console.error('keyboard browser script error:',String(error)));
  await page.route('**/api/switch',async route=>{writes.push(route.request().postDataJSON());await route.fulfill({json:{ok:true}})});
  await page.route('**/api/user',async route=>{writes.push(route.request().postDataJSON());await route.fulfill({json:{ok:true}})});
  await page.goto('http://127.0.0.1:'+server.address().port);await page.locator('#pt-daily').waitFor();await page.locator('#auto-ref').uncheck();
  await page.locator('#auto-ref').focus();let found=false;
  for(let i=0;i<30;i++){await page.keyboard.press('Tab');if(await page.locator('#ms-toggle').evaluate(e=>document.activeElement===e)){found=true;break}}
  assert.ok(found,'Tab must reach visible master switch');
  assert.ok(await page.locator('#ms-toggle').getAttribute('aria-label'));
  const before=await page.locator('#ms-toggle').isChecked();await page.keyboard.press('Space');await page.waitForTimeout(150);
  assert.equal(await page.locator('#ms-toggle').isChecked(),!before);assert.deepEqual(writes,[{key:'enabled',value:!before}]);
  const controls=await page.locator('.tg input').evaluateAll(es=>es.map(e=>({disabled:e.disabled,name:e.getAttribute('aria-label')||e.labels?.[0]?.textContent.trim(),display:getComputedStyle(e).display})));
  assert.ok(controls.every(c=>c.name&&c.display!=='none'));
  for(const key of ['harvest','kimi'])assert.ok(await page.locator('input[data-k="'+key+'"]').isDisabled());
  await page.getByRole('button',{name:'用户',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#people-range')?.textContent.includes('本页'));
  await page.locator('#people-operations summary').click();
  const source=page.locator('#people-source');const options=await source.locator('option').evaluateAll(es=>es.map(e=>e.value).filter(Boolean));
  if(options.length){await source.selectOption(options[0]);const cb=page.locator('input[data-scope="user"][data-k="reply"]');await cb.waitFor();const uid=await cb.getAttribute('data-uid');await cb.focus();await page.keyboard.press('Space');await page.waitForTimeout(150);assert.equal(writes.at(-1).uid,uid);assert.equal(writes.filter(w=>w.uid).length,1);
   await page.getByRole('button',{name:'私聊',exact:true}).click().catch(()=>{});await page.waitForTimeout(150);assert.equal(writes.filter(w=>w.uid).length,1);}
  console.log(JSON.stringify({checks:7,writes,controls:controls.length,synthetic_only:true}));
 } finally {if(browser)await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1});
