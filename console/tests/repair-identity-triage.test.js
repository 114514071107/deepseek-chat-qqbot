const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {createUserWorkbench}=require('../user-workbench'),{seed}=require('./workbench-fixture');
const {seedTriage}=require('./triage-fixture');
const hash=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex');
const mem=s=>'p2_'+hash([s.platform,s.instance,s.bot,s.sender]);
const by=(list,uid)=>list.people.find(p=>p.sources.some(s=>s.uid===uid));
function fixture(t){const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-triage-')),f=seed(root);t.after(()=>fs.rmSync(root,{recursive:true,force:true}));return {...f,w:createUserWorkbench(f.data)};}
test('derived name/ledger key belongs to its exact source instead of a phantom legacy user',t=>{
  const f=fixture(t),alias=mem(f.scopes.g1);f.save('names_all.json',{[alias]:'历史称呼'});f.save('points_all.json',{[alias]:{balance:777}});
  const before=fs.readFileSync(path.join(f.data,'points_all.json'),'utf8'),list=f.w.list();
  assert.equal(list.total,5);assert.equal(by(list,'g1').sources[0].name,'历史称呼');
  assert.equal(by(list,'g1').sources[0].index_aliases[0].uid,alias);
  assert.deepEqual(list.counts,{confirmed_users:0,pending_sources:4,legacy_archives:1,unassigned_legacy_archives:1,conversation_sources:4,metadata_keys:1,raw_keys:6});
  assert.equal(list.metadata[0].has_points,true);assert.ok(!JSON.stringify(list).includes('777'));
  assert.equal(fs.readFileSync(path.join(f.data,'points_all.json'),'utf8'),before);
});
test('existing explicit confirmation through an unambiguous derived alias reaches the actual source',t=>{
  const f=fixture(t),alias=mem(f.scopes.g1);f.save('names_all.json',{[alias]:'任意历史称呼'});
  f.save('console_people_v1.json',{version:1,groups:[['p1',alias]]});
  const file=path.join(f.data,'console_people_v1.json'),before=fs.readFileSync(file,'utf8');
  const p=by(f.w.list(),'p1');assert.equal(p.sources.length,2);assert.equal(p.status,'manual_confirmed');
  assert.ok(p.sources.some(s=>s.uid==='g1'));assert.equal(fs.readFileSync(file,'utf8'),before);
});
test('legacy person confirmation keeps its scene unknown and out of private/group projection',t=>{
  const f=fixture(t);let list=f.w.list(),body={left:by(list,'p1').id,right:by(list,'legacy').id,revision:list.revision,confirm:true};
  assert.equal(f.w.link(body).ok,true);list=f.w.list();const p=by(list,'p1');
  assert.equal(p.sources.find(s=>s.uid==='legacy').kind,'legacy');assert.equal(p.status,'manual_confirmed');
  assert.equal(list.counts.legacy_archives,1);assert.equal(list.counts.unassigned_legacy_archives,0);
  const rows=f.w.history(new URLSearchParams({person:p.id,mode:'private'}));assert.equal(rows.entries.length,2);
  assert.ok(rows.entries.every(r=>r.scope_uid==='p1'));
  assert.equal(f.w.history(new URLSearchParams({person:p.id,mode:'legacy'})).entries[0].text,'LEGACY-ONLY');
});
test('settings-only keys are inspectable metadata while a real new inbound source stays pending',t=>{
  const f=fixture(t);f.scopes.new={...f.scopes.p1,sender:'new-user',message_id:'real-inbound'};f.save('scopes_v2.json',f.scopes);
  f.save('names_all.json',{'only-note':'不是聊天','old-empty':'空索引'});f.save('points_all.json',{'only-ledger':{balance:12345}});
  const list=f.w.list();assert.equal(list.total,6);assert.equal(by(list,'new').status,'pending');
  assert.equal(list.counts.metadata_keys,3);assert.equal(list.metadata.length,3);assert.ok(!JSON.stringify(list).includes('12345'));
  assert.equal(list.counts.conversation_sources,5);
});
test('explicit standalone confirmation can be revoked without touching other peoples decisions',t=>{
  const f=fixture(t);let list=f.w.list();
  assert.equal(f.w.confirm({person:by(list,'p1').id,revision:list.revision,confirm:true}).ok,true);
  list=f.w.list();f.w.confirm({person:by(list,'other').id,revision:list.revision,confirm:true});
  list=f.w.list();assert.equal(list.counts.confirmed_users,2);
  f.w.unlink({person:by(list,'p1').id,scope:'p1',revision:list.revision,confirm:true});
  list=f.w.list();assert.equal(by(list,'p1').status,'pending');assert.equal(by(list,'other').status,'manual_confirmed');
});
test('category counts explain confirmed users, pending sources and archives without claiming a total population',t=>{
  const f=fixture(t);f.save('console_people_v1.json',{version:1,groups:[['p1','g1','g2']]});
  const all=f.w.list();assert.equal(all.counts.confirmed_users,1);assert.equal(all.counts.pending_sources,1);
  assert.equal(f.w.list(new URLSearchParams('category=confirmed')).people.length,1);
  assert.equal(f.w.list(new URLSearchParams('category=legacy')).people[0].sources[0].uid,'legacy');
  assert.throws(()=>f.w.list(new URLSearchParams('category=unknown')),/分类/);
});
test('a stable nickname source wins conflicting later sources while its own rename still updates',t=>{
  const f=fixture(t),profiles={version:1,sources:{}};
  function p(uid,seen,at,name){profiles.sources[uid]={source:f.scopes[uid],app:'fixture-app',observed_at:at,first_seen_at:seen,message_id:'m',
    identity:{namespace:'qq_user_openid',value:'private-A',basis:f.scopes[uid].private?'qq_author_user':'qq_author_pair'},
    nickname:{kind:'platform_name',value:name,source:'qq.author.username',at,message_id:'m'}};f.save('workbench_profiles_v1.json',profiles);}
  p('p1',1,20,'第一来源');p('g1',2,30,'另一路称呼');
  const before=by(f.w.list(),'p1');assert.match(before.label,/第一来源/);assert.equal(before.nickname_conflict,true);
  p('g1',2,50,'另一路又变了');assert.match(by(f.w.list(),'p1').label,/第一来源/);
  p('p1',1,60,'原来源改名');assert.match(by(f.w.list(),'p1').label,/原来源改名/);assert.equal(by(f.w.list(),'p1').id,before.id);
});
test('six people with eighteen mixed keys produce four confirmed users without guessing missing mappings',t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-six-people-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const f=seedTriage(root),w=createUserWorkbench(f.data),list=w.list();
  assert.deepEqual(list.counts,{confirmed_users:4,pending_sources:3,legacy_archives:2,unassigned_legacy_archives:2,conversation_sources:12,metadata_keys:4,raw_keys:18});
  assert.equal(list.total,9);assert.equal(by(list,'pA').sources.length,2);assert.equal(by(list,'pB').sources.length,3);
  assert.equal(by(list,'gD1').sources.length,2);assert.equal(by(list,'gE').sources.length,2);
  assert.notEqual(by(list,'pC').id,by(list,'gC').id);assert.notEqual(by(list,'gE').id,by(list,'gF').id);
  const id=by(list,'gD1').id;f.source('pD','user-D','',{user:'user-D'});f.flush();
  const after=createUserWorkbench(f.data).list();assert.equal(by(after,'gD1').sources.length,3);assert.equal(by(after,'gD1').id,id);
  assert.equal(after.counts.confirmed_users,4);assert.equal(after.counts.pending_sources,3);
  assert.ok(!JSON.stringify(after).includes('32100'));
});
test('ambiguous derived keys do not merge two group domains or silently satisfy a human confirmation',t=>{
  const f=fixture(t);f.scopes.g2.sender=f.scopes.g1.sender;f.save('scopes_v2.json',f.scopes);
  const alias=mem(f.scopes.g1);f.save('names_all.json',{[alias]:'共享资料键'});f.save('console_people_v1.json',{version:1,groups:[['p1',alias]]});
  const list=f.w.list();assert.notEqual(by(list,'g1').id,by(list,'g2').id);assert.equal(by(list,'p1').status,'pending');
  assert.equal(list.metadata[0].related_count,2);assert.equal(by(list,'g1').sources[0].name,'');
  assert.equal(list.unresolved_mapping_references,1);
});
