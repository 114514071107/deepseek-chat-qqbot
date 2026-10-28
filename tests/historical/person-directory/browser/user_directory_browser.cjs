// Real browser against a short-lived synthetic Console. No production reads/writes.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {chromium}=require('playwright'),{createConsoleServer}=require('../console/server');
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
(async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-directory-browser-')),data=path.join(root,'dsh_data');fs.mkdirSync(data);
  const scopes={},history={},directory={version:1,sources:{},pending:{}},checks=[],errors=[];
  for(let i=1;i<=7;i++)for(const group of i===1?['','group-alpha','group-beta']:i===2?['','group-alpha']:['']){
    const uid='fixture-'+i+'-'+(group||'private'),s={platform:'qq_official',instance:'fixture',bot:'bot',sender:'member-'+i+'-'+group,group,private:!group,message_id:'message-'+uid};
    scopes[uid]=s;history[uid]=[{id:uid+'-u',role:'user',text:'SYNTHETIC user '+i+' '+(group||'private'),ts:i*10,request_id:uid,source:s},
      {id:uid+'-a',role:'assistant',text:'SYNTHETIC answer '+i,ts:i*10+1,request_id:uid,source:s,delivery:{status:'accepted'}}];
    directory.sources[hash([s.platform,s.instance,s.bot,group?'group':'private',group,s.sender,'fixture-app'])]={source:s,app:'fixture-app',person:String(i).padStart(32,'0'),created_at:1,nickname:{value:'合成用户'+i,kind:'self_selected',source:'dsh.self_selected',at:2}};
  }
  history.legacy=[{role:'user',text:'SYNTHETIC old unknown scene',ts:1}];
  const save=(file,v)=>fs.writeFileSync(path.join(data,file),JSON.stringify(v));
  save('scopes_v2.json',scopes);save('history_v2.json',history);save('user_directory_v1.json',directory);
  save('console_people_v1.json',{version:2,groups:[['fixture-1-private','legacy']],denied:[]});
  save('thoughts_v2.json',{'fixture-1-private':[{text:'SYNTHETIC thought 1',src:'fixture',t:1}]});
  const original=fs.readFileSync(path.join(data,'history_v2.json'));
  const token='synthetic-directory-browser-token-123456',server=createConsoleServer({dsh:root,port:0,token});await new Promise(r=>server.listen(0,'127.0.0.1',r));
  let browser;
  try{
    browser=await chromium.launch({channel:'msedge',headless:true});
    const context=await browser.newContext({httpCredentials:{username:'dsh',password:token},viewport:{width:1280,height:960}}),page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
    const base='http://127.0.0.1:'+server.address().port;
    await page.goto(base);await page.locator('[data-t="memory"]').click();
    await page.waitForSelector('#m-uid option',{state:'attached'});assert.equal(await page.locator('#m-uid option').count(),7);
    const options=await page.locator('#m-uid option').allTextContents();assert.ok(options.every(s=>/^合成用户[1-7]$/.test(s)));checks.push('seven people, one named memory option each');
    const catalog=await (await context.request.get(base+'/api/people')).json(),p1=catalog.people.find(p=>p.label==='合成用户1'),p2=catalog.people.find(p=>p.label==='合成用户2');
    await page.selectOption('#m-uid',p1.id);await page.waitForSelector('#m-history >> text=SYNTHETIC old unknown scene');
    assert.ok((await page.locator('#m-history').textContent()).includes('group-alpha'));assert.ok((await page.locator('#m-history').textContent()).includes('私聊'));assert.ok((await page.locator('#m-history').textContent()).includes('场景未知'));checks.push('one person includes private, two groups and marked unknown legacy');
    await page.selectOption('#m-mode','group');await page.waitForSelector('#m-group');await page.selectOption('#m-group','group-beta');await page.waitForFunction(()=>document.querySelector('#m-history')?.textContent.includes('group-beta')&&!document.querySelector('#m-history')?.textContent.includes('group-alpha'));checks.push('concrete group filter excludes private and other group');
    await page.selectOption('#m-uid',p2.id);await page.waitForFunction(()=>document.querySelector('#m-history')?.textContent.includes('user 2'));assert.ok(!(await page.locator('#m-history').textContent()).includes('user 1'));checks.push('switching person clears foreign group and excludes previous person');
    await page.locator('[data-t="users"]').click();await page.waitForSelector('[data-person]');await page.locator('[data-person="'+p1.id+'"]').click();
    await page.getByRole('button',{name:'全部消息',exact:true}).waitFor();await page.waitForFunction(()=>document.querySelector('#people-history')?.textContent.includes('SYNTHETIC old unknown scene'));checks.push('user page defaults to all messages with the same person');
    await page.locator('#auto-ref').uncheck();await page.locator('[data-person="'+p2.id+'"]').click();await page.waitForFunction(()=>document.querySelector('#people-history')?.textContent.includes('user 2'));
    for(const row of Object.values(directory.sources))if(row.nickname.value==='合成用户2')row.person='f'.repeat(32);save('user_directory_v1.json',directory);
    const updated=await (await context.request.get(base+'/api/people')).json(),newP2=updated.people.find(p=>p.label==='合成用户2');
    await page.locator('#btn-ref').click();await page.locator('[data-person="'+newP2.id+'"].on').waitFor();checks.push('new self proof preserves the selected user across a changed person id');
    await page.locator('[data-t="memory"]').click();await page.waitForSelector('#m-uid');await page.setViewportSize({width:390,height:844});await page.selectOption('#m-mode','all');await page.selectOption('#m-uid',p1.id);await page.waitForFunction(()=>document.querySelector('#m-history')?.textContent.includes('SYNTHETIC old unknown scene'));
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));checks.push('390px view has no horizontal page overflow');
    const out=path.join(root,'synthetic-memory.png');await page.screenshot({path:out,fullPage:true});
    assert.deepEqual(errors,[]);assert.deepEqual(fs.readFileSync(path.join(data,'history_v2.json')),original);checks.push('no page errors or original history writes');
    console.log(JSON.stringify({passed:checks.length,checks,errors,screenshot:out}));
    if(process.env.DSH_IDENTITY_SCREENSHOT){fs.mkdirSync(path.dirname(process.env.DSH_IDENTITY_SCREENSHOT),{recursive:true});fs.copyFileSync(out,process.env.DSH_IDENTITY_SCREENSHOT);await page.screenshot({path:process.env.DSH_IDENTITY_SCREENSHOT.replace('.png','-viewport.png')});}
  }finally{if(browser)await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
