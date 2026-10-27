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
 assert.equal(p.sources[0].kind,'private');assert.equal(g.sources[0].group,'group-A');assert.equal(p.status,'automatic_confirmed');
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
 assert.equal(list.archive_indexes.length,1);assert.equal(list.unresolved_mapping_references,1);assert.equal(list.counts.confirmed_users,2);assert.ok(list.people.every(p=>!p.manual));
});
test('source-less assistant-only history is readable outbound evidence and cannot confirm a person',t=>{
 const f=fixture(t);f.save('history_all.json',{old:[{id:'bot-only',role:'assistant',text:'BOT-ONLY',ts:1,delivery:{status:'accepted'}}]});
 const list=f.w.list();assert.equal(list.total,0);assert.equal(list.counts.confirmed_users,0);assert.equal(list.outbound_archives.length,1);
 const a=list.outbound_archives[0];assert.equal(a.source,null);assert.match(a.reason,/来源|入站/);
 assert.equal(f.w.outbound(new URLSearchParams({uid:a.uid})).entries[0].text,'BOT-ONLY');
 assert.throws(()=>f.w.confirm({person:a.uid,revision:list.revision,confirm:true}));assert.equal(f.w.list().counts.confirmed_users,0);
});
test('partial unknown mixed-file human references stay unresolved rather than shrink to one subset',t=>{
 const f=fixture(t);f.save('history_all.json',{mixed:[f.row(f.source('group-A'),'KNOWN'),{id:'unknown',role:'user',text:'UNKNOWN',ts:2}]});
 f.save('console_people_v1.json',{version:2,groups:[['mixed']],denied:[]});const before=fs.readFileSync(path.join(f.root,'console_people_v1.json'),'utf8');
 const list=f.w.list();assert.equal(list.counts.confirmed_users,1);assert.equal(list.unresolved_mapping_references,1);assert.equal(list.archive_indexes.length,1);assert.ok(list.people.every(p=>!p.manual));
 assert.equal(list.archive_indexes[0].related_sources.length,2);assert.ok(list.people.every(p=>p.sources.every(o=>o.uid!=='mixed')));
 assert.equal(fs.readFileSync(path.join(f.root,'console_people_v1.json'),'utf8'),before);
});
test('older recovered outbound aliases cannot evict newer inbound records or regress latest activity',t=>{
 const f=fixture(t),s=f.source('group-A'),provenance={scope_key:'oldOut',source:s,target:{platform:s.platform,instance:s.instance,bot:s.bot,kind:'group',address:s.group},mode:'proactive',trigger:'proactive',request_id:''};
 f.save('scopes_v2.json',{existing:s});f.save('history_all.json',{
   existing:Array.from({length:150},(_,i)=>({id:'new-'+i,role:'user',text:'NEW',ts:1000+i,source:s})),
   oldOut:Array.from({length:150},(_,i)=>({id:'old-'+i,role:'assistant',text:'OLD',ts:i,source:s,provenance,delivery:{status:'accepted',message_id:'out-'+i}}))});
 const before=fs.readFileSync(path.join(f.root,'history_all.json'),'utf8'),list=f.w.list(),p=list.people[0];
 const h=f.w.history(new URLSearchParams({person:p.id,mode:'group'}));assert.equal(h.entries.length,150);assert.ok(h.entries.every(r=>r.role==='user'));
 assert.equal(h.entries[0].ts,1149);assert.equal(p.last_at,1149);assert.equal(h.next_offset,null);
 assert.equal(fs.readFileSync(path.join(f.root,'history_all.json'),'utf8'),before);
});
