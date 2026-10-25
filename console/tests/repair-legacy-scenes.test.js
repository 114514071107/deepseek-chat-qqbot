const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createUserWorkbench}=require('../user-workbench');
function fixture(t){const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-legacy-scenes-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const save=(n,v)=>fs.writeFileSync(path.join(root,n),JSON.stringify(v)),w=createUserWorkbench(root);
 const source=(group='')=>({platform:'qq_official',instance:'fixture',bot:'bot',sender:'member',group,private:!group,message_id:'inbound'});
 const row=(source,text,role='user')=>({id:text,role,text,ts:100,source,request_id:'request',...(role==='assistant'?{delivery:{status:'accepted',message_id:'out'}}:{})});
 return {root,save,w,source,row};}
test('historical private and group rows recover scene without scope table or data writes',t=>{
 const f=fixture(t);f.save('history_all.json',{oldPrivate:[f.row(f.source(),'PRIVATE')],oldGroup:[f.row(f.source('group-A'),'GROUP')]});
 const before=fs.readFileSync(path.join(f.root,'history_all.json'),'utf8'),list=f.w.list();
 const p=list.people.find(p=>p.sources.some(o=>o.uid==='oldPrivate')),g=list.people.find(p=>p.sources.some(o=>o.uid==='oldGroup'));
 assert.equal(p.sources[0].kind,'private');assert.equal(g.sources[0].group,'group-A');assert.equal(p.status,'pending');
 assert.equal(p.sources[0].projection_only,true);assert.match(p.sources[0].scene_basis,/source/);
 assert.equal(f.w.history(new URLSearchParams({person:p.id,mode:'private'})).entries[0].text,'PRIVATE');
 assert.equal(fs.readFileSync(path.join(f.root,'history_all.json'),'utf8'),before);
});
test('mixed legacy file partitions per record, preserving unknown records and manual person confirmation',t=>{
 const f=fixture(t);f.save('history_all.json',{mixed:[f.row(f.source(),'PRIVATE'),f.row(f.source('group-A'),'GROUP'),{id:'unknown',role:'user',text:'UNKNOWN',ts:101}]});
 let list=f.w.list();assert.equal(list.counts.conversation_sources,2);assert.equal(list.counts.legacy_archives,1);
 const origins=list.people.flatMap(p=>p.sources);assert.equal(origins.length,3);assert.ok(origins.every(o=>o.original_uid==='mixed'));
 for(const [mode,text]of [['private','PRIVATE'],['group','GROUP'],['legacy','UNKNOWN']]){
   const p=list.people.find(p=>p.sources.some(o=>o.kind===mode));
   assert.deepEqual(f.w.history(new URLSearchParams({person:p.id,mode})).entries.map(r=>r.text),[text]);
 }
 f.save('console_people_v1.json',{version:1,groups:[['mixed']]});list=f.w.list();
 assert.equal(list.counts.conversation_sources,2);assert.equal(list.counts.legacy_archives,1);
});
test('a scope table entry never reassigns mixed records, and bare sender or last route is insufficient',t=>{
 const f=fixture(t);f.save('scopes_v2.json',{mixed:f.source('group-A')});f.save('umo_all.json',{bare:'fixture:FriendMessage:bare'});
 f.save('history_all.json',{mixed:[f.row(f.source('group-A'),'A'),f.row(f.source('group-B'),'B'),{role:'user',text:'MISSING'}],bare:[{role:'user',text:'BARE'}]});
 const list=f.w.list();assert.equal(list.counts.conversation_sources,2);assert.equal(list.counts.legacy_archives,2);
 assert.ok(list.people.flatMap(p=>p.sources).filter(o=>o.kind==='legacy').every(o=>o.scene_reason));
});
test('overlapping old and v2 stores preserve distinct records and deduplicate identical entry ids',t=>{
 const f=fixture(t),a=f.row(f.source(),'OLD'),b=f.row(f.source('group-A'),'NEW');
 f.save('history_all.json',{mixed:[a]});f.save('history_v2.json',{mixed:[b]});
 const list=f.w.list();assert.equal(list.counts.conversation_sources,2);
 const entries=list.people.flatMap(p=>['private','group'].flatMap(mode=>f.w.history(new URLSearchParams({person:p.id,mode})).entries));
 assert.deepEqual(entries.map(r=>r.text).sort(),['NEW','OLD']);
});
test('validated v2 keys and unique triggering requests recover source-less rows in the readable projection',t=>{
 const f=fixture(t),crypto=require('node:crypto'),s=f.source(),uid='p2_'+crypto.createHash('sha256').update(JSON.stringify([s.platform,s.instance,s.bot,s.sender])).digest('hex');
 f.save('scopes_v2.json',{[uid]:s});f.save('history_all.json',{[uid]:[{id:'source-less-user',role:'user',text:'RECOVER-KEY',request_id:'r',ts:1}]});
 let list=f.w.list(),p=list.people.find(p=>p.sources.some(o=>o.uid===uid));
 const recovered=f.w.history(new URLSearchParams({person:p.id,mode:'private'})).entries[0];
 assert.equal(recovered?.text,'RECOVER-KEY');assert.equal(recovered.source.message_id,'','scene recovery cannot invent the historical trigger from latest scope');
 f.save('history_all.json',{other:[f.row(f.source('group-A'),'GROUP-USER'),{id:'missing-source-assistant',role:'assistant',text:'RECOVER-REQUEST',request_id:'request',ts:101,delivery:{status:'accepted',message_id:'out'}}]});
 list=f.w.list();p=list.people.find(p=>p.sources.some(o=>o.uid==='other'));
 const rows=f.w.history(new URLSearchParams({person:p.id,mode:'group'})).entries;
 assert.ok(rows.some(r=>r.text==='RECOVER-REQUEST'&&r.source_projection?.basis.includes('request_id')));
 assert.equal(JSON.parse(fs.readFileSync(path.join(f.root,'history_all.json'),'utf8')).other[1].source,undefined);
});
test('indistinguishable legacy rows keep multiplicity while stable exact copies across stores deduplicate',t=>{
 const f=fixture(t),row={role:'user',text:'REPEATED',ts:1,source:f.source()},stable={...row,id:'stable'};
 f.save('history_all.json',{legacy:[row,row,stable]});f.save('history_v2.json',{legacy:[stable]});
 const list=f.w.list(),p=list.people[0],history=f.w.history(new URLSearchParams({person:p.id,mode:'private'}));
 assert.equal(history.entries.length,3);assert.equal(new Set(history.entries.map(r=>r.view_key)).size,3);
});
test('fully identified mixed archives retain an ambiguous file index without becoming settings-only metadata',t=>{
 const f=fixture(t);f.save('history_all.json',{mixed:[f.row(f.source(),'P'),f.row(f.source('group-A'),'G')]});
 f.save('console_people_v1.json',{version:2,groups:[['mixed']],denied:[]});
 const list=f.w.list();assert.equal(list.counts.conversation_sources,2);assert.equal(list.counts.metadata_keys,0);
 assert.equal(list.archive_indexes.length,1);assert.equal(list.unresolved_mapping_references,1);assert.equal(list.counts.confirmed_users,0);
});
