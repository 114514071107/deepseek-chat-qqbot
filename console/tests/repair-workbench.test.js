const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createConsoleServer}=require('../server');
const {seed}=require('./workbench-fixture');
async function fixture(t){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-people-'));const seeded=seed(root);
  const server=createConsoleServer({dsh:root,port:0,token:'fixture-token-for-workbench-12345678'});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  t.after(async()=>{server.closeAllConnections();await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true});});
  const base='http://127.0.0.1:'+server.address().port;
  const headers={authorization:'Basic '+Buffer.from('dsh:fixture-token-for-workbench-12345678').toString('base64'),'X-DSH-Request':'1',origin:base};
  const get=async url=>(await fetch(base+url,{headers})).json();
  const post=async(url,body)=>(await fetch(base+url,{method:'POST',headers:{...headers,'content-type':'application/json'},body:JSON.stringify(body)})).json();
  return {...seeded,base,headers,get,post};
}
const byScope=(list,uid)=>list.people.find(p=>p.sources.some(s=>s.uid===uid));
async function link(f,left,right){const list=await f.get('/api/people');return f.post('/api/people/link',{left:byScope(list,left).id,right:byScope(list,right).id,revision:list.revision,confirm:true});}

test('list contains no message bodies; ambiguous QQ identities and same names remain separate',async t=>{
  const f=await fixture(t),list=await f.get('/api/people');
  assert.equal(list.ok,true);assert.equal(list.total,5);assert.equal(list.scope_count,5);
  assert.notEqual(byScope(list,'p1').id,byScope(list,'other').id);
  assert.notEqual(byScope(list,'p1').id,byScope(list,'g1').id);
  assert.ok(!JSON.stringify(list).includes('SYNTHETIC-'));
  assert.equal(byScope(list,'legacy').legacy,true);
});
test('explicit association produces one entry for private and two groups; unlink preserves original stores',async t=>{
  const f=await fixture(t);const before=fs.readFileSync(path.join(f.data,'history_v2.json'),'utf8');
  assert.equal((await link(f,'p1','g1')).ok,true);assert.equal((await link(f,'p1','g2')).ok,true);
  const list=await f.get('/api/people'),person=byScope(list,'p1');
  assert.equal(person.sources.length,3);assert.equal(list.total,3);assert.equal(list.scope_count,5);
  const result=await f.post('/api/people/unlink',{person:person.id,scope:'g2',revision:list.revision,confirm:true});assert.equal(result.ok,true);
  assert.equal(byScope(await f.get('/api/people'),'p1').sources.length,2);
  assert.equal(fs.readFileSync(path.join(f.data,'history_v2.json'),'utf8'),before);
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(f.data,'points_all.json'),'utf8')),{});
});
test('private/group/group-filter projections keep sources, accepted replies and media',async t=>{
  const f=await fixture(t);await link(f,'p1','g1');await link(f,'p1','g2');
  const id=byScope(await f.get('/api/people'),'p1').id;
  const privateRows=await f.get('/api/people/history?person='+id+'&mode=private');
  assert.equal(privateRows.entries.length,2);assert.ok(privateRows.entries.every(e=>e.scope_uid==='p1'));
  assert.deepEqual(privateRows.entries.find(e=>e.role==='user').images,['media/fixture.png']);
  const all=await f.get('/api/people/history?person='+id+'&mode=group');
  assert.equal(all.entries.length,4);assert.ok(all.entries.every(e=>e.group));
  assert.ok(!JSON.stringify(all).includes('OTHER-MEMBER-SECRET'));assert.ok(!JSON.stringify(all).includes('UNBOUND-ASSISTANT'));
  const one=await f.get('/api/people/history?person='+id+'&mode=group&group=group-one');assert.equal(one.entries.length,2);
  assert.equal((await f.get('/api/people/history?person='+id+'&mode=group&group=foreign')).ok,false);
});
test('pagination, empty modes, legacy and invalid input have explicit bounds',async t=>{
  const f=await fixture(t);const list=await f.get('/api/people?limit=2&offset=0');assert.equal(list.people.length,2);assert.equal(list.next_offset,2);
  const id=byScope(await f.get('/api/people'),'p1').id;
  const empty=await f.get('/api/people/history?person='+id+'&mode=group');assert.deepEqual(empty.entries,[]);assert.equal(empty.recent_only,true);
  const page=await f.get('/api/people/history?person='+id+'&mode=private&limit=1');assert.equal(page.entries.length,1);assert.equal(page.next_offset,1);
  assert.equal((await f.get('/api/people?limit=-1')).ok,false);
  const legacy=byScope(await f.get('/api/people'),'legacy');
  assert.equal((await f.get('/api/people/history?person='+legacy.id+'&mode=legacy')).entries[0].text,'LEGACY-ONLY');
});
test('mapping needs confirmation/current revision and rejects legacy or fabricated persons',async t=>{
  const f=await fixture(t);const list=await f.get('/api/people');const body={left:byScope(list,'p1').id,right:byScope(list,'g1').id,revision:list.revision};
  assert.equal((await f.post('/api/people/link',body)).ok,false);
  assert.equal((await f.post('/api/people/link',{...body,confirm:true})).ok,true);
  assert.equal((await f.post('/api/people/link',{...body,confirm:true})).ok,false);
  assert.equal((await link(f,'p1','legacy')).ok,false);
  assert.equal((await f.post('/api/people/unlink',{person:'fake',scope:'p1',confirm:true,revision:(await f.get('/api/people')).revision})).ok,false);
});
test('authentication, cross-origin, media and original scope operations remain protected',async t=>{
  const f=await fixture(t);assert.equal((await fetch(f.base+'/api/people')).status,401);
  assert.equal((await fetch(f.base+'/api/people',{headers:{...f.headers,origin:'http://evil.invalid'}})).status,403);
  assert.equal((await fetch(f.base+'/api/people/link',{method:'POST',headers:{...f.headers,origin:'http://evil.invalid','content-type':'application/json'},body:'{}'})).status,403);
  assert.equal((await fetch(f.base+'/api/media?f=media/fixture.png')).status,401);
  assert.equal((await fetch(f.base+'/api/media?f=media/fixture.png',{headers:f.headers})).status,200);
  const old=await f.get('/api/history?uid=p1');assert.equal(old.entries.length,2);
  assert.equal((await f.post('/api/points',{uid:'person_invalid',mode:'add',value:10})).ok,false);
});

