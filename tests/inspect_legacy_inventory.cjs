// Read-only inventory. Only anonymous counts leave this process; no SQLite.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {createUserWorkbench}=require('../console/user-workbench');
const data=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]);
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const files=fs.readdirSync(data).filter(n=>/^(history|scopes|groups|workbench_profiles|console_people|user_directory|delivery_receipts|names|thoughts)/.test(n)&&/\.(json|jsonl)$/.test(n)).map(n=>path.join(data,n));
for(const folder of ['memories','memes'])if(fs.existsSync(path.join(data,folder)))for(const name of fs.readdirSync(path.join(data,folder)))if(fs.statSync(path.join(data,folder,name)).isFile())files.push(path.join(data,folder,name));
for(const name of fs.readdirSync(data))if(/^session_.*\.json$/.test(name))files.push(path.join(data,name));
const before=new Map(files.map(p=>[p,sha(p)])),w=createUserWorkbench(data),list=w.list();
const rows=list.people.map((p,i)=>{const m=w.memory(new URLSearchParams({person:p.id}));return {person:'P'+String(i+1).padStart(2,'0'),status:p.status,conflict:p.conflict,nickname_kind:p.profile_kind||'missing',private_sources:p.sources.filter(s=>s.kind==='private').length,group_sources:p.sources.filter(s=>s.kind==='group').length,unknown_archives:p.sources.filter(s=>s.legacy).length,manual_decision:p.manual,natural_person_evidence:p.manual?'requires_original_confirmation_evidence':p.sources.length===1&&!p.legacy?'single_trusted_source':'requires_verification',notes_files:m.sections.flatMap(s=>s.notes).length};});
const stores={};for(const name of ['history_all.json','history_v2.json','scopes_v2.json','workbench_profiles_v1.json','console_people_v1.json','user_directory_v1.json','delivery_receipts_v2.json']){
 const p=path.join(data,name);if(!fs.existsSync(p)){stores[name]={exists:false};continue;}const value=JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
 stores[name]={exists:true,entries:Object.keys(value.sources||value).length};if(name.startsWith('history'))stores[name].rows=Object.values(value).reduce((n,a)=>n+(Array.isArray(a)?a.length:0),0);
}
for(const name of ['history_archive.jsonl','history_archive_v2.jsonl']){
 const p=path.join(data,name);if(!fs.existsSync(p)){stores[name]={exists:false};continue;}
 const rows=fs.readFileSync(p,'utf8').split(/\r?\n/).filter(Boolean).map(s=>JSON.parse(s));stores[name]={exists:true,lines:rows.length,with_source:rows.filter(r=>r.source).length,request_states:rows.filter(r=>r.role==='request_state').length};
}
const result={counts:list.counts,people:rows,total:list.total,unresolved_mapping_references:list.unresolved_mapping_references,outbound_only_archives:list.outbound_archives.length,stores,files_read:files.length,read_hashes_unchanged:files.every(p=>sha(p)===before.get(p)),sqlite_connected:false,real_data_written:false};
fs.writeFileSync(out,JSON.stringify(result,null,2));console.log(JSON.stringify({people:rows.length,counts:result.counts,unchanged:result.read_hashes_unchanged}));
