// Management-only identity associations. Never used by bot authorization/routing.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {atomicJson}=require('./state-bridge');
const hash=value=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
const decisionKeys=o=>[o.base,...(o.identity_origin?[o.identity_origin]:[])];
const fail=message=>{throw Object.assign(new Error(message),{statusCode:400});};
function readBounded(file,fallback,max=32*1024*1024){
  try{if(fs.statSync(file).size>max)fail('工作台读取上限已达到，请缩小原始数据后重试；未修改记录');
    return JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));
  }catch(error){if(error.code==='ENOENT')return fallback;throw error;}
}
function sourceValid(s){return s&&['platform','instance','bot','sender'].every(k=>typeof s[k]==='string'&&s[k].length>0&&s[k].length<=256)&&
  typeof s.private==='boolean'&&typeof s.group==='string'&&(s.private?s.group==='':s.group.length>0);}
function same(a,b){return sourceValid(a)&&['platform','instance','bot','sender','group','private'].every(k=>a[k]===b[k]);}
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
  return {profile:nickname||null,group_card:s.private?null:card,observed_app:text(p.app)?p.app:'',identity_key:valid?hash([s.platform,s.instance,p.app,i.namespace,i.value]):'',
    identity_origin:qq&&text(p.app)?hash([s.platform,s.instance,p.app,s.private?'user_openid':'member_openid',s.group,s.sender]):'',
    identity_domain:valid?hash([s.platform,s.instance,p.app,i.namespace]):'',identity_value:valid?i.value:'',
    identity_basis:valid?(qq?'平台同一 author 的 user_openid 映射（限当前应用/实例）':'OneBot 已核验 QQ 帐号（限当前机器人/实例）'):'',
    identity_conflict:p.identity_conflict===true};
}

