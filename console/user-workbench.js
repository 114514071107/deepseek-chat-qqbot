// Read-only conversation catalog. Actor scopes remain actor scopes for auth/quota.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {collectSources}=require('./people-sources');
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
const valid=s=>s&&['platform','instance','bot','sender'].every(k=>typeof s[k]==='string'&&s[k])&&typeof s.private==='boolean'&&typeof s.group==='string'&&(s.private?!s.group:!!s.group);
const key=s=>(s.private?'p2_':'g2_')+hash(s.private?[s.platform,s.instance,s.bot,s.sender]:[s.platform,s.instance,s.bot,s.group]);
const fail=m=>{throw Object.assign(Error(m),{statusCode:400});};
function createUserWorkbench(data){
 const read=(name,fallback={})=>{try{const f=path.join(data,name);if(fs.statSync(f).size>32*1024*1024)fail('读取超过上限');return JSON.parse(fs.readFileSync(f,'utf8').replace(/^\uFEFF/,''));}catch(e){if(e.code==='ENOENT')return fallback;throw e;}};
 const text=name=>{try{const p=path.join(data,name);if(fs.statSync(p).size>1024*1024)fail('记忆超过读取上限');return fs.readFileSync(p,'utf8');}catch(e){if(e.code==='ENOENT')return '';throw e;}};
 function snapshot(){
  const scopes=read('scopes_v2.json'),histories={...read('history_all.json'),...read('history_v2.json')};
  const c=collectSources({sources:scopes,histories,sourceValid:valid,receipts:read('delivery_receipts_v2.json')});
  const names=read('names_all.json'),profiles=read('conversation_profiles_v1.json',{sources:{}}).sources||{},groups=new Map();
  for(const o of c.origins.values()){
   if(o.legacy)continue;const s=o.source,id=key(s);
   if(!groups.has(id))groups.set(id,{id,kind:s.private?'private':'group',source:s,actors:[],entries:[],aliases:[]});
   const g=groups.get(id);g.actors.push(o.uid);g.aliases.push(o.uid,o.original_uid||o.uid,...(o.history_aliases||[]));g.entries.push(...(c.projectedHistories[o.uid]||[]));
  }
  const groupRows=read('groups_v2.json');
  for(const g of groups.values()){
   const s=g.source,p=profiles[g.id],rawName=names[g.id]||(p&&p.platform===s.platform&&p.instance===s.instance&&p.bot===s.bot&&p.kind===g.kind&&p.address===(s.private?s.sender:s.group)?p.name:'');
   g.label=rawName||((s.private?'私聊用户 · ':'群聊 · ')+(s.private?s.sender:s.group).slice(0,12));g.display_name=g.label;
   const rows=g.entries.concat(groupRows[g.id]||[]),seen=new Map();g.entries=[];
   const same=(a,b)=>valid(a)&&valid(b)&&['platform','instance','bot','sender','group','private'].every(k=>a[k]===b[k]);
   const bound=row=>{
    const p=row.provenance,t=p?.target,a=row.source;
    if(p){if(!same(p.source,a)||!g.aliases.includes(p.scope_key)||!t||!['platform','instance','bot'].every(k=>t[k]===a[k])||t.kind!==(a.private?'private':'group')||t.address!==(a.private?a.sender:a.group))return false;
     return p.mode==='proactive'&&p.trigger==='proactive'||p.mode==='reply'&&p.request_id&&row.request_id===p.request_id&&t.message_id===a.message_id;}
    return a.private||!!row.request_id&&rows.some(u=>u.role==='user'&&u.request_id===row.request_id&&same(u.source,a));
   };
   for(const row of rows){if(!valid(row.source)||key(row.source)!==g.id||!['user','assistant'].includes(row.role))continue;if(row.role==='assistant'&&(row.delivery?.status!=='accepted'||!bound(row)))continue;
    const k=row.id?JSON.stringify([row.source.platform,row.source.instance,row.source.bot,row.source.private,row.source.group,row.source.sender,row.id]):JSON.stringify(row);if(seen.has(k)){const existing=seen.get(k);if(JSON.stringify(existing)!==JSON.stringify(row)){existing.projection_conflicts||=[];if(!existing.projection_conflicts.some(v=>JSON.stringify(v)===JSON.stringify(row)))existing.projection_conflicts.push(row);}continue;}const copy={...row};seen.set(k,copy);g.entries.push(copy);}
   g.entries.sort((a,b)=>(Number(a.ts)||0)-(Number(b.ts)||0)||String(a.id||'').localeCompare(String(b.id||'')));g.entries=g.entries.slice(-150);
   g.last_at=Math.max(0,...g.entries.map(r=>Number(r.ts)||0));
   g.sources=[{uid:g.id,operation_uid:g.id,kind:g.kind,group:s.group,platform:s.platform,instance:s.instance,bot:s.bot,label:g.kind==='group'?'整个群聊':'私聊用户',legacy:false}];
   g.status_label=g.kind==='group'?'群聊':'私聊用户';g.category=g.kind;g.origin_count=1;g.features={reply:true,voice:true,proactive:g.kind==='group',...(read('friends_all.json')[g.id]||{})};
  }
  return {people:[...groups.values()].sort((a,b)=>b.last_at-a.last_at||a.id.localeCompare(b.id)),legacy_count:[...c.origins.values()].filter(o=>o.legacy).length};
 }
 const pub=({entries,actors,source,aliases,...p})=>p;
 function list(q=new URLSearchParams()){
  const s=snapshot(),query=q.get('q')||'',category=q.get('category')||'all';if(!['all','private','group'].includes(category))fail('分类无效');
  const people=s.people.filter(p=>(category==='all'||p.kind===category)&&(!query||p.label.toLowerCase().includes(query.toLowerCase())||p.id.includes(query)));
  const offset=num(q,'offset',0),limit=Math.max(1,Math.min(100,num(q,'limit',100)));return {ok:true,people:people.slice(offset,offset+limit).map(pub),total:people.length,offset,next_offset:offset+limit<people.length?offset+limit:null,counts:{private_users:s.people.filter(p=>p.kind==='private').length,groups:s.people.filter(p=>p.kind==='group').length},legacy_excluded:s.legacy_count,revision:hash(s.people.map(p=>p.id)),metadata:[],outbound_archives:[],archive_indexes:[]};
 }
 function choose(q){const p=snapshot().people.find(p=>p.id===q.get('person'));if(!p)fail('会话不存在，请刷新');return p;}
 function history(q){const p=choose(q),query=q.get('q')||'',offset=num(q,'offset',0),limit=Math.min(150,Math.max(1,num(q,'limit',150)));const rows=p.entries.filter(r=>!query||String(r.text||'').includes(query)).slice().reverse().map((r,i)=>({...r,view_key:hash([p.id,r.id||r,i]),scene:p.kind,group:p.source.group,scope_uid:p.id,speaker:r.role==='assistant'?'机器人':r.source.sender}));return {ok:true,person:p.id,entries:rows.slice(offset,offset+limit),count:rows.length,next_offset:offset+limit<rows.length?offset+limit:null,recent_only:true,per_scope_limit:150,source_count:1,delivery_outcomes:[]};}
 function memory(q){const p=choose(q),uid=p.id;const collision=p.kind==='private'&&Object.values(read('scopes_v2.json')).some(s=>valid(s)&&!s.private&&'p2_'+hash([s.platform,s.instance,s.bot,s.sender])===uid);const safe=!collision||(read('conversation_storage_v1.json').cleaned_ambiguous_private||[]).includes(uid);const notes=safe?text('memories/'+uid+'.md'):'';return {ok:true,person:uid,label:p.label,sections:[{uid,operation_uid:uid,scene:p.kind,group:p.source.group,label:p.kind==='group'?'整个群聊':'私聊用户',thoughts:safe?(read('thoughts_v2.json')[uid]||[]).map((r,index)=>({...r,index})).reverse():[],notes:notes?[{key:uid,text:notes,note:p.kind==='group'?'仅本群共同记忆':'仅本私聊记忆'}]:[],session:safe?read('session_'+uid+'.json'):{},memes:safe?text('memes/'+uid+'.md'):''} ]};}
 const retired=()=>fail('跨场景人物关联已取消，不再支持合并或确认');
 return {objects:()=>snapshot().people.map(pub),list,history,memory,outbound:retired,link:retired,unlink:retired,deny:retired,confirm:retired};
}
function num(q,k,d){const v=q.get(k);if(v===null)return d;if(!/^\d{1,6}$/.test(v))fail('分页无效');return Number(v);}
module.exports={createUserWorkbench,conversationKey:key};
