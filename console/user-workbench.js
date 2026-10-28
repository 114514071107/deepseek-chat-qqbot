// Management-only identity associations. Never used by bot authorization/routing.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {atomicJson}=require('./state-bridge');
const {collectSources}=require('./people-sources');
const hash=value=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
const at=row=>Number.isFinite(Number(row.ts))?Number(row.ts):0;
// Recovered aliases can be older than the base file. Select recent rows before paging.
const recent=rows=>rows.slice().sort((a,b)=>at(a)-at(b)||String(a.id||'').localeCompare(String(b.id||''))||hash(a).localeCompare(hash(b))).slice(-150);
const decisionKeys=o=>[o.base,...(o.identity_origin?[o.identity_origin]:[]),...(o.decision_aliases||[])];
const managementBot=(s,app)=>s.platform==='qq_official'&&app&&s.instance&&['qq_official','unknown_selfid'].includes(s.bot)?['qq_official_adapter_placeholder']:s.bot;
const fail=message=>{throw Object.assign(new Error(message),{statusCode:400});};
function readBounded(file,fallback,max=32*1024*1024){
  try{if(fs.statSync(file).size>max)fail('工作台读取上限已达到，请缩小原始数据后重试；未修改记录');
    return JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));
  }catch(error){if(error.code==='ENOENT')return fallback;throw error;}
}
function sourceValid(s){return s&&['platform','instance','bot','sender'].every(k=>typeof s[k]==='string'&&s[k].length>0&&s[k].length<=256)&&
  typeof s.private==='boolean'&&typeof s.group==='string'&&(s.private?s.group==='':s.group.length>0);}
function same(a,b){return sourceValid(a)&&sourceValid(b)&&['platform','instance','bot','sender','group','private'].every(k=>a[k]===b[k]);}
function outboundBound(row,source,origin){
  const p=row.provenance,t=p?.target;
  if(!p||!t||!same(p.source,source)||![origin.original_uid||origin.uid,...(origin.history_aliases||[])].includes(p.scope_key)||
    !['platform','instance','bot'].every(k=>t[k]===source[k])||t.kind!==(source.private?'private':'group')||
    t.address!==(source.private?source.sender:source.group))return false;
  return p.mode==='proactive'&&p.trigger==='proactive'||p.mode==='reply'&&!!p.request_id&&row.request_id===p.request_id&&t.message_id===row.source?.message_id;
}
function number(q,key,fallback,max){const raw=q.get(key);if(raw===null)return fallback;
  if(!/^\d{1,6}$/.test(raw)||Number(raw)>max||(key==='limit'&&Number(raw)<1))fail('分页参数无效');return Number(raw);}

function profileFor(s,p){
  if(!p||!same(s,p.source)||!Number.isFinite(p.observed_at)||p.observed_at<=0)return {};
  const text=v=>typeof v==='string'&&v.length>0&&v.length<=256;
  const field=(value,kind,source)=>value&&value.kind===kind&&value.source===source&&text(value.value)&&
    Number.isFinite(value.at)&&value.at>0&&value.at<=p.observed_at?value:null;
  const qq=s.platform==='qq_official',onebot=s.platform==='aiocqhttp';
  const nickname=qq?field(p.nickname,'platform_name','qq.author.username'):
    onebot?field(p.nickname,'qq_nickname','onebot.sender.nickname'):null;
  const card=field(p.group_card,'group_card',qq?'qq.member.nick':'onebot.sender.card');
  const i=p.identity,valid=i&&text(p.app)&&text(i.value)&&(
    (qq&&i.namespace==='qq_user_openid'&&i.basis===(s.private?'qq_author_user':'qq_author_pair')&&(!s.private||i.value===s.sender))||
    (onebot&&i.namespace==='onebot_qq'&&i.basis==='onebot_message_sender'&&i.value===s.sender&&p.app===s.bot&&/^\d+$/.test(i.value)));
  return {profile:nickname||null,profile_first_seen:Number.isFinite(p.first_seen_at)&&p.first_seen_at>0?p.first_seen_at:p.observed_at,
    group_card:s.private?null:card,observed_app:text(p.app)?p.app:'',identity_key:valid?hash([s.platform,s.instance,p.app,i.namespace,i.value]):'',
    identity_origin:qq&&text(p.app)?hash([s.platform,s.instance,p.app,s.private?'user_openid':'member_openid',s.group,s.sender]):'',
    identity_domain:valid?hash([s.platform,s.instance,p.app,i.namespace]):'',identity_value:valid?i.value:'',
    identity_basis:valid?(qq?'平台同一 author 的 user_openid 映射（限当前应用/实例）':'OneBot 已核验 QQ 帐号（限当前机器人/实例）'):'',
    identity_at:valid?(p.identity_observed_at||p.observed_at):null,identity_message_id:valid?(p.identity_message_id||p.message_id):'',
    identity_conflict_count:Array.isArray(p.identity_conflicts)?p.identity_conflicts.length:0,
    identity_conflict:p.identity_conflict===true};
}

