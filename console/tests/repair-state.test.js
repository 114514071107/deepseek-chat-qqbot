const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const crypto=require('node:crypto');
const {createConsoleServer}=require('../server');

async function fixture(t,bridgeTimeout=100){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-state-')); const data=path.join(root,'dsh_data');fs.mkdirSync(data);
  t.after(()=>fs.promises.rm(root,{recursive:true,force:true,maxRetries:5,retryDelay:50}));
  const token=crypto.randomBytes(32).toString('hex'); const server=createConsoleServer({dsh:root,token,port:0,bridgeTimeout});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>{server.closeAllConnections();server.close(r);}));
  const origin='http://127.0.0.1:'+server.address().port;
  const headers={authorization:'Basic '+Buffer.from('dsh:'+token).toString('base64'),origin,'content-type':'application/json','x-dsh-request':'1'};
  return {data,get:async(url)=>(await fetch(origin+url,{headers})).json(),post:async(url,body)=>{const r=await fetch(origin+url,{method:'POST',headers,body:JSON.stringify(body)});return r.json();}};
}

test('offline runtime is an explicit failure; console cannot alter a stale cached file',async t=>{
  const {data,post}=await fixture(t); const file=path.join(data,'history_all.json');
  const original=JSON.stringify({fixture:[{text:'preserve'}]});fs.writeFileSync(file,original);
  const result=await post('/api/history/clear',{uid:'fixture',layers:['rolling']});
  assert.equal(result.ok,false);assert.equal(fs.readFileSync(file,'utf8'),original);
  const switched=await post('/api/switch',{key:'enabled',value:false});assert.equal(switched.ok,false);
  assert.equal(fs.existsSync(path.join(data,'dsh_soul_conf.json')),false);
});

test('private proactive effective default is off without writing an override',async t=>{
  const {data,get}=await fixture(t);
  const source={platform:'qq_official',instance:'fixture',bot:'self',sender:'user',group:'',message_id:'m',private:true};
  const key='p2_'+crypto.createHash('sha256').update(JSON.stringify([source.platform,source.instance,source.bot,source.sender])).digest('hex');
  fs.writeFileSync(path.join(data,'scopes_v2.json'),JSON.stringify({[key]:source}));
  const result=await get('/api/switches');
  assert.equal(result.friends[key].proactive,false);assert.ok(result.users.some(user=>user.uid===key));
  assert.equal(fs.existsSync(path.join(data,'friends_all.json')),false);
});

test('commands wait for matching runtime acknowledgment; expired lease and untyped sends fail',async t=>{
  const {data,post}=await fixture(t);const root=path.join(data,'admin_v2');fs.mkdirSync(path.join(root,'requests'),{recursive:true});fs.mkdirSync(path.join(root,'responses'));
  fs.writeFileSync(path.join(root,'live.json'),JSON.stringify({instance:'fixture-instance',at:Date.now()/1000}));
  let command;
  const timer=setInterval(()=>{
    try {
    const name=fs.readdirSync(path.join(root,'requests'))[0];if(!name)return;
    command=JSON.parse(fs.readFileSync(path.join(root,'requests',name)));
    fs.writeFileSync(path.join(root,'responses',name),JSON.stringify({ok:true,instance:'fixture-instance',id:name.slice(0,-5),applied_instance:'fixture-instance'}));
    fs.unlinkSync(path.join(root,'requests',name));
    } catch(error) {if(error.code!=='ENOENT')throw error;}
  },5);t.after(()=>clearInterval(timer));
  const result=await post('/api/points',{uid:'fixture',mode:'add',value:5});
  assert.equal(result.ok,true);assert.equal(command.operation,'points');assert.equal(command.body.value,5);
  assert.equal(fs.existsSync(path.join(data,'points_all.json')),false); // only the runtime may write it
  assert.equal((await post('/api/admin_send',{uid:'ambiguous-id',text:'fixture'})).ok,false);
  fs.writeFileSync(path.join(root,'live.json'),JSON.stringify({instance:'old',at:0}));
  assert.equal((await post('/api/switch',{key:'enabled',value:true})).ok,false);
});

test('real isolated Python state owner acknowledges cache, points, deletion and typed group target',async t=>{
  const {data,post,get}=await fixture(t,5000);
  const child=require('node:child_process').spawn('D:\\dsbot\\venv\\Scripts\\python.exe',['-B',path.resolve(__dirname,'../../tests/bridge_fixture.py'),path.dirname(data)],{cwd:path.dirname(data),windowsHide:true,stdio:['ignore','ignore','pipe'],env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
  let errors='';child.stderr.on('data',b=>errors+=b);
  const closed=new Promise(resolve=>child.once('close',resolve));
  try{
    for(let i=0;i<100&&!fs.existsSync(path.join(data,'admin_v2/live.json'));i++)await new Promise(r=>setTimeout(r,20));
    assert.equal(fs.existsSync(path.join(data,'admin_v2/live.json')),true,errors);
    const key=Object.keys(JSON.parse(fs.readFileSync(path.join(data,'scopes_v2.json'))))[0];
    // Runtime polling is 100ms; use the normal timeout for real IPC.
    const points=await post('/api/points',{uid:key,mode:'set',value:17});
    assert.equal(points.ok,true,JSON.stringify(points));
    const view=await get("/api/switches");assert.equal(view.points[key].balance,17);
    const name=await post('/api/name',{uid:key,name:'fixture name'});assert.equal(name.ok,true);
    assert.equal(JSON.parse(fs.readFileSync(path.join(data,'runtime_fixture.json'))).names[key],'fixture name');
    const sent=await post('/api/admin_send',{target_key:key,kind:'group',instance:'fixture-instance',text:'fixture'});assert.equal(sent.ok,true);
    assert.equal(JSON.parse(fs.readFileSync(path.join(data,'sent_fixture.json'))).kind,'group');
    const deleted=await post('/api/history/clear',{uid:key,layers:['rolling']});assert.equal(deleted.ok,true);
    assert.deepEqual(JSON.parse(fs.readFileSync(path.join(data,'runtime_fixture.json'))).h[key],[]);
  }finally{child.kill();await closed;}
});
