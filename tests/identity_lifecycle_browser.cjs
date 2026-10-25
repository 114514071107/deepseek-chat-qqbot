const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require('playwright'),{createConsoleServer}=require('../console/server'),{seedTriage}=require('../console/tests/triage-fixture');
(async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-legacy-browser-')),f=seedTriage(root),checks=[];
 f.histories.oldPrivate=[{id:'old-private',role:'user',text:'RECOVERED PRIVATE',ts:1,source:f.scopes.pA}];
 f.histories.mixed=[{id:'mix-group',role:'user',text:'RECOVERED MIXED GROUP',ts:2,source:f.scopes.gC},{id:'mix-unknown',role:'user',text:'STILL UNKNOWN',ts:3}];
 f.histories.botOnly=[{id:'bot-only',role:'assistant',text:'OUTBOUND ARCHIVE PRESERVED',ts:4,source:{...f.scopes.gC,group:'unmatched-group',sender:'unmatched-source'}}];
 const receiptSource={...f.scopes.gA,message_id:''},receiptProvenance={scope_key:'oldReceipt',source:receiptSource,target:{platform:receiptSource.platform,instance:receiptSource.instance,bot:receiptSource.bot,kind:'group',address:receiptSource.group},mode:'proactive',trigger:'proactive',request_id:'',job_id:'recovered-original-job'};
 f.histories.oldReceipt=[{id:'receipt-only',role:'assistant',text:'RECEIPT RECOVERED BOT',ts:5,delivery:{status:'accepted',message_id:'recovered-platform-id',attempt_id:'recovered-attempt'}}];f.flush();
 f.histories.knownMixed=[{id:'known-p',role:'user',text:'KNOWN MIXED PRIVATE',ts:6,source:f.scopes.pC},{id:'known-g',role:'user',text:'KNOWN MIXED GROUP',ts:7,source:f.scopes.gF}];f.flush();
 f.save('delivery_receipts_v2.json',{oldReceipt:[{attempt_id:'recovered-attempt',status:'accepted',message_id:'recovered-platform-id',provenance:receiptProvenance}]});
 const token='synthetic-identity-lifecycle-token-1234567890',server=createConsoleServer({dsh:root,port:0,token});await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({httpCredentials:{username:'dsh',password:token},viewport:{width:1280,height:900}}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  const base='http://127.0.0.1:'+server.address().port,catalog=async()=>(await context.request.get(base+'/api/people')).json();
  const choose=async uid=>{const p=(await catalog()).people.find(p=>p.sources.some(o=>o.uid===uid));await page.locator('[data-person="'+p.id+'"]').click();await page.waitForFunction(()=>document.querySelector('#people-range')?.textContent.includes('本页'));return p;};
  await page.goto(base);await page.locator('#auto-ref').uncheck();await page.getByRole('button',{name:'用户',exact:true}).click();await choose('gF');
  await page.locator('#people-associations summary').click();await page.locator('#people-confirm').click();await page.locator('#people-review-confirm').click();
  await page.waitForFunction(()=>document.querySelector('#people-status')?.textContent.includes('人工已确认'),{timeout:5000});checks.push('successful standalone decision repaints immediately with current revision');
  await page.locator('#people-associations summary').click();await page.locator('#people-unlink').click();await page.locator('#people-review-confirm').click();await page.waitForFunction(()=>document.querySelector('#people-status')?.textContent.includes('待人工确认'));checks.push('successive decision uses new revision and revokes confirmation');
  await choose('oldPrivate');assert.match(await page.locator('#people-history').innerText(),/RECOVERED PRIVATE/);assert.match(await page.locator('#people-status').innerText(),/待人工确认/);
  await page.locator('#people-associations summary').click();assert.match(await page.locator('#people-associations').innerText(),/场景识别：已识别/);assert.match(await page.locator('#people-associations').innerText(),/逐条 record.source/);
  assert.equal(await page.locator('#people-source option[value="oldPrivate"]').count(),0);checks.push('old private scene is readable while person stays pending and management stays disabled');
  const group=(await catalog()).people.flatMap(p=>p.sources).find(o=>o.original_uid==='mixed'&&o.kind==='group');await choose(group.uid);await page.getByRole('button',{name:'群聊',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#people-history')?.textContent.includes('RECOVERED MIXED GROUP'));
  assert.doesNotMatch(await page.locator('#people-history').innerText(),/STILL UNKNOWN/);await choose('mixed');assert.match(await page.locator('#people-history').innerText(),/STILL UNKNOWN/);assert.doesNotMatch(await page.locator('#people-history').innerText(),/RECOVERED MIXED GROUP/);checks.push('mixed records retain separate known group and unknown scene views');
  await page.locator('#people-outbound-archives summary').click();await page.locator('[data-outbound="botOnly"]').click();await page.getByText('OUTBOUND ARCHIVE PRESERVED',{exact:false}).waitFor();
  assert.match(await page.locator('#people-outbound-records').innerText(),/投递状态未留存/);assert.ok(!(await catalog()).people.some(p=>p.sources.some(o=>o.original_uid==='botOnly')));checks.push('assistant-only unmatched archive is inspectable without generating a user or claiming delivery success');
  const before=(await catalog()).counts;await choose('pA');await page.getByRole('button',{name:'群聊',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#people-history')?.textContent.includes('RECEIPT RECOVERED BOT'));
  assert.match(await page.locator('#people-history').innerText(),/历史来源依据：.*回执/);assert.match(await page.locator('#people-history').innerText(),/recovered-original-job/);assert.deepEqual((await catalog()).counts,before);checks.push('reliable frozen receipt joins the existing group as assistant with original job and no new source');
  await page.locator('#people-archive-indexes summary').click();assert.match(await page.locator('#people-archive-indexes').innerText(),/knownMixed/);assert.ok(!(await catalog()).metadata.some(m=>m.uid==='knownMixed'));checks.push('fully known mixed file has a separate index and never masquerades as no-chat settings');
  assert.deepEqual(errors,[]);checks.push('no JavaScript errors');console.log(JSON.stringify({passed:checks.length,checks}));
 }finally{if(browser)await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