function classify(origins,mapping,aliasOwners){
  const parent=new Map([...origins.keys()].map(uid=>[uid,uid])),manual=new Map(),denied=mapping.denied||[];
  const find=uid=>{let root=uid;while(parent.get(root)!==root)root=parent.get(root);while(uid!==root){const next=parent.get(uid);parent.set(uid,root);uid=next;}return root;};
  const join=(a,b)=>{a=find(a);b=find(b);if(a!==b)parent.set(b,a);};
  const membersOf=root=>[...origins.values()].filter(o=>find(o.uid)===find(root));
  const blocked=(left,right)=>{const a=new Set(left.flatMap(decisionKeys)),b=new Set(right.flatMap(decisionKeys));
    return denied.some(([x,y])=>(a.has(x)&&b.has(y))||(a.has(y)&&b.has(x)));};
  const bases=new Map(),conflicted=new Set();
  for(const o of origins.values()){
    const exact=o.identity_origin||hash([o.base,o.observed_app||'']);
    const roots=bases.get(exact)||[];let merged=false;
    for(const previous of roots){
      const left=membersOf(o.uid),right=membersOf(previous);
      if(blocked(left,right)){[...left,...right].forEach(row=>conflicted.add(row.uid));continue;}
      join(previous,o.uid);merged=true;break;
    }
    if(!merged)roots.push(o.uid);bases.set(exact,roots);
  }
  const claimed=new Set();
  const conflict=rows=>{
    const domains=new Map();
    for(const o of rows){if(o.identity_conflict)return true;if(o.identity_domain){
      if(domains.has(o.identity_domain)&&domains.get(o.identity_domain)!==o.identity_value)return true;
      domains.set(o.identity_domain,o.identity_value);}}
    return false;
  };
  for(const group of mapping.groups){
    if(!Array.isArray(group)||group.length>20)fail('人工关联来源上限为20');
    const raw=[...new Set(group)],active=raw.filter(uid=>origins.has(uid)||aliasOwners.get(uid)?.length===1);
    if(active.some(uid=>claimed.has(uid)))fail('管理关联文件含重叠来源');active.forEach(uid=>claimed.add(uid));
    const members=[...new Set(raw.map(uid=>origins.has(uid)?uid:aliasOwners.get(uid)?.length===1?aliasOwners.get(uid)[0]:null).filter(uid=>uid&&origins.has(uid)))];
    if(members.length>1||(mapping.version===2&&group.length===1&&members.length===1)){
      // Keep the original decision, but quarantine its whole component on
      // reliable counterevidence. Unproven archives cannot be assigned a side.
      const rows=[...new Set(members.flatMap(uid=>membersOf(uid)))];
      const quarantine=conflict(rows);
      members.forEach(uid=>{manual.set(uid,[...(manual.get(uid)||[]),hash(group.slice().sort())]);if(!quarantine)join(members[0],uid);});
      if(quarantine)rows.forEach(o=>conflicted.add(o.uid));
    }
  }
  const automatic=new Map();
  for(const o of origins.values())if(!o.legacy)for(const key of [o.identity_key,o.self_identity_key].filter(Boolean)){
    if(!automatic.has(key))automatic.set(key,[]);automatic.get(key).push(o.uid);
  }
  for(const ids of automatic.values()){
    const roots=[];
    for(const uid of ids){
      let merged=false;
      for(const previous of roots){
        if(find(uid)===find(previous)){merged=true;break;}
        const left=membersOf(uid),right=membersOf(previous);
        if(blocked(left,right)||conflict([...left,...right])){
          [...left,...right].forEach(o=>conflicted.add(o.uid));continue;
        }
        join(previous,uid);merged=true;break;
      }
      if(!merged)roots.push(uid);
    }
  }
  const buckets=new Map();for(const o of origins.values()){
    const root=find(o.uid);if(!buckets.has(root))buckets.set(root,[]);buckets.get(root).push(o.uid);
  }
  return [...buckets.values()].map(members=>{
    const rows=members.map(uid=>origins.get(uid)),manualKeys=[...new Set(members.flatMap(uid=>manual.get(uid)||[]))].sort();
    const rejected=denied.some(pair=>pair.some(base=>rows.some(o=>decisionKeys(o).includes(base))));
    return {members,manual:manualKeys.length>0,manualKeys,rejected,conflict:conflict(rows)||members.some(uid=>conflicted.has(uid))};
  });
}