function classify(origins,mapping){
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
  for(const group of mapping.groups){
    if(!Array.isArray(group)||group.length>20)fail('人工关联来源上限为20');
    const members=[...new Set(group)].filter(uid=>origins.has(uid)&&!origins.get(uid).legacy);
    if(members.some(uid=>claimed.has(uid)))fail('管理关联文件含重叠来源');
    if(members.length>1){members.forEach(uid=>{claimed.add(uid);manual.set(uid,hash(group.slice().sort()));join(members[0],uid);});}
  }
  const conflict=rows=>{
    const domains=new Map();
    for(const o of rows){if(o.identity_conflict)return true;if(o.identity_domain){
      if(domains.has(o.identity_domain)&&domains.get(o.identity_domain)!==o.identity_value)return true;
      domains.set(o.identity_domain,o.identity_value);}}
    return false;
  };
  const automatic=new Map();
  for(const o of origins.values())if(o.identity_key&&!o.legacy){
    if(!automatic.has(o.identity_key))automatic.set(o.identity_key,[]);automatic.get(o.identity_key).push(o.uid);
  }
  for(const ids of automatic.values()){
    const roots=[];
    for(const uid of ids){
      let merged=false;
      for(const previous of roots){
        if(find(uid)===find(previous)){merged=true;break;}
        const left=membersOf(uid),right=membersOf(previous);
        if(blocked(left,right)||conflict(left)||conflict(right)){
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
    const rows=members.map(uid=>origins.get(uid)),manualKeys=[...new Set(members.map(uid=>manual.get(uid)).filter(Boolean))].sort();
    const rejected=denied.some(pair=>pair.some(base=>rows.some(o=>decisionKeys(o).includes(base))));
    return {members,manual:manualKeys.length>0,manualKeys,rejected,conflict:conflict(rows)||members.some(uid=>conflicted.has(uid))};
  });
}

function createUserWorkbench(data){
  const mappingFile=path.join(data,'console_people_v1.json');
  function snapshot(){
    const sources=readBounded(path.join(data,'scopes_v2.json'),{});
    const histories={...readBounded(path.join(data,'history_all.json'),{}),...readBounded(path.join(data,'history_v2.json'),{})};
    const names=readBounded(path.join(data,'names_all.json'),{});
    const friends=readBounded(path.join(data,'friends_all.json'),{});
    const profiles=readBounded(path.join(data,'workbench_profiles_v1.json'),{version:1,sources:{}},8*1024*1024);
    if(profiles.version!==1||!profiles.sources||typeof profiles.sources!=='object'||Array.isArray(profiles.sources))fail('资料观察文件格式不受支持');
    const mapping=readBounded(mappingFile,{version:1,groups:[]},1024*1024);
    if(![1,2].includes(mapping.version)||!Array.isArray(mapping.groups)||mapping.groups.length>2000||
      (mapping.denied!==undefined&&(!Array.isArray(mapping.denied)||mapping.denied.length>10000||mapping.denied.some(pair=>!Array.isArray(pair)||pair.length!==2||pair.some(v=>!/^([a-f0-9]{64})$/.test(v))))))fail('管理关联文件格式不受支持');
    const uids=[...new Set([...Object.keys(sources),...Object.keys(histories),...Object.keys(friends),...Object.keys(names)])];
    if(uids.length>10000)fail('来源会话超过工作台一万条上限');
    const origins=new Map();
    for(const uid of uids){
      const s=sources[uid],known=sourceValid(s);
      // QQ group member_openid is documented as scoped to this group, while
      // C2C uses user_openid. Equal strings are not a cross-scene mapping.
      const base=known?hash([s.platform,s.instance,s.bot,s.private?'private':'group',s.private?'':s.group,s.sender]):hash(['legacy',uid]);
      origins.set(uid,{uid,base,legacy:!known,name:String(names[uid]||''),...(known?profileFor(s,profiles.sources[uid]):{}),kind:known?(s.private?'private':'group'):'legacy',
        platform:known?s.platform:'',instance:known?s.instance:'',bot:known?s.bot:'',sender:known?s.sender:'',group:known?s.group:'',
        label:known?`${s.private?'私聊':'群 '+s.group} / ${s.platform} / ${s.instance} / ${s.bot} / ${s.sender}`:`旧档（来源未定） / ${uid}`});
    }
    const observedApps=new Map();for(const o of origins.values())if(o.observed_app){
      if(!observedApps.has(o.base))observedApps.set(o.base,new Set());observedApps.get(o.base).add(o.observed_app);
    }
    for(const o of origins.values())if(observedApps.get(o.base)?.size>1)o.identity_conflict=true;
    const people=classify(origins,mapping).map(({members,manual,manualKeys,rejected,conflict})=>{
      const rows=members.map(uid=>origins.get(uid)).sort((a,b)=>a.uid.localeCompare(b.uid));
      const fields=rows.filter(o=>o.profile).map(o=>({...o.profile,uid:o.uid})).sort((a,b)=>b.at-a.at||String(b.message_id).localeCompare(String(a.message_id))||a.uid.localeCompare(b.uid));
      const chosen=fields.find(n=>n.kind==='qq_nickname')||fields[0],legacy=rows.every(o=>o.legacy);
      const exact=rows.length>1&&new Set(rows.map(o=>o.identity_origin||o.base)).size===1;
      const automatic=rows.length>1&&(exact||rows.some(o=>o.identity_key)),status=legacy?'legacy':conflict?'pending':manual?'manual_confirmed':automatic?'automatic_confirmed':'pending';
      const label=chosen?chosen.value+(chosen.kind==='platform_name'?'（平台用户名；QQ 昵称未核验）':''):
        '昵称未获取'+(rows.find(o=>o.name)?' / '+(legacy?'历史称呼：':'备注：')+rows.find(o=>o.name).name:'');
      const identities=[...new Set(rows.map(o=>o.identity_key).filter(Boolean))].sort();
      const key=manual?['manual',manualKeys]:status==='automatic_confirmed'?(identities.length?['identity',identities]:['source',rows[0].identity_origin||rows[0].base]):rows.map(o=>o.uid);
      let last=0;for(const uid of members)for(const row of (histories[uid]||[]).slice(-150))last=Math.max(last,Number(row.ts)||0);
      return {id:'person_'+hash(key),label,nickname:chosen?.kind==='qq_nickname'?chosen.value:null,profile_kind:chosen?.kind||null,
        profile_at:chosen?.at||null,nickname_conflict:new Set(fields.map(n=>n.kind+':'+n.value)).size>1,status,conflict,
        status_label:({legacy:'来源不明旧档',pending:'待人工确认',manual_confirmed:'人工已确认',automatic_confirmed:'自动确认'})[status],
        basis:[...(manual?['维护者明确确认的展示关联']:[]),...(exact&&!legacy?['相同原始身份（平台、实例、应用/机器人及身份域均一致）']:[]),...[...new Set(rows.map(o=>o.identity_basis).filter(Boolean))],...(rejected?['已记录人工解除/否认不关联；仅重新人工确认可移除该限制']:[]),...(conflict?['证据冲突或人工已解除/否认；不自动合回']:[])],
        manual,legacy,origin_count:rows.length,last_at:last,sources:rows.map(({base,identity_origin,identity_key,identity_domain,identity_value,identity_conflict,...o})=>o)};
    }).sort((a,b)=>b.last_at-a.last_at||a.id.localeCompare(b.id));
    return {people,sources,histories,mapping,origins,revision:hash([mapping,[...origins.values()].map(o=>[o.uid,o.base,o.identity_origin,o.observed_app,o.identity_key,o.identity_conflict])]),scope_count:uids.length};
  }
  function list(q=new URLSearchParams()){
    const s=snapshot(),limit=number(q,'limit',100,100),offset=number(q,'offset',0,10000),query=q.get('q')||'';
    if(query.length>256)fail('搜索词过长');
    const people=s.people.filter(p=>!query||JSON.stringify([p.label,p.sources]).toLowerCase().includes(query.toLowerCase()));
    return {ok:true,people:people.slice(offset,offset+limit),total:people.length,scope_count:s.scope_count,offset,
      next_offset:offset+limit<people.length?offset+limit:null,revision:s.revision};
  }
  function history(q){
    const s=snapshot(),p=s.people.find(p=>p.id===q.get('person')),mode=q.get('mode');
    if(!p||!['private','group','legacy'].includes(mode))fail('用户入口或场景无效，请刷新列表');
    const group=q.get('group')||'',limit=number(q,'limit',150,200),offset=number(q,'offset',0,10000);
    if(group&&!p.sources.some(o=>o.kind==='group'&&o.group===group))fail('群不属于该用户入口');
    const selected=p.sources.filter(o=>o.kind===mode&&(!group||o.group===group));
    const entries=[];let excluded=0;
    for(const o of selected){
      const source=s.sources[o.uid],rows=(s.histories[o.uid]||[]).slice(-150);
      const userRequests=new Set(rows.filter(r=>r.role==='user'&&same(r.source,source)).map(r=>r.request_id).filter(Boolean));
      for(const row of rows){
        if(!['user','assistant'].includes(row.role))continue;
        if(!o.legacy&&(!same(row.source,source)||(row.role==='assistant'&&(row.delivery?.status!=='accepted'||
          (mode==='group'&&!userRequests.has(row.request_id)))))){excluded++;continue;}
        entries.push({...row,scope_uid:o.uid,scene:o.kind,group:o.group,speaker:row.role==='assistant'?'机器人':
          o.profile?o.profile.value+(o.profile.kind==='platform_name'?'（平台用户名）':''):'昵称未获取'+(o.name?' / 备注：'+o.name:''),speaker_profile:o.profile||null});
      }
    }
    entries.sort((a,b)=>(Number(b.ts)||0)-(Number(a.ts)||0)||String(a.id||'').localeCompare(String(b.id||''))||a.scope_uid.localeCompare(b.scope_uid));
    return {ok:true,person:p.id,mode,group,entries:entries.slice(offset,offset+limit),count:entries.length,next_offset:offset+limit<entries.length?offset+limit:null,
      recent_only:true,per_scope_limit:150,source_count:selected.length,excluded_unverified:excluded};
  }
  function mutate(operation,body){
    if(!body||typeof body!=='object'||Array.isArray(body))fail('关联请求必须为对象');
    let lock;
    try{lock=fs.openSync(mappingFile+'.lock','wx');}catch(error){if(error.code==='EEXIST')throw Object.assign(new Error('关联正在被并发修改，请稍后刷新；未覆盖数据'),{statusCode:409});throw error;}
    try{
    const s=snapshot();
    if(body.confirm!==true||body.revision!==s.revision)fail('请明确确认来源；列表已变化时须刷新再关联');
    let groups=s.mapping.groups.map(g=>g.slice());
    let denied=(s.mapping.denied||[]).map(pair=>pair.slice());
    if(operation==='link'||operation==='deny'){
      const left=s.people.find(p=>p.id===body.left),right=s.people.find(p=>p.id===body.right);
      if(!left||!right||left.id===right.id||left.legacy||right.legacy)fail('只能关联两个已知来源的不同用户入口，旧档不得猜测关联');
      const members=[...new Set([...left.sources,...right.sources].map(o=>o.uid))];
      if(members.length>20)fail('每个人工关联最多20个来源');
      const a=new Set(left.sources.flatMap(o=>decisionKeys(s.origins.get(o.uid)))),b=new Set(right.sources.flatMap(o=>decisionKeys(s.origins.get(o.uid))));
      if(operation==='deny')for(const x of a)for(const y of b){if(x!==y)denied.push([x,y].sort());}
      else{
        denied=denied.filter(([x,y])=>!((a.has(x)&&b.has(y))||(a.has(y)&&b.has(x))));
        groups=groups.filter(g=>!g.some(uid=>members.includes(uid)));groups.push(members.sort());
      }
    }else{
      const p=s.people.find(p=>p.id===body.person);
      if(!p||p.sources.length<2||!p.sources.some(o=>o.uid===body.scope))fail('请选择该关联中的具体来源');
      const chosen=s.origins.get(body.scope),base=chosen.identity_origin||chosen.base;
      for(const o of p.sources)if(o.uid!==body.scope){
        const row=s.origins.get(o.uid),other=row.identity_origin||row.base;
        if(base===other)fail('同一原始身份的副本不能拆分为两个人');denied.push([base,other].sort());
      }
      groups=groups.map(g=>g.filter(uid=>uid!==body.scope)).filter(g=>g.length>1);
    }
    denied=[...new Map(denied.map(pair=>[JSON.stringify(pair),pair])).values()];
    if(groups.length>2000||denied.length>10000)fail('展示关联容量已满；未修改数据');
    const mapping={version:2,groups,denied};
    if(Buffer.byteLength(JSON.stringify(mapping))>1024*1024)fail('关联数据超过上限');
    atomicJson(mappingFile,mapping);
    return {ok:true,revision:snapshot().revision,note:'仅更新管理展示关联；原身份、权限、积分、历史及发送目标未修改'};
    }finally{fs.closeSync(lock);fs.unlinkSync(mappingFile+'.lock');}
  }
  return {list,history,link:body=>mutate('link',body),unlink:body=>mutate('unlink',body),deny:body=>mutate('deny',body)};
}
module.exports={createUserWorkbench};
