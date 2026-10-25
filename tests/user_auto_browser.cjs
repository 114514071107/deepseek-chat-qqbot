// Isolated synthetic service only. Existing Playwright and installed Edge.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require('playwright'),{createConsoleServer}=require('../console/server'),{seed}=require('../console/tests/workbench-fixture');
(async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-auto-browser-')),f=seed(root),token='synthetic-auto-browser-token-12345';
  const profiles={version:1,sources:{}};
  function qq(uid,at=20,name='合成平台用户名'){
    profiles.sources[uid]={source:f.scopes[uid],app:'fixture-app',observed_at:at,message_id:'fixture-profile',
      identity:{namespace:'qq_user_openid',value:'private-A',basis:f.scopes[uid].private?'qq_author_user':'qq_author_pair'},
      nickname:{value:name,kind:'platform_name',source:'qq.author.username',at,message_id:'fixture-profile'}};
  }
  for(const uid of ['p1','g1','g2'])qq(uid,uid==='g2'?30:20);
  for(const [uid,group] of [['n1',''],['n2','onebot-fixture-group']]){
    const s=f.scopes[uid]={platform:'aiocqhttp',instance:'fixture-onebot',bot:'654321',sender:'123456',group,private:!group,message_id:'synthetic-msg'};
    f.histories[uid]=[{role:'user',text:'ONEBOT-SYNTHETIC',ts:30,request_id:'synthetic-request',source:s}];
    profiles.sources[uid]={source:s,app:'654321',observed_at:40,message_id:'profile',
      identity:{namespace:'onebot_qq',value:'123456',basis:'onebot_message_sender'},
      nickname:{value:'<img src=x onerror="window.__profileXss=1">新昵称',kind:'qq_nickname',source:'onebot.sender.nickname',at:40,message_id:'profile'},
      group_card:group?{value:'合成群名片',kind:'group_card',source:'onebot.sender.card',at:40,message_id:'profile'}:null};
  }
  f.save('scopes_v2.json',f.scopes);f.save('history_v2.json',f.histories);f.save('workbench_profiles_v1.json',profiles);
  const original=fs.readFileSync(path.join(f.data,'history_v2.json'),'utf8');
  const server=createConsoleServer({dsh:root,port:0,token});await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const evidence=process.env.DSH_AUTO_BROWSER_EVIDENCE||path.resolve(__dirname,'../docs/reviews/evidence/2026-10-25-user-auto');fs.mkdirSync(evidence,{recursive:true});
  let browser;const checks=[];
  try{
    browser=await chromium.launch({channel:'msedge',headless:true});
    const context=await browser.newContext({httpCredentials:{username:'dsh',password:token},viewport:{width:1280,height:960}}),page=await context.newPage(),errors=[];
    page.on('pageerror',e=>errors.push(String(e)));page.on('dialog',d=>d.accept());
    const base='http://127.0.0.1:'+server.address().port;
    const catalog=async()=>(await context.request.get(base+'/api/people')).json();
    const person=async uid=>(await catalog()).people.find(p=>p.sources.some(s=>s.uid===uid));
    const settled=()=>page.waitForFunction(()=>document.querySelector('#people-range')?.textContent.includes('本页'));
    const confirmReview=async()=>{await page.locator('#people-review-confirm').click();await page.waitForFunction(()=>!document.querySelector('#people-review')&&(!document.querySelector('#people-associations')?.open||document.querySelector('#people-link-result')?.textContent));};
    const choose=async uid=>{const p=await person(uid);await page.locator('[data-person="'+p.id+'"]').click();await settled();return p;};
    await page.goto(base);await page.waitForLoadState('networkidle');await page.locator('#auto-ref').uncheck();
    await page.getByRole('button',{name:'用户',exact:true}).click();await settled();
    assert.equal(await page.locator('.uchip').count(),4);await choose('p1');
    assert.match(await page.locator('#people-status').innerText(),/自动确认/);assert.equal((await person('p1')).sources.length,3);
    checks.push('trusted raw-author mapping automatically joins private plus two groups with visible basis');
    const prior=(await person('p1')).id;f.scopes.g3={...f.scopes.g1,group:'group-three',sender:'member-A-3'};qq('g3');
    f.save('scopes_v2.json',f.scopes);f.save('workbench_profiles_v1.json',profiles);await page.locator('#btn-ref').click();await settled();
    assert.equal((await person('p1')).id,prior);assert.equal((await person('p1')).sources.length,4);
    checks.push('later trustworthy origin enters the existing stable automatic entry');
    await choose('other');assert.match(await page.locator('#people-status').innerText(),/待人工确认.*昵称未获取/);
    checks.push('same-note stranger remains separate, pending and honestly missing a nickname');
    await choose('n1');assert.match(await page.locator('#people-status').innerText(),/QQ 昵称/);
    assert.equal(await page.locator('.uchip img').count(),0);assert.equal(await page.evaluate(()=>window.__profileXss),undefined);
    assert.match(await page.locator('#people-detail h3').innerText(),/<img/);
    await page.getByText('来源与人工关联',{exact:true}).click();assert.match(await page.locator('#people-associations .source-list').first().innerText(),/群名片/);
    checks.push('QQ nickname source and group-card nature are distinct; HTML nickname stays inert text');
    await page.screenshot({path:path.join(evidence,'nickname-and-evidence.png'),fullPage:true});
    await choose('p1');await page.getByRole('button',{name:'群聊',exact:true}).click();await settled();
    assert.equal(await page.locator('#people-history .msg').count(),4);
    assert.match(await page.locator('#people-history').innerText(),/group-one/);assert.match(await page.locator('#people-history').innerText(),/平台用户名/);
    await page.locator('#people-group').selectOption('group-two');await settled();assert.equal(await page.locator('#people-history .msg').count(),2);
    await page.getByRole('button',{name:'私聊',exact:true}).click();await settled();assert.equal(await page.locator('#people-history .msg').count(),2);
    checks.push('private/all-group/specific-group switch preserves actual speaker, source and accepted replies');
    await page.getByText('来源与人工关联',{exact:true}).click();await page.locator('#people-unlink-source').selectOption('g1');
    await page.locator('#people-unlink').click();await confirmReview();await settled();
    assert.notEqual((await person('p1')).id,(await person('g1')).id);await page.locator('#btn-ref').click();await settled();
    assert.notEqual((await person('p1')).id,(await person('g1')).id);checks.push('UI unlink persists refusal across refresh; stale automatic evidence cannot rejoin');
    await choose('p1');await page.getByText('来源与人工关联',{exact:true}).click();await page.locator('#people-associate').selectOption((await person('g1')).id);
    await page.locator('#people-link').click();await confirmReview();await settled();assert.equal((await person('p1')).status,'manual_confirmed');
    assert.equal((await person('p1')).sources.length,4);checks.push('explicit UI reconfirmation restores one group and stays manual, never platform-certified');
    await choose('p1');await page.getByText('来源与人工关联',{exact:true}).click();await page.locator('#people-associate').selectOption((await person('other')).id);
    await page.locator('#people-deny').click();await confirmReview();await settled();await choose('other');
    assert.match(await page.locator('#people-detail').innerText(),/人工解除\/否认不关联/);checks.push('UI deny records a visible decision without joining the candidate');
    await page.locator('#people-search').fill('新昵称');await page.getByRole('button',{name:'查找用户',exact:true}).click();await settled();
    assert.equal(await page.locator('.uchip').count(),1);assert.equal((await person('n1')).sources.length,2);
    await page.locator('#people-search').fill('');await page.getByRole('button',{name:'查找用户',exact:true}).click();await settled();
    checks.push('user search finds nicknames without losing scene/query isolation');
    await choose('p1');assert.equal(await page.locator('[data-ptadd]').count(),0);
    await page.locator('#auto-ref').check();await page.getByText('来源与人工关联',{exact:true}).click();
    await page.locator('#people-associate').selectOption((await person('other')).id);await page.locator('#people-link').focus();
    await page.waitForTimeout(5600);assert.equal(await page.locator('#people-associate').inputValue(),(await person('other')).id);
    assert.equal(await page.locator('#auto-ref').isChecked(),true);await page.getByText('来源与人工关联',{exact:true}).click();
    let refreshed=false;page.on('request',r=>{if(r.url().includes('/api/people?'))refreshed=true;});
    await page.waitForTimeout(5600);assert.equal(refreshed,true);await settled();
    checks.push('association editing pauses repaint without disabling auto-refresh; collapse resumes it');
    await page.locator('#auto-ref').uncheck();await page.setViewportSize({width:390,height:844});await choose('p1');
    await page.getByRole('button',{name:'群聊',exact:true}).focus();await page.keyboard.press('Enter');await settled();
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
    assert.ok(await page.locator('.uchip .un').evaluateAll(nodes=>nodes.every(n=>n.scrollWidth<=n.clientWidth+1)));
    await page.screenshot({path:path.join(evidence,'narrow-pending-and-scenes.png'),fullPage:true});
    checks.push('keyboard scene switching and 390px width remain usable without page overflow');
    assert.equal(fs.readFileSync(path.join(f.data,'history_v2.json'),'utf8'),original);assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(evidence,'browser.json'),JSON.stringify({date:'2026-10-25',synthetic_only:true,checks,js_errors:errors,history_unchanged:true},null,2));
    console.log(JSON.stringify({passed:checks.length,checks,js_errors:errors}));
  }finally{if(browser)await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