function createUserWorkbench(data){
  const mappingFile=path.join(data,'console_people_v1.json');
  function snapshot(){
    const sources=readBounded(path.join(data,'scopes_v2.json'),{});
    const rawHistories=Object.create(null);
    for(const store of ['history_all.json','history_v2.json'])for(const [uid,rows]of Object.entries(readBounded(path.join(data,store),{}))){
      if(!Array.isArray(rows))continue;
      const earlier=rawHistories[uid]||[],seen=new Set(earlier.filter(row=>row?.id).map(row=>JSON.stringify(row)));
      rawHistories[uid]=earlier.concat(rows.filter(row=>!row?.id||!seen.has(JSON.stringify(row))));
    }
    const names=readBounded(path.join(data,'names_all.json'),{});
    const friends=readBounded(path.join(data,'friends_all.json'),{});
    const points=readBounded(path.join(data,'points_all.json'),{});
    const profiles=readBounded(path.join(data,'workbench_profiles_v1.json'),{version:1,sources:{}},8*1024*1024);
    if(profiles.version!==1||!profiles.sources||typeof profiles.sources!=='object'||Array.isArray(profiles.sources))fail('资料观察文件格式不受支持');
    const mapping=readBounded(mappingFile,{version:1,groups:[]},1024*1024);
    if(![1,2].includes(mapping.version)||!Array.isArray(mapping.groups)||mapping.groups.length>2000||
      (mapping.denied!==undefined&&(!Array.isArray(mapping.denied)||mapping.denied.length>10000||mapping.denied.some(pair=>!Array.isArray(pair)||pair.length!==2||pair.some(v=>!/^([a-f0-9]{64})$/.test(v))))))fail('管理关联文件格式不受支持');
    const {origins,metadata,archiveIndexes,aliasOwners,raw_key_count,projectedHistories:histories,projectedSources,outboundArchives}=collectSources({sources,histories:rawHistories,names,friends,points,sourceValid,profileFor,profiles:profiles.sources,receipts:readBounded(path.join(data,'delivery_receipts_v2.json'),{})});
    const directory=readBounded(path.join(data,'user_directory_v1.json'),{version:1,sources:{}},2*1024*1024);
    if(directory.version!==1||!directory.sources||typeof directory.sources!=='object'||Array.isArray(directory.sources))fail('自助身份资料格式不受支持');
    const verified=new Map();
    for(const [key,row] of Object.entries(directory.sources)){
      const a=row?.source;
      if(!sourceValid(a)||typeof row.app!=='string'||!row.app||row.app.length>256||!/^([a-f0-9]{32})$/.test(row.person)||
        !Number.isFinite(row.created_at)||row.created_at<=0||key!==hash([a.platform,a.instance,a.bot,a.private?'private':'group',a.group,a.sender,row.app]))continue;
      const base=hash([a.platform,a.instance,a.bot,a.private?'private':'group',a.group,a.sender]);
      if(!verified.has(base))verified.set(base,[]);verified.get(base).push(row);
    }
    for(const o of origins.values())if(!o.legacy){
      const matches=verified.get(o.base)||[];
      if(matches.length!==1||o.observed_app&&matches[0].app!==o.observed_app)continue;
      const row=matches[0],a=o.source,n=row.nickname;
      o.self_identity_key=hash([a.platform,a.instance,managementBot(a,row.app),row.app,'dsh_self_verified',row.person]);
      o.observed_app=row.app;
      o.identity_origin ||= hash([a.platform,a.instance,row.app,a.private?'user_openid':'member_openid',a.group,a.sender]);
      o.identity_basis=[o.identity_basis,'用户本人完成的本地称呼/关联验证（仅用于管理展示）'].filter(Boolean).join('；');
      if(n?.kind==='self_selected'&&n.source==='dsh.self_selected'&&typeof n.value==='string'&&n.value.trim()&&Array.from(n.value).length<=32&&
        !/[\p{C}]/u.test(n.value)&&Number.isFinite(n.at)&&n.at>0){o.profile={...n};o.profile_first_seen=n.at;}
    }
    const observedApps=new Map();for(const o of origins.values())if(o.observed_app){
      if(!observedApps.has(o.base))observedApps.set(o.base,new Set());observedApps.get(o.base).add(o.observed_app);
    }
    for(const o of origins.values())if(observedApps.get(o.base)?.size>1)o.identity_conflict=true;
    const people=classify(origins,mapping,aliasOwners).map(({members,manual,manualKeys,rejected,conflict})=>{
      const rows=members.map(uid=>origins.get(uid)).sort((a,b)=>a.uid.localeCompare(b.uid));
      const fields=rows.filter(o=>o.profile).map(o=>({...o.profile,uid:o.uid,first_seen_at:o.profile_first_seen||o.profile.at})).sort((a,b)=>a.first_seen_at-b.first_seen_at||a.uid.localeCompare(b.uid));
      const chosen=fields.filter(n=>n.kind==='self_selected').sort((a,b)=>b.at-a.at)[0]||fields.find(n=>n.kind==='qq_nickname')||fields[0],legacy=rows.every(o=>o.legacy);
      const exact=rows.length>1&&new Set(rows.map(o=>o.identity_origin||o.base)).size===1;
      const automatic=rows.some(o=>!o.legacy),status=conflict?'pending':manual?'manual_confirmed':legacy?'legacy':automatic?'automatic_confirmed':'pending';
      const label=chosen?chosen.value+(chosen.kind==='platform_name'?'（平台用户名；QQ 昵称未核验）':''):
        '昵称未获取'+(rows.find(o=>o.name)?' / '+(legacy?'历史称呼：':'备注：')+rows.find(o=>o.name).name:'');
      const selfIdentities=[...new Set(rows.map(o=>o.self_identity_key).filter(Boolean))].sort();
      const identities=selfIdentities.length?selfIdentities:[...new Set(rows.map(o=>o.identity_key).filter(Boolean))].sort();
      const key=manual?['manual',manualKeys,...(conflict?[rows.map(o=>o.uid).sort()]:[])]:status==='automatic_confirmed'?(identities.length?['identity',identities]:['source',rows[0].identity_origin||rows[0].base]):rows.map(o=>o.uid);
      let last=0;for(const uid of members)for(const row of histories[uid]||[])last=Math.max(last,at(row));
      return {id:'person_'+hash(key),label,display_name:chosen?.value||label,nickname:chosen?.kind==='qq_nickname'?chosen.value:null,profile_kind:chosen?.kind||null,
        profile_at:chosen?.at||null,profile_source_uid:chosen?.uid||null,nickname_conflict:new Set(fields.map(n=>n.kind+':'+n.value)).size>1,status,conflict,
        status_label:({legacy:'来源不明旧档',pending:'关联证据待核对',manual_confirmed:'人工已确认',automatic_confirmed:'自动建档'})[status],
        basis:[...(manual?['维护者明确确认的展示关联']:[]),...(exact&&!legacy?['相同原始身份（平台、实例、应用/机器人及身份域均一致）']:[]),...[...new Set(rows.map(o=>o.identity_basis).filter(Boolean))],...(rejected?['已记录人工解除/否认不关联；仅重新人工确认可移除该限制']:[]),...(conflict?['证据冲突或人工已解除/否认；不自动合回']:[])],
        category:['manual_confirmed','automatic_confirmed'].includes(status)?'confirmed':status==='legacy'?'legacy':'pending',
        manual,legacy,origin_count:rows.length,last_at:last,sources:rows.map(({source,base,decision_aliases,identity_origin,identity_key,self_identity_key,identity_domain,identity_value,identity_conflict,...o})=>o)};
    }).sort((a,b)=>b.last_at-a.last_at||a.id.localeCompare(b.id));
    const counts={confirmed_users:people.filter(p=>p.category==='confirmed').length,
      pending_sources:people.filter(p=>p.category==='pending').flatMap(p=>p.sources).filter(o=>!o.legacy).length,
      legacy_archives:[...origins.values()].filter(o=>o.legacy).length,
      unassigned_legacy_archives:people.filter(p=>p.category==='legacy').flatMap(p=>p.sources).length,
      conversation_sources:[...origins.values()].filter(o=>!o.legacy).length,metadata_keys:metadata.length,raw_keys:raw_key_count};
    const unresolved_mapping_references=new Set(mapping.groups.flat().filter(uid=>!origins.has(uid)&&aliasOwners.get(uid)?.length!==1)).size;
    const revisionFor=value=>hash([value,[...origins.values()].map(o=>[o.uid,o.base,o.identity_origin,o.observed_app,o.identity_key,o.self_identity_key,o.identity_conflict,o.index_aliases]),[...aliasOwners]]);
    return {people,sources,histories,projectedSources,outboundArchives,archiveIndexes,mapping,origins,metadata,aliasOwners,counts,unresolved_mapping_references,revisionFor,revision:revisionFor(mapping),scope_count:origins.size};
  }
  function list(q=new URLSearchParams()){
    const s=snapshot(),limit=number(q,'limit',100,100),offset=number(q,'offset',0,10000),query=q.get('q')||'';
    if(query.length>256)fail('搜索词过长');
    const category=q.get('category')||'all';if(!['all','confirmed','pending','legacy'].includes(category))fail('用户分类无效');
    const people=s.people.filter(p=>(category==='all'||p.category===category)&&(!query||JSON.stringify([p.label,p.sources]).toLowerCase().includes(query.toLowerCase())));
    const metaOffset=number(q,'metadata_offset',0,10000),metadata=s.metadata.filter(m=>!query||JSON.stringify(m).toLowerCase().includes(query.toLowerCase()));
    return {ok:true,people:people.slice(offset,offset+limit),total:people.length,scope_count:s.scope_count,offset,
      next_offset:offset+limit<people.length?offset+limit:null,revision:s.revision,counts:s.counts,unresolved_mapping_references:s.unresolved_mapping_references,
      outbound_archives:s.outboundArchives.map(({entries,...a})=>({...a,count:entries.length})),
      archive_indexes:s.archiveIndexes,
      metadata:metadata.slice(metaOffset,metaOffset+100),metadata_total:metadata.length,metadata_next_offset:metaOffset+100<metadata.length?metaOffset+100:null};
  }
  function outbound(q){const a=snapshot().outboundArchives.find(a=>a.uid===q.get('uid'));if(!a)fail('未找到待核 Bot 出站旧档');return {ok:true,source:a.source,reason:a.reason,entries:recent(a.entries)};}
  function history(q){
    const s=snapshot(),p=s.people.find(p=>p.id===q.get('person')),mode=q.get('mode');
    if(!p||!['all','private','group','legacy'].includes(mode))fail('用户入口或场景无效，请刷新列表');
    const group=q.get('group')||'',limit=number(q,'limit',150,200),offset=number(q,'offset',0,10000);
    if(group&&!p.sources.some(o=>o.kind==='group'&&o.group===group))fail('群不属于该用户入口');
    const selected=p.sources.filter(o=>(mode==='all'||o.kind===mode)&&(!group||o.group===group));
    const entries=[],delivery_outcomes=[],receipts=readBounded(path.join(data,'delivery_receipts_v2.json'),{});let excluded=0;
    for(const o of selected){
      const source=s.projectedSources[o.uid],rows=recent(s.histories[o.uid]||[]);
      const occurrences=new Map();
      const ids=new Map();for(const row of rows)if(row.id)ids.set(row.id,(ids.get(row.id)||0)+1);
      const userRequests=new Set(rows.filter(r=>r.role==='user'&&same(r.source,source)).map(r=>r.request_id).filter(Boolean));
      for(const alias of [o.original_uid||o.uid,...(o.history_aliases||[])])for(const receipt of receipts[alias]||[])if(same(receipt.provenance?.source,source))delivery_outcomes.push(receipt);
      for(const row of rows){
        if(!['user','assistant'].includes(row.role))continue;
        if(!o.legacy&&(!same(row.source,source)||(row.role==='assistant'&&(row.delivery?.status!=='accepted'||
          (row.provenance?!outboundBound(row,source,o):o.kind==='group'&&!userRequests.has(row.request_id)))))){excluded++;continue;}
        const content=row.id&&ids.get(row.id)===1?String(row.id):hash(row),occurrence=(occurrences.get(content)||0)+1;occurrences.set(content,occurrence);
        entries.push({...row,view_key:hash([o.uid,content,occurrence]),scope_uid:o.uid,scene:o.kind,group:o.group,speaker:row.role==='assistant'?'机器人':
          p.label,speaker_profile:o.profile||null});
      }
    }
    entries.sort((a,b)=>(Number(b.ts)||0)-(Number(a.ts)||0)||String(a.id||'').localeCompare(String(b.id||''))||a.scope_uid.localeCompare(b.scope_uid));
    return {ok:true,person:p.id,mode,group,entries:entries.slice(offset,offset+limit),count:entries.length,next_offset:offset+limit<entries.length?offset+limit:null,delivery_outcomes:delivery_outcomes.slice(-150),
      recent_only:true,per_scope_limit:150,source_count:selected.length,excluded_unverified:excluded};
  }
  function memory(q){
    const s=snapshot(),p=s.people.find(p=>p.id===q.get('person')),mode=q.get('mode')||'all',group=q.get('group')||'';
    if(!p||!['all','private','group','legacy'].includes(mode)||group&&!p.sources.some(o=>o.kind==='group'&&o.group===group))fail('用户入口或场景无效，请刷新列表');
    const safe=uid=>String(uid).replace(/[^A-Za-z0-9_-]/g,'_'),personal=o=>'p2_'+hash([o.platform,o.instance,o.bot,o.sender]);
    const text=file=>{try{if(fs.statSync(file).size>1024*1024)fail('记忆文件超过读取上限');return fs.readFileSync(file,'utf8');}catch(e){if(e.code==='ENOENT')return '';throw e;}};
    const allThoughts={...readBounded(path.join(data,'thoughts_all.json'),{}),...readBounded(path.join(data,'thoughts_v2.json'),{})},seen=new Set(),owners=new Map(),originalOwners=new Map();
    for(const o of s.origins.values()){const uid=o.original_uid||o.uid;originalOwners.set(uid,(originalOwners.get(uid)||0)+1);}
    for(const person of s.people)for(const o of person.sources){const k=o.legacy?(o.original_uid||o.uid):personal(o);if(!owners.has(k))owners.set(k,new Set());owners.get(k).add(person.id);}
    const sections=p.sources.filter(o=>(mode==='all'||o.kind===mode)&&(!group||o.group===group)).map(o=>{
      const uid=o.original_uid||o.uid,direct=!o.projection_only||o.legacy&&originalOwners.get(uid)===1,notesKey=o.legacy?uid:personal(o),canRead=direct||!o.legacy,notes=[];
      const ambiguous=owners.get(notesKey)?.size>1;
      if(canRead&&!ambiguous&&!seen.has(notesKey)){seen.add(notesKey);const value=text(path.join(data,'memories',safe(notesKey)+'.md'));if(value)notes.push({key:notesKey,text:value,scene:'unknown',note:'原记忆文件未逐条记录场景；此处不推断为群聊或私聊'});}
      // A split archive's unscoped metadata cannot be assigned to one projection.
      return {uid:o.uid,operation_uid:!o.projection_only?uid:null,scene:o.kind,group:o.group,label:o.kind==='private'?'私聊':o.kind==='group'?'群聊 · '+o.group:'旧档 · 场景未知',
        thoughts:direct&&Array.isArray(allThoughts[uid])?allThoughts[uid].map((row,index)=>({...row,index})).reverse():[],notes,
        session:direct?readBounded(path.join(data,'session_'+safe(uid)+'.json'),{}):{},
        memes:direct?text(path.join(data,'memes',safe(uid)+'.md')):'',
        notice:ambiguous?'该原记忆键对应多个未关联人物，暂不归属；请由本人验证关联后查看':o.projection_only?'历史派生来源；未带场景的摘要、念头与学习资料不作猜测归属':''};
    });
    return {ok:true,person:p.id,label:p.label,mode,group,sections,revision:s.revision};
  }
  function mutate(operation,body){
    if(!body||typeof body!=='object'||Array.isArray(body))fail('关联请求必须为对象');
    let lock;
    try{lock=fs.openSync(mappingFile+'.lock','wx');}catch(error){if(error.code==='EEXIST')throw Object.assign(new Error('关联正在被并发修改，请稍后刷新；未覆盖数据'),{statusCode:409});throw error;}
    try{
    const s=snapshot();
    if(body.confirm!==true||body.revision!==s.revision)fail('请明确确认来源；列表已变化时须刷新再关联');
    let groups=s.mapping.groups.map(g=>g.slice());
    const resolve=uid=>s.origins.has(uid)?uid:s.aliasOwners.get(uid)?.length===1?s.aliasOwners.get(uid)[0]:uid;
    let denied=(s.mapping.denied||[]).map(pair=>pair.slice());
    if(operation==='confirm'){
      const p=s.people.find(p=>p.id===body.person);
      if(!p||p.manual||p.sources.length!==1||p.conflict)fail('请先核对单一来源；冲突或多来源须逐项关联确认');
      groups=groups.filter(g=>!g.some(uid=>resolve(uid)===p.sources[0].uid));groups.push([p.sources[0].uid]);
    }else if(operation==='link'||operation==='deny'){
      const left=s.people.find(p=>p.id===body.left),right=s.people.find(p=>p.id===body.right);
      if(!left||!right||left.id===right.id)fail('只能明确确认两个不同展示入口；旧档仅关联人物，不回填场景');
      const members=[...new Set([...left.sources,...right.sources].map(o=>o.uid))];
      if(members.length>20)fail('每个人工关联最多20个来源');
      const a=new Set(left.sources.flatMap(o=>decisionKeys(s.origins.get(o.uid)))),b=new Set(right.sources.flatMap(o=>decisionKeys(s.origins.get(o.uid))));
      if(operation==='deny')for(const x of a)for(const y of b){if(x!==y)denied.push([x,y].sort());}
      else{
        denied=denied.filter(([x,y])=>!((a.has(x)&&b.has(y))||(a.has(y)&&b.has(x))));
        groups=groups.filter(g=>!g.some(uid=>members.includes(resolve(uid))));groups.push(members.sort());
      }
    }else{
      const p=s.people.find(p=>p.id===body.person);
      if(!p||(!p.manual&&p.sources.length<2)||!p.sources.some(o=>o.uid===body.scope))fail('请选择该关联中的具体来源');
      const chosen=s.origins.get(body.scope),base=chosen.identity_origin||chosen.base;
      for(const o of p.sources)if(o.uid!==body.scope){
        const row=s.origins.get(o.uid),other=row.identity_origin||row.base;
        if(base===other)fail('同一原始身份的副本不能拆分为两个人');denied.push([base,other].sort());
      }
      groups=groups.flatMap(g=>{if(!g.some(uid=>resolve(uid)===body.scope))return [g];const remaining=g.filter(uid=>resolve(uid)!==body.scope);return remaining.length>1?[remaining]:[];});
    }
    denied=[...new Map(denied.map(pair=>[JSON.stringify(pair),pair])).values()];
    if(groups.length>2000||denied.length>10000)fail('展示关联容量已满；未修改数据');
    const mapping={version:2,groups,denied};
    if(Buffer.byteLength(JSON.stringify(mapping))>1024*1024)fail('关联数据超过上限');
    atomicJson(mappingFile,mapping);
    return {ok:true,revision:s.revisionFor(mapping),note:'仅更新管理展示关联；原身份、权限、积分、历史及发送目标未修改'};
    }finally{fs.closeSync(lock);fs.unlinkSync(mappingFile+'.lock');}
  }
  return {list,history,memory,outbound,link:body=>mutate('link',body),unlink:body=>mutate('unlink',body),deny:body=>mutate('deny',body),confirm:body=>mutate('confirm',body)};
}
module.exports={createUserWorkbench};
