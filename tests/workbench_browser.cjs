// Uses the existing bundled Playwright and installed Edge; no browser download.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require('playwright');
const {createConsoleServer}=require('../console/server');
const {seed}=require('../console/tests/workbench-fixture');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-workbench-browser-')),f=seed(root);
  const original=fs.readFileSync(path.join(f.data,'history_v2.json'),'utf8');
  const token='fixture-token-for-workbench-12345678',server=createConsoleServer({dsh:root,token,port:0});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  let browser;const checks=[];
  const evidence=process.env.DSH_BROWSER_EVIDENCE||path.resolve(__dirname,'../docs/reviews/evidence');fs.mkdirSync(evidence,{recursive:true});
  try{
    browser=await chromium.launch({channel:'msedge',headless:true});
    const context=await browser.newContext({httpCredentials:{username:'dsh',password:token},viewport:{width:1280,height:960}});
    const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));page.on('dialog',d=>d.accept());
    const base='http://127.0.0.1:'+server.address().port;
    const catalog=async()=>(await context.request.get(base+'/api/people')).json();
    const person=async uid=>(await catalog()).people.find(p=>p.sources.some(s=>s.uid===uid));
    const settled=()=>page.waitForFunction(()=>document.querySelector('#people-range')?.textContent.includes('本页'));
    const choose=async uid=>{const p=await person(uid);await page.locator('[data-person="'+p.id+'"]').click();await settled();return p;};
    await page.goto(base);await page.waitForLoadState('networkidle');await page.locator('#auto-ref').uncheck();
    await page.getByRole('button',{name:'用户',exact:true}).click();await page.waitForLoadState('networkidle');
    await page.locator('.uchip').first().waitFor();await settled();
    assert.equal(await page.locator('.uchip').count(),5);checks.push('separate unconfirmed origins; no name-based merge');
    await choose('p1');assert.equal(await page.locator('[data-ptadd]').count(),0);
    for(const uid of ['g1','g2']){
      await page.getByText('来源与人工关联',{exact:true}).click();
      await page.locator('#people-associate').selectOption((await person(uid)).id);
      await page.locator('#people-link').click();await page.waitForLoadState('networkidle');
      await page.waitForFunction(n=>document.querySelectorAll('.uchip').length===n,uid==='g1'?4:3);
    }
    const joined=await person('p1');assert.equal(joined.sources.length,3);checks.push('UI confirmation links private plus two groups into one entry');
    await page.getByRole('button',{name:'群聊',exact:true}).click();await page.locator('#people-group').waitFor();await page.waitForLoadState('networkidle');
    assert.equal(await page.locator('#people-history .msg').count(),4);
    let history=await page.locator('#people-history').innerText();assert.ok(history.includes('group-one')&&history.includes('group-two'));
    assert.ok(!history.includes('OTHER-MEMBER-SECRET')&&!history.includes('UNBOUND-ASSISTANT'));
    await page.screenshot({path:path.join(evidence,'2026-10-25-users-groups.png'),fullPage:true});
    await page.locator('#people-group').selectOption('group-one');await settled();assert.equal(await page.locator('#people-history .msg').count(),2);
    checks.push('group and specific-group filtering preserve speaker/source; unrelated replies absent');
    let releaseGroup,enterGroup;const groupHeld=new Promise(r=>releaseGroup=r),groupStarted=new Promise(r=>enterGroup=r);
    await page.route('**/api/people/history?**',async route=>{const u=new URL(route.request().url());
      if(u.searchParams.get('group')==='group-one'){
        enterGroup();await groupHeld;try{await route.fulfill({json:{ok:true,entries:[{role:'user',text:'STALE-GROUP-SENTINEL',ts:1}],count:1,source_count:1,next_offset:null}});}catch(_){}
      }else await route.continue();});
    await page.locator('#people-group').selectOption('group-two');await settled();
    await page.locator('#people-group').selectOption('group-one');await groupStarted;
    assert.match(await page.locator('#people-history').innerText(),/正在加载/);
    await page.locator('#people-group').selectOption('group-two');await settled();releaseGroup();await sleep(100);
    assert.ok((await page.locator('#people-history').innerText()).includes('SYNTHETIC-g2'));
    assert.ok(!(await page.locator('#people-history').innerText()).includes('STALE-GROUP-SENTINEL'));
    await page.unroute('**/api/people/history?**');checks.push('loading clears old rows; delayed specific-group response cannot replace another group');
    await page.getByRole('button',{name:'私聊',exact:true}).click();await settled();
    assert.equal(await page.locator('#people-history .msg').count(),2);assert.equal(await page.locator('#people-history img').count(),1);
    await page.screenshot({path:path.join(evidence,'2026-10-25-users-desktop.png'),fullPage:true});
    checks.push('private projection and authenticated image rendering');
    // A slow private response must not survive selecting another person.
    let release,entered;const blocked=new Promise(r=>release=r),started=new Promise(r=>entered=r);
    await page.route('**/api/people/history?**',async route=>{
      const u=new URL(route.request().url());
      if(u.searchParams.get('person')===joined.id&&u.searchParams.get('mode')==='private'){
        entered();await blocked;try{await route.fulfill({json:{ok:true,entries:[{role:'user',text:'STALE-PRIVATE-SENTINEL',ts:1}],count:1,source_count:1,next_offset:null}});}catch(_){}
      }else await route.continue();
    });
    await page.getByRole('button',{name:'群聊',exact:true}).click();await settled();
    await page.getByRole('button',{name:'私聊',exact:true}).click();await started;
    await choose('other');release();await sleep(150);
    history=await page.locator('#people-history').innerText();assert.ok(history.includes('SYNTHETIC-other'));assert.ok(!history.includes('STALE-PRIVATE-SENTINEL'));
    await page.unroute('**/api/people/history?**');checks.push('out-of-order private response cannot replace a new person');
    await page.getByRole('button',{name:'群聊',exact:true}).click();await settled();
    assert.match(await page.locator('#people-history').innerText(),/没有所选场景/);checks.push('empty mode is explicit');
    await page.route('**/api/people/history?**',route=>route.fulfill({status:503,json:{ok:false,error:'SYNTHETIC-READ-FAILURE'}}));
    await page.getByRole('button',{name:'私聊',exact:true}).click();await page.locator('#people-history-retry').waitFor();
    assert.match(await page.locator('#people-history').innerText(),/加载失败/);await page.unroute('**/api/people/history?**');
    await page.locator('#people-history-retry').click();await page.locator('#people-history .msg').first().waitFor();checks.push('read error and retry recover without old private content');
    await choose('p1');await page.getByText('来源与人工关联',{exact:true}).click();
    await page.locator('#people-unlink-source').selectOption('g2');await page.locator('#people-unlink').click();await page.waitForLoadState('networkidle');
    assert.equal((await catalog()).total,4);assert.equal((await person('p1')).sources.length,2);checks.push('UI unlink detaches one origin without rewriting records');
    await choose('p1');await page.getByText('管理具体来源',{exact:true}).click();
    assert.equal(await page.locator('[data-ptadd]').count(),0);
    await page.route('**/api/history?uid=g1&limit=150',route=>route.fulfill({status:503,json:{ok:false,error:'SYNTHETIC-SOURCE-FAILURE'}}));
    await page.locator('#people-source').selectOption('g1');
    assert.match(await page.locator('#people-operation-source').innerText(),/qq_official.*fixture-bot.*member-A-1.*g1/);
    await page.getByText('所选来源记录加载失败：SYNTHETIC-SOURCE-FAILURE。可点刷新重试。',{exact:true}).waitFor();
    await page.unroute('**/api/history?uid=g1&limit=150');await page.locator('#h-load').click();await page.locator('#h-list .msg').first().waitFor();
    checks.push('explicit source history errors are visible and its refresh recovers');
    await page.locator('[data-ptadd="10"]').waitFor();let mutation;
    await page.route('**/api/points',async route=>{mutation=route.request().postDataJSON();await route.fulfill({json:{ok:true}});});
    await page.locator('[data-ptadd="10"]').click();await settled();assert.equal(mutation.uid,'g1');
    assert.equal(page.locator('#people-source')&&await page.locator('#people-source').inputValue(),'g1');checks.push('explicit operation source survives refresh; points request targets only original g1');
    const deletion=[];
    await page.route('**/api/delete/preview',route=>route.fulfill({json:{ok:true,mapping:{rolling:'所选来源滚动记录'},backups:[],backup_impact:'合成测试，无备份'}}));
    await page.route('**/api/history/clear',async route=>{deletion.push(route.request().postDataJSON());await route.fulfill({json:{ok:true}});});
    await page.locator('#people-operations summary').click();await page.locator('#h-clear').click();
    await page.locator('[data-delete-layer="rolling"]').check();await page.locator('#delete-apply').click();
    await page.waitForFunction(()=>document.querySelector('#delete-result')?.textContent.includes('处理完成'));
    assert.equal(deletion[0].uid,'g1');assert.deepEqual(deletion[0].layers,['rolling']);checks.push('delete requires explicit g1 and selected data layer; aggregate not expanded');
    await choose('p1');await page.getByRole('button',{name:'群聊',exact:true}).focus();await page.keyboard.press('Enter');
    await settled();assert.equal(await page.getByRole('button',{name:'群聊',exact:true}).getAttribute('aria-pressed'),'true');
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(evidence,'2026-10-25-users-mobile.png'),fullPage:true});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));checks.push('keyboard scene switch; 390px view has no horizontal page overflow');
    await choose('legacy');assert.match(await page.locator('#people-history').innerText(),/LEGACY-ONLY/);checks.push('legacy retains a separate inspectable entry');
    for(let n=0;n<105;n++)f.scopes['extra'+n]={...f.scopes.p1,sender:'extra-'+n};
    f.scopes['deep-target']={...f.scopes.p1,sender:'deep-target'};f.save('scopes_v2.json',f.scopes);
    const secondPage=await (await context.request.get(base+'/api/people?limit=100&offset=100')).json();
    const outside=secondPage.people.at(-1),outsideUid=outside.sources[0].uid;
    assert.ok(!(await catalog()).people.some(p=>p.id===outside.id));
    await page.locator('#btn-ref').click();await page.locator('.uchip').first().waitFor();await choose('p1');
    await page.getByText('来源与人工关联',{exact:true}).click();await page.locator('#people-link-search').fill(outsideUid);
    await page.locator('#people-link-find').click();await page.waitForFunction(()=>document.querySelector('#people-associate')?.options.length===2);
    await page.locator('#people-associate').selectOption(outside.id);
    await page.locator('#people-link').click();await settled();assert.equal((await person('p1')).sources.length,3);
    checks.push('association search finds an origin beyond the first 100-entry list page');
    await page.route('**/api/people?limit=100&offset=0',route=>route.fulfill({status:503,json:{ok:false,error:'SYNTHETIC-LIST-FAILURE'}}));
    await page.locator('#btn-ref').click();await page.locator('#people-retry').waitFor();assert.equal(await page.locator('.msg').count(),0);
    await page.unroute('**/api/people?limit=100&offset=0');await page.locator('#people-retry').click();await settled();
    checks.push('list failure clears private content and explicit retry restores current data');
    await page.route('**/api/people?limit=100&offset=0',route=>route.fulfill({json:{ok:true,people:[],total:0,scope_count:0,revision:'fixture-empty',next_offset:null}}));
    await page.locator('#btn-ref').click();await page.getByText('暂无用户来源。收到并保存消息后再刷新。',{exact:true}).waitFor();
    await page.unroute('**/api/people?limit=100&offset=0');checks.push('empty catalog has a clear next step');
    assert.equal(fs.readFileSync(path.join(f.data,'history_v2.json'),'utf8'),original);assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(evidence,'2026-10-25-users-browser.json'),JSON.stringify({date:'2026-10-25',browser:'installed Edge / bundled Playwright',synthetic_only:true,checks,js_errors:errors,history_unchanged:true},null,2));
    console.log(JSON.stringify({passed:checks.length,checks,js_errors:errors}));
  }finally{if(browser)await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
