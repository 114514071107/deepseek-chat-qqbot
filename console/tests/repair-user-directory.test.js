const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {seed}=require('./workbench-fixture'),{createUserWorkbench}=require('../user-workbench');
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
const by=(r,uid)=>r.people.find(p=>p.sources.some(s=>s.uid===uid));
function fixture(t){const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-directory-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));const f=seed(root);return {...f,w:createUserWorkbench(f.data)};}
function directory(f){const sources={};for(const uid of ['p1','g1','g2']){const s=f.scopes[uid],app='fixture-app';
  const key=hash([s.platform,s.instance,s.bot,s.private?'private':'group',s.group,s.sender,app]);
  sources[key]={source:s,app,person:'a'.repeat(32),created_at:1,nickname:{value:'小禾',kind:'self_selected',source:'dsh.self_selected',at:20}};
}f.save('user_directory_v1.json',{version:1,sources,pending:{}});}
test('new trusted conversation is automatically a user without owner confirmation; names never join people',t=>{
  const f=fixture(t),r=f.w.list();assert.equal(by(r,'p1').status,'automatic_confirmed');assert.equal(by(r,'p1').category,'confirmed');
  assert.notEqual(by(r,'p1').id,by(r,'other').id);assert.equal(by(r,'legacy').status,'legacy');
});
test('self verified private and two group identities share one named entry after restart and all-history stays scoped',t=>{
  const f=fixture(t);directory(f);const r=f.w.list(),p=by(r,'p1');assert.equal(p.sources.length,3);assert.equal(p.label,'小禾');assert.equal(p.profile_kind,'self_selected');
  assert.equal(by(createUserWorkbench(f.data).list(),'p1').id,p.id);
  const h=f.w.history(new URLSearchParams({person:p.id,mode:'all'}));assert.deepEqual([...new Set(h.entries.map(e=>e.scene))].sort(),['group','private']);
  assert.equal(h.entries.filter(e=>e.role==='user').length,3);assert.ok(!JSON.stringify(h).includes('OTHER-MEMBER-SECRET'));assert.ok(!JSON.stringify(h).includes('UNBOUND-ASSISTANT'));
});
test('memory lists only selected person sources and deduplicates shared memory keys without changing data',t=>{
  const f=fixture(t);directory(f);const p=by(f.w.list(),'p1');
  fs.mkdirSync(path.join(f.data,'memories'));const k='p2_'+hash(['qq_official','fixture-bot','self','member-A-1']);
  fs.writeFileSync(path.join(f.data,'memories',k+'.md'),'GROUP-ONLY');
  fs.writeFileSync(path.join(f.data,'memories','private-B.md'),'FOREIGN-SECRET');
  const before=fs.readFileSync(path.join(f.data,'history_v2.json'));
  const m=f.w.memory(new URLSearchParams({person:p.id,mode:'all'}));assert.equal(m.sections.length,3);assert.ok(JSON.stringify(m).includes('GROUP-ONLY'));assert.ok(!JSON.stringify(m).includes('FOREIGN-SECRET'));
  assert.deepEqual(fs.readFileSync(path.join(f.data,'history_v2.json')),before);
  assert.throws(()=>f.w.memory(new URLSearchParams({person:'person_missing'})),/无效/);
});
test('self proof does not bypass existing deny, foreign app metadata or source mismatch',t=>{
  const f=fixture(t);let r=f.w.list();f.w.deny({left:by(r,'p1').id,right:by(r,'g1').id,revision:r.revision,confirm:true});directory(f);
  r=f.w.list();assert.notEqual(by(r,'p1').id,by(r,'g1').id);
  const store=JSON.parse(fs.readFileSync(path.join(f.data,'user_directory_v1.json')));Object.values(store.sources).find(x=>x.source.group==='group-two').source.sender='forged';f.save('user_directory_v1.json',store);
  assert.notEqual(by(f.w.list(),'p1').id,by(f.w.list(),'g2').id);
});
test('unverified identical memory keys stay unassigned; verification shows the original file only once',t=>{
  const f=fixture(t);f.scopes.g2.sender=f.scopes.g1.sender;
  f.save('scopes_v2.json',f.scopes);const key='p2_'+hash(['qq_official','fixture-bot','self','member-A-1']);
  fs.mkdirSync(path.join(f.data,'memories'));fs.writeFileSync(path.join(f.data,'memories',key+'.md'),'AMBIGUOUS-NOTES');
  let p=by(f.w.list(),'g1'),m=f.w.memory(new URLSearchParams({person:p.id}));assert.ok(!JSON.stringify(m).includes('AMBIGUOUS-NOTES'));assert.match(m.sections[0].notice,/多个/);
  directory(f);p=by(f.w.list(),'g1');m=f.w.memory(new URLSearchParams({person:p.id}));assert.equal(m.sections.flatMap(s=>s.notes).filter(n=>n.text==='AMBIGUOUS-NOTES').length,1);
});
test('legacy metadata stays readable only for an unsplit archive; split unknown metadata is not assigned',t=>{
  const f=fixture(t);f.save('thoughts_all.json',{legacy:[{text:'LEGACY-THOUGHT'}]});
  const p=by(f.w.list(),'legacy'),m=f.w.memory(new URLSearchParams({person:p.id}));assert.equal(m.sections[0].thoughts[0].text,'LEGACY-THOUGHT');assert.equal(m.sections[0].operation_uid,null);
  f.histories.legacy.push({role:'user',text:'KNOWN-PRIVATE',ts:2,source:f.scopes.p1});f.save('history_v2.json',f.histories);
  const split=f.w.list().people.find(p=>p.sources.some(o=>o.original_uid==='legacy'&&o.legacy));
  assert.ok(!JSON.stringify(f.w.memory(new URLSearchParams({person:split.id}))).includes('LEGACY-THOUGHT'));
});
test('later contradictory platform evidence separates self linked sources instead of displaying both as one conflicted person',t=>{
  const f=fixture(t);directory(f);const profiles={version:1,sources:{}};
  for(const [uid,user] of [['p1','private-A'],['g1','different-private-user']])profiles.sources[uid]={source:f.scopes[uid],app:'fixture-app',observed_at:30,message_id:'profile',identity:{namespace:'qq_user_openid',value:user,basis:uid==='p1'?'qq_author_user':'qq_author_pair'}};
  f.save('workbench_profiles_v1.json',profiles);const r=f.w.list();assert.notEqual(by(r,'p1').id,by(r,'g1').id);assert.equal(by(r,'g1').conflict,true);
});
test('a legacy archive and a known person cannot both claim the same original notes file without identity proof',t=>{
  const f=fixture(t),key='p2_'+hash(['qq_official','fixture-bot','self','member-A-1']);
  f.histories[key]=[{role:'user',text:'UNSCOPED-OLD',ts:1}];f.save('history_v2.json',f.histories);
  fs.mkdirSync(path.join(f.data,'memories'));fs.writeFileSync(path.join(f.data,'memories',key+'.md'),'UNCLAIMED-NOTES');
  const list=f.w.list(),known=by(list,'g1'),legacy=by(list,key);assert.notEqual(known.id,legacy.id);
  for(const p of [known,legacy])assert.ok(!JSON.stringify(f.w.memory(new URLSearchParams({person:p.id}))).includes('UNCLAIMED-NOTES'));
});
