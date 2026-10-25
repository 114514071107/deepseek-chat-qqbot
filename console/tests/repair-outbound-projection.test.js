const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createUserWorkbench}=require('../user-workbench'),{seed}=require('./workbench-fixture');
test('assistant-only archive stays inspectable without inventing a pending person or conversation',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-bot-only-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const source={platform:'qq_official',instance:'fixture',bot:'bot',sender:'counterparty',group:'group-A',private:false,message_id:''};
 fs.writeFileSync(path.join(root,'history_all.json'),JSON.stringify({botOnly:[{id:'old-out',role:'assistant',text:'PRESERVE ME',source,ts:1}]}));
 const w=createUserWorkbench(root),list=w.list();assert.equal(list.counts.pending_sources,0);assert.equal(list.counts.conversation_sources,0);assert.equal(list.total,0);
 assert.equal(list.outbound_archives[0].uid,'botOnly');assert.equal(w.outbound(new URLSearchParams({uid:'botOnly'})).entries[0].text,'PRESERVE ME');
});
test('a matching frozen receipt recovers an assistant row into its unique existing destination without altering raw history',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-receipt-recovery-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const source={platform:'qq_official',instance:'fixture',bot:'bot',sender:'counterparty',group:'group-A',private:false,message_id:''};
 const provenance={scope_key:'oldOut',source,target:{platform:'qq_official',instance:'fixture',bot:'bot',kind:'group',address:'group-A'},mode:'proactive',trigger:'proactive',request_id:'',job_id:'original-job'};
 fs.writeFileSync(path.join(root,'scopes_v2.json'),JSON.stringify({existing:{...source,message_id:'in'}}));
 fs.writeFileSync(path.join(root,'history_all.json'),JSON.stringify({oldOut:[{id:'old-out',role:'assistant',text:'RECOVER RECEIPT',ts:2,delivery:{status:'accepted',message_id:'platform-out',attempt_id:'attempt'}}]}));
 fs.writeFileSync(path.join(root,'delivery_receipts_v2.json'),JSON.stringify({oldOut:[{attempt_id:'attempt',message_id:'platform-out',status:'accepted',provenance}]}));
 const w=createUserWorkbench(root),list=w.list();assert.equal(list.counts.pending_sources,1);assert.equal(list.counts.conversation_sources,1);assert.equal(list.outbound_archives.length,0);
 const history=w.history(new URLSearchParams({person:list.people[0].id,mode:'group'}));assert.equal(history.entries[0]?.text,'RECOVER RECEIPT');assert.match(history.entries[0].source_projection.basis,/回执/);assert.equal(history.entries[0].provenance.job_id,'original-job');
 assert.equal(JSON.parse(fs.readFileSync(path.join(root,'history_all.json'),'utf8')).oldOut[0].source,undefined);
});
test('verified proactive group delivery remains in its conversation without inventing a user task',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-outbound-projection-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const f=seed(root),s=f.scopes.g1,provenance={scope_key:'g1',source:s,target:{platform:s.platform,instance:s.instance,bot:s.bot,kind:'group',address:s.group},mode:'proactive',trigger:'proactive',request_id:'',job_id:'job-A'};
 const row={id:'proactive',role:'assistant',text:'GROUP-ANNOUNCEMENT',ts:200,source:s,request_id:'correlation-only',provenance,delivery:{status:'accepted',message_id:'proactive-platform-id',attempt_id:'attempt-A'}};
 f.histories.g1.push(row);f.save('history_v2.json',f.histories);
 f.save('delivery_receipts_v2.json',{g1:[{attempt_id:'unknown-A',status:'unknown',provenance},{attempt_id:'failed-A',status:'failed',provenance}]});
 const w=createUserWorkbench(f.data),list=w.list(),p=list.people.find(p=>p.sources.some(o=>o.uid==='g1'));
 const history=w.history(new URLSearchParams({person:p.id,mode:'group'}));
 assert.ok(history.entries.some(r=>r.id==='proactive'&&r.role==='assistant'&&r.provenance.request_id===''));
 assert.deepEqual(history.delivery_outcomes.map(r=>r.status).sort(),['failed','unknown']);
 const counts=list.counts;f.histories.g1.push({...row,id:'bad-target',text:'MISMATCHED',delivery:{status:'accepted',message_id:'another'},provenance:{...provenance,target:{...provenance.target,address:'foreign-group'}}});f.save('history_v2.json',f.histories);
 const again=w.history(new URLSearchParams({person:p.id,mode:'group'}));assert.ok(!again.entries.some(r=>r.id==='bad-target'));
 assert.deepEqual(w.list().counts,counts);
});