test('aggregate identity cannot become a mutation uid even when a runtime is online',async t=>{
  const f=await fixture(t),id=byScope(await f.get('/api/people'),'p1').id;
  const root=path.join(f.data,'admin_v2');fs.mkdirSync(path.join(root,'requests'),{recursive:true});fs.mkdirSync(path.join(root,'responses'));
  fs.writeFileSync(path.join(root,'live.json'),JSON.stringify({instance:'fixture',at:Date.now()/1000}));
  const timer=setInterval(()=>{for(const name of fs.readdirSync(path.join(root,'requests'))){if(!name.endsWith('.json'))continue;
    fs.writeFileSync(path.join(root,'responses',name),JSON.stringify({id:name.slice(0,-5),instance:'fixture',ok:true}));}},5);
  t.after(()=>clearInterval(timer));
  for(const endpoint of ['/api/points','/api/user','/api/history/clear']){
    const result=await f.post(endpoint,{uid:id,mode:'add',value:10,key:'reply',layers:['rolling']});
    assert.equal(result.ok,false);assert.match(result.error,/来源/);
  }
  assert.equal(fs.readdirSync(path.join(root,'requests')).length,0);
});

test('nickname changes do not split identity; source caps and unaccepted replies are explicit',async t=>{
  const f=await fixture(t),original=byScope(await f.get('/api/people'),'p1').id;
  f.save('names_all.json',{p1:'全新备注',other:'全新备注'});
  const renamed=await f.get('/api/people');assert.equal(byScope(renamed,'p1').id,original);assert.notEqual(byScope(renamed,'other').id,original);
  f.histories.p1=Array.from({length:400},(_,n)=>({id:String(n),ts:n,role:'user',text:'row'+n,source:f.scopes.p1}));
  f.histories.p1.push({role:'assistant',text:'UNKNOWN',ts:500,source:f.scopes.p1,delivery:{status:'unknown'}});
  f.save('history_v2.json',f.histories);
  const rows=await f.get('/api/people/history?person='+original+'&mode=private&limit=200');
  assert.equal(rows.entries.length,149);assert.equal(rows.per_scope_limit,150);assert.equal(rows.recent_only,true);assert.equal(rows.excluded_unverified,1);
});

test('oversized history is rejected before loading or mutating the file',async t=>{
  const f=await fixture(t),file=path.join(f.data,'history_v2.json');
  fs.truncateSync(file,33*1024*1024);
  const result=await f.get('/api/people');assert.equal(result.ok,false);assert.match(result.error,/读取上限/);
  assert.equal(fs.statSync(file).size,33*1024*1024);
});
