const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {seed}=require('./workbench-fixture'),{createUserWorkbench}=require('../user-workbench');
test('two groups with multiple actors are two group entries and a private chat stays separate despite old mappings',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-conversations-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));const f=seed(root);
 f.scopes.g3={...f.scopes.g1,sender:'member-b'};f.histories.g3=[{id:'gb',role:'user',text:'GROUP-B',ts:20,source:f.scopes.g3}];f.save('scopes_v2.json',f.scopes);f.save('history_v2.json',f.histories);
 f.save('console_people_v1.json',{version:2,groups:[['p1','g1','g2','g3','other']],denied:[]});f.save('union_rollout_v1.json',{invalid:'obsolete configuration must be inert'});
 const w=createUserWorkbench(f.data),r=w.list();assert.equal(r.people.filter(p=>p.kind==='group').length,2);assert.equal(r.people.filter(p=>p.kind==='private').length,2);
 const g=r.people.find(p=>p.kind==='group'&&p.sources[0].group==='group-one');assert.equal(g.sources.length,1);const h=w.history(new URLSearchParams({person:g.id,mode:'all'}));
 assert.ok(h.entries.some(e=>e.text==='GROUP-B'));assert.ok(h.entries.some(e=>e.text==='SYNTHETIC-g1'));assert.ok(!JSON.stringify(h).includes('SYNTHETIC-p1'));assert.equal(new Set(h.entries.filter(e=>e.role==='user').map(e=>e.speaker)).size,3);
 assert.equal(w.list(new URLSearchParams({category:'group'})).total,2);assert.equal(w.list(new URLSearchParams({category:'private'})).total,2);
 assert.throws(()=>w.link({}),/不再|取消|不支持/);
});

function setup(t){const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-session-contract-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));const f=seed(root);return {...f,w:createUserWorkbench(f.data)};}
test('recent cap, paging, search and stable outbound duplicate projection agree without deleting equal text new events',t=>{
 const f=setup(t);f.histories.other=Array.from({length:170},(_,i)=>({id:'row'+i,role:'user',text:'SAME-TEXT',ts:i,source:{...f.scopes.other,message_id:'m'+i}}));f.save('history_v2.json',f.histories);
 const p=f.w.list().people.find(p=>p.sources[0].kind==='private'&&p.sources[0].uid.includes('p2_')&&f.w.history(new URLSearchParams({person:p.id})).entries.some(r=>r.id==='row169'));
 const q=new URLSearchParams({person:p.id,limit:'100',q:'SAME-TEXT'});const a=f.w.history(q);assert.equal(a.count,150);assert.equal(a.entries.length,100);q.set('offset',String(a.next_offset));const b=f.w.history(q);assert.equal(b.entries.length,50);assert.equal(new Set([...a.entries,...b.entries].map(r=>r.view_key)).size,150);
});
test('private memory remains distinct from group memory; obsolete mappings never grant access',t=>{
 const f=setup(t),list=f.w.list();fs.mkdirSync(path.join(f.data,'memories'));for(const p of list.people)fs.writeFileSync(path.join(f.data,'memories',p.id+'.md'),p.id);
 for(const p of list.people){const m=f.w.memory(new URLSearchParams({person:p.id}));assert.equal(m.sections[0].notes[0].text,p.id);for(const other of list.people.filter(x=>x.id!==p.id))assert.ok(!JSON.stringify(m).includes(other.id));}
 assert.throws(()=>f.w.memory(new URLSearchParams({person:'person_old'})),/不存在/);
});
test('same bare group ID in different bot, platform and instance never merges',t=>{
 const f=setup(t);for(const [i,patch]of [{bot:'other'},{instance:'other'},{platform:'other'}].entries()){f.scopes['domain'+i]={...f.scopes.g1,...patch};}
 f.save('scopes_v2.json',f.scopes);assert.equal(f.w.list(new URLSearchParams({category:'group'})).total,5);
});
test('ambiguous old private/member memory is excluded until explicit cleanup',t=>{
 const f=setup(t);f.scopes.g1.sender=f.scopes.p1.sender;f.save('scopes_v2.json',f.scopes);const p=f.w.list().people.find(p=>p.kind==='private'&&p.sources[0].label==='私聊用户'&&f.w.history(new URLSearchParams({person:p.id})).entries.some(r=>r.text==='SYNTHETIC-p1'));fs.mkdirSync(path.join(f.data,'memories'));fs.writeFileSync(path.join(f.data,'memories',p.id+'.md'),'OLD-SHARED-SECRET');assert.ok(!JSON.stringify(f.w.memory(new URLSearchParams({person:p.id}))).includes('OLD-SHARED-SECRET'));
});

test('unbound accepted group output is excluded and conflicting stable versions stay auditable',t=>{
 const f=setup(t),g=f.w.list().people.find(p=>p.kind==='group'&&p.sources[0].group==='group-one');let h=f.w.history(new URLSearchParams({person:g.id}));assert.ok(!JSON.stringify(h).includes('UNBOUND-ASSISTANT'));
 f.histories.alias=[{...f.histories.g1[1],text:'CONFLICTING-STABLE-ANSWER'}];f.save('history_v2.json',f.histories);h=f.w.history(new URLSearchParams({person:g.id}));assert.equal(h.entries.filter(r=>r.id==='g1-a').length,1);assert.ok(JSON.stringify(h).includes('CONFLICTING-STABLE-ANSWER'));
});

test('all catalog pages remain reachable and management validation includes objects after 100',t=>{
 const f=setup(t);for(let i=0;i<115;i++)f.scopes['bulk'+i]={...f.scopes.p1,sender:'bulk-'+i};f.save('scopes_v2.json',f.scopes);
 const a=f.w.list(new URLSearchParams({limit:'100'})),b=f.w.list(new URLSearchParams({limit:'100',offset:String(a.next_offset)}));
 assert.equal(a.total,119);assert.equal(b.people.length,19);assert.equal(b.next_offset,null);assert.equal(new Set([...a.people,...b.people].map(p=>p.id)).size,119);
 const last=b.people.at(-1);assert.ok(f.w.objects().some(p=>p.id===last.id));assert.equal(f.w.history(new URLSearchParams({person:last.id})).ok,true);
});

test('group accepted output must match frozen Target, actor, request and source message',t=>{
 const f=setup(t),s=f.scopes.g1,target={platform:s.platform,instance:s.instance,bot:s.bot,kind:'group',address:s.group,message_id:s.message_id};
 const base={role:'assistant',text:'VALID-BOUND',ts:30,source:s,request_id:'request',delivery:{status:'accepted'},provenance:{scope_key:'g1',source:s,target,mode:'reply',request_id:'request'}};
 f.histories.g1.push({...base,id:'valid'},...[
  {target:{...target,address:'other-group'}},{target:{...target,bot:'other-bot'}},{target:{...target,message_id:'other-message'}},
  {source:{...s,sender:'other-member'}},{request_id:'other-request'}
 ].map((patch,i)=>({...base,id:'invalid'+i,text:'REJECT-'+i,provenance:{...base.provenance,...patch}})));
 f.save('history_v2.json',f.histories);const g=f.w.objects().find(p=>p.kind==='group'&&p.sources[0].group===s.group),h=JSON.stringify(f.w.history(new URLSearchParams({person:g.id})));
 assert.match(h,/VALID-BOUND/);assert.doesNotMatch(h,/REJECT-/);
});
