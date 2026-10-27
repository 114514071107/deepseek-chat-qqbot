const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createUserWorkbench}=require('../user-workbench');
const {seed}=require('./workbench-fixture');
const by=(list,uid)=>list.people.find(p=>p.sources.some(s=>s.uid===uid));
function fixture(t){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-auto-people-')),f=seed(root);
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const profiles={version:1,sources:{}};
  function profile(uid,user='private-A',at=20,name='小禾'){
    profiles.sources[uid]={source:f.scopes[uid],app:'fixture-app',observed_at:at,message_id:'profile-'+at,
      identity:{namespace:'qq_user_openid',value:user,basis:f.scopes[uid].private?'qq_author_user':'qq_author_pair'},
      nickname:{value:name,kind:'platform_name',source:'qq.author.username',at,message_id:'profile-'+at}};
    f.save('workbench_profiles_v1.json',profiles);
  }
  return {...f,profiles,profile,w:createUserWorkbench(f.data)};
}
test('trusted author mappings auto join private and two groups, including a later source and restart',t=>{
  const f=fixture(t);f.profile('p1');f.profile('g1');
  assert.equal(by(f.w.list(),'p1').sources.length,2);
  f.profile('g2');const result=f.w.list(),p=by(result,'p1');
  assert.equal(p.sources.length,3);assert.equal(result.total,4);assert.equal(p.status,'automatic_confirmed');
  assert.equal(by(createUserWorkbench(f.data).list(),'p1').id,p.id);
  assert.equal(by(f.w.list(),'p1').id,p.id);
});
test('no evidence and equal strings in different domains never guess identity',t=>{
  const f=fixture(t);f.scopes.g1.sender=f.scopes.p1.sender;f.save('scopes_v2.json',f.scopes);
  const list=f.w.list();assert.notEqual(by(list,'p1').id,by(list,'g1').id);
  assert.equal(by(list,'p1').status,'automatic_confirmed');assert.equal(by(list,'legacy').status,'legacy');
});
test('nickname types and an established source stay visible without using a note as a QQ nickname',t=>{
  const f=fixture(t);f.profile('p1','private-A',30,'新版');f.profile('g1','private-A',10,'旧版');
  f.profiles.sources.p1.first_seen_at=100;f.profiles.sources.g1.first_seen_at=200;f.save('workbench_profiles_v1.json',f.profiles);
  let p=by(f.w.list(),'p1');assert.equal(p.nickname,null);assert.match(p.label,/新版/);
  assert.equal(p.profile_kind,'platform_name');assert.match(p.label,/平台用户名/);
  f.profiles.sources.p1.nickname={value:'新QQ昵称',kind:'qq_nickname',source:'onebot.sender.nickname',at:40,message_id:'new'};
  f.save('workbench_profiles_v1.json',f.profiles);
  // A QQ-official source cannot forge a OneBot nickname type.
  p=by(f.w.list(),'p1');assert.equal(p.nickname,null);
  assert.match(by(f.w.list(),'other').label,/昵称未获取/);
});
test('unlink of automatic sources persists rejection instead of silently rejoining',t=>{
  const f=fixture(t);f.profile('p1');f.profile('g1');f.profile('g2');
  let list=f.w.list(),p=by(list,'p1');
  assert.equal(f.w.unlink({person:p.id,scope:'g1',confirm:true,revision:list.revision}).ok,true);
  list=createUserWorkbench(f.data).list();assert.notEqual(by(list,'p1').id,by(list,'g1').id);
  assert.equal(by(list,'g1').status,'pending');assert.equal(by(list,'g1').conflict,true);
  assert.equal(f.w.list().people.length,5);
});
test('old manual groups stay manual and future reliable source joins without overwriting decisions',t=>{
  const f=fixture(t);f.save('console_people_v1.json',{version:1,groups:[['p1','g1']]});
  assert.equal(by(f.w.list(),'p1').status,'manual_confirmed');
  f.profile('p1');f.profile('g1');f.profile('g2');
  const p=by(f.w.list(),'p1');assert.equal(p.sources.length,3);assert.equal(p.status,'manual_confirmed');
});
test('stale revision and a second writer cannot lose an existing mapping',t=>{
  const f=fixture(t),second=createUserWorkbench(f.data),initial=f.w.list();
  const body={left:by(initial,'p1').id,right:by(initial,'g1').id,confirm:true,revision:initial.revision};
  f.w.link(body);assert.throws(()=>second.link({...body,right:by(initial,'g2').id}),/变化/);
  const lock=path.join(f.data,'console_people_v1.json.lock');fs.writeFileSync(lock,'fixture-owner');
  const current=f.w.list();assert.throws(()=>second.link({left:by(current,'p1').id,right:by(current,'g2').id,confirm:true,revision:current.revision}),/并发|正在/);
  assert.equal(by(f.w.list(),'p1').sources.length,2);
});
test('deny is visible, survives new evidence, and only explicit reconfirmation removes the block',t=>{
  const f=fixture(t);let list=f.w.list();
  f.w.deny({left:by(list,'p1').id,right:by(list,'g1').id,revision:list.revision,confirm:true});
  assert.match(by(f.w.list(),'p1').basis.join(' '),/否认|不关联/);
  f.profile('p1');f.profile('g1');list=f.w.list();
  assert.notEqual(by(list,'p1').id,by(list,'g1').id);
  f.w.link({left:by(list,'p1').id,right:by(list,'g1').id,revision:list.revision,confirm:true});
  assert.equal(by(f.w.list(),'p1').sources.length,2);assert.equal(by(f.w.list(),'p1').status,'manual_confirmed');
});
test('application and instance boundaries, mismatched evidence and conflicting claims block auto merge',t=>{
  const f=fixture(t);f.profile('p1');f.profile('g1');
  f.profiles.sources.g1.app='different-app';f.save('workbench_profiles_v1.json',f.profiles);
  assert.notEqual(by(f.w.list(),'p1').id,by(f.w.list(),'g1').id);
  f.profiles.sources.g1.app='fixture-app';f.profiles.sources.g1.source={...f.scopes.g1,sender:'not-this-user'};
  f.save('workbench_profiles_v1.json',f.profiles);assert.notEqual(by(f.w.list(),'p1').id,by(f.w.list(),'g1').id);
  f.profile('g1');f.profiles.sources.g1.identity_conflict=true;f.save('workbench_profiles_v1.json',f.profiles);
  const list=f.w.list();assert.notEqual(by(list,'p1').id,by(list,'g1').id);assert.equal(by(list,'g1').conflict,true);
});
test('OneBot numeric account auto merges while nickname updates remain display only',t=>{
  const f=fixture(t);
  for(const uid of ['p1','g1','g2']){
    f.scopes[uid]={...f.scopes[uid],platform:'aiocqhttp',bot:'654321',sender:'123456'};
    f.profile(uid,'123456',uid==='g2'?30:20,uid==='g2'?'改名':'老昵称');
    const p=f.profiles.sources[uid];p.app='654321';p.identity={namespace:'onebot_qq',value:'123456',basis:'onebot_message_sender'};
    p.first_seen_at=uid==='g2'?50:100;
    p.nickname.kind='qq_nickname';p.nickname.source='onebot.sender.nickname';
    p.group_card={value:'仅群名片',kind:'group_card',source:'onebot.sender.card',at:20,message_id:'card'};
  }
  f.save('scopes_v2.json',f.scopes);f.save('workbench_profiles_v1.json',f.profiles);
  let p=by(f.w.list(),'p1');const id=p.id;assert.equal(p.nickname,'改名');assert.equal(p.sources.length,3);
  assert.equal(p.status,'automatic_confirmed');assert.equal(p.nickname_conflict,true);
  f.profiles.sources.g2.nickname.value='再次改名';f.save('workbench_profiles_v1.json',f.profiles);
  p=by(f.w.list(),'p1');assert.equal(p.id,id);assert.equal(p.nickname,'再次改名');
  assert.equal(p.sources.find(s=>s.uid==='p1').group_card,null);
});
test('same exact original identity can be automatically confirmed even without a nickname',t=>{
  const f=fixture(t);f.scopes.alias={...f.scopes.p1};f.save('scopes_v2.json',f.scopes);
  const p=by(f.w.list(),'p1');assert.equal(p.sources.length,2);assert.equal(p.status,'automatic_confirmed');
  assert.match(p.basis.join(' '),/原始身份/);
  f.scopes.otherAlias={...f.scopes.other};f.save('scopes_v2.json',f.scopes);
  const list=f.w.list();assert.notEqual(by(list,'p1').id,by(list,'other').id,'different exact-origin sets need different person IDs');
});
test('exact source strings with conflicting application evidence cannot collapse into one entry',t=>{
  const f=fixture(t);f.scopes.alias={...f.scopes.p1};f.save('scopes_v2.json',f.scopes);
  f.profile('p1');f.profile('alias');f.profiles.sources.alias.app='other-app';f.save('workbench_profiles_v1.json',f.profiles);
  const list=f.w.list();assert.notEqual(by(list,'p1').id,by(list,'alias').id);
  assert.equal(by(list,'p1').conflict,true);assert.equal(by(list,'alias').status,'pending');
});
test('verified app and group-member identity survive SDK self-id placeholders without crossing groups',t=>{
  const f=fixture(t);f.scopes.alias={...f.scopes.g1,bot:'other-sdk-placeholder'};f.save('scopes_v2.json',f.scopes);
  f.profile('g1');f.profile('alias');
  f.profiles.sources.g1.identity=null;f.profiles.sources.alias.identity=null;f.save('workbench_profiles_v1.json',f.profiles);
  const list=f.w.list(),p=by(list,'g1');assert.equal(p.sources.length,2);assert.equal(p.status,'automatic_confirmed');
  assert.notEqual(p.id,by(list,'g2').id);
});
test('a prior manual denial also blocks a later exact-origin proof',t=>{
  const f=fixture(t);f.scopes.alias={...f.scopes.g1,bot:'other-sdk-placeholder'};f.save('scopes_v2.json',f.scopes);
  let list=f.w.list();f.w.deny({left:by(list,'g1').id,right:by(list,'alias').id,revision:list.revision,confirm:true});
  f.profile('g1');f.profile('alias');f.profiles.sources.g1.identity=null;f.profiles.sources.alias.identity=null;
  f.save('workbench_profiles_v1.json',f.profiles);list=f.w.list();
  assert.notEqual(by(list,'g1').id,by(list,'alias').id);assert.equal(by(list,'g1').status,'pending');
  assert.equal(by(list,'alias').conflict,true);
});
test('mapping capacity is rejected before an unsupported store can be written',t=>{
  const f=fixture(t),file=path.join(f.data,'console_people_v1.json');
  f.save('console_people_v1.json',{version:1,groups:Array.from({length:2000},()=>['archived-a','archived-b'])});
  const before=fs.readFileSync(file,'utf8'),list=f.w.list();
  assert.throws(()=>f.w.link({left:by(list,'p1').id,right:by(list,'g1').id,revision:list.revision,confirm:true}));
  assert.equal(fs.readFileSync(file,'utf8'),before);
});
