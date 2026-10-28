const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {seed}=require('./workbench-fixture'),{createUserWorkbench}=require('../user-workbench');
test('stable outbound alias deduplicates before recent cap and paging while equal text events survive with conflict audit',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-outbound-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));const f=seed(root),w=createUserWorkbench(f.data);
 f.histories.alias=[{...f.histories.other[1]}];f.save('history_v2.json',f.histories);
 const p=w.list().people.find(p=>p.sources.some(o=>o.uid==='other')),q=new URLSearchParams({person:p.id,mode:'all',limit:'1'});
 let all=w.history(new URLSearchParams({person:p.id,mode:'all'}));assert.equal(all.entries.filter(r=>r.id==='other-a').length,1);assert.equal(all.count,2);
 f.histories.alias[0].text='CONFLICT-VERSION';
 f.histories.alias.push({...f.histories.other[1],id:'another-record',delivery:{status:'accepted',message_id:'different-delivery'}});f.save('history_v2.json',f.histories);
 all=w.history(new URLSearchParams({person:p.id,mode:'all'}));assert.equal(all.count,3);assert.ok(JSON.stringify(all).includes('CONFLICT-VERSION'));
 const keys=[];for(let offset=0;offset<all.count;offset++){q.set('offset',String(offset));keys.push(w.history(q).entries[0].view_key);}assert.equal(new Set(keys).size,3);
 f.histories.alias=Array.from({length:170},()=>({...f.histories.other[1]}));f.save('history_v2.json',f.histories);
 assert.equal(w.history(new URLSearchParams({person:p.id,mode:'all'})).count,2);
});
