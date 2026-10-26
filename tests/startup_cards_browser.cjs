const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {chromium}=require('playwright'),{createConsoleServer}=require('../console/server'),{seedTriage}=require('../console/tests/triage-fixture');
(async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-startup-cards-'));seedTriage(root);
 const token='synthetic-startup-cards-0123456789abcd',server=createConsoleServer({dsh:root,port:0,token,lifecycle:{status:async()=>({running:true,status:'succeeded'})}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({httpCredentials:{username:'dsh',password:token}}),page=await context.newPage();let snapshot,reads=0,writes=0;
  page.on('request',r=>{if(r.method()==='POST')writes++});
  await page.route('**/api/status',async route=>{if(!snapshot){const r=await route.fetch();snapshot=await r.json();}reads++;await route.fulfill({json:snapshot})});
  await page.goto('http://127.0.0.1:'+server.address().port);await page.locator('#pt-daily').waitFor();
  const cards=()=>page.getByRole('heading',{name:'能力与隐私',exact:true});assert.equal(await cards().count(),1);
  for(let i=0;i<4;i++)await page.evaluate(()=>vStatus({refresh:true,manual:true}));
  assert.equal(await cards().count(),1,'S06: unchanged cached HTML still appends duplicate privacy cards');
  await page.locator('#pt-daily').fill('321');await page.locator('#pt-daily').focus();
  await page.waitForTimeout(5600);assert.equal(await page.locator('#pt-daily').inputValue(),'321');assert.ok(await page.locator('#pt-daily').evaluate(e=>e===document.activeElement));assert.equal(await cards().count(),1);
  await page.locator('#pt-daily').fill('30');await page.locator('#view h3').first().click();
  await page.getByRole('button',{name:'记忆',exact:true}).click();await page.getByRole('button',{name:'状态',exact:true}).click();await page.locator('#pt-daily').waitFor();assert.equal(await cards().count(),1);
  assert.equal(writes,0);console.log(JSON.stringify({checks:7,status_reads:reads,posts:writes,synthetic_only:true}));
 }finally{if(browser)await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1});
