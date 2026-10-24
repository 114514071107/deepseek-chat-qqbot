// Management-only identity associations. Never used by bot authorization/routing.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {atomicJson}=require('./state-bridge');
const hash=value=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
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

function createUserWorkbench(data){
  const mappingFile=path.join(data,'console_people_v1.json');
  function snapshot(){
    const sources=readBounded(path.join(data,'scopes_v2.json'),{});
    const histories={...readBounded(path.join(data,'history_all.json'),{}),...readBounded(path.join(data,'history_v2.json'),{})};
    const names=readBounded(path.join(data,'names_all.json'),{});
    const friends=readBounded(path.join(data,'friends_all.json'),{});
    const mapping=readBounded(mappingFile,{version:1,groups:[]},1024*1024);
    if(mapping.version!==1||!Array.isArray(mapping.groups)||mapping.groups.length>2000)fail('管理关联文件格式不受支持');
    const uids=[...new Set([...Object.keys(sources),...Object.keys(histories),...Object.keys(friends),...Object.keys(names)])];
    if(uids.length>10000)fail('来源会话超过工作台一万条上限');
    const origins=new Map();
    for(const uid of uids){
      const s=sources[uid],known=sourceValid(s);
      // QQ group member_openid is documented as scoped to this group, while
      // C2C uses user_openid. Equal strings are not a cross-scene mapping.
      const base=known?hash([s.platform,s.instance,s.bot,s.private?'private':'group',s.private?'':s.group,s.sender]):hash(['legacy',uid]);
      origins.set(uid,{uid,base,legacy:!known,name:String(names[uid]||''),kind:known?(s.private?'private':'group'):'legacy',
        platform:known?s.platform:'',instance:known?s.instance:'',bot:known?s.bot:'',sender:known?s.sender:'',group:known?s.group:'',
        label:known?`${s.private?'私聊':'群 '+s.group} / ${s.platform} / ${s.instance} / ${s.bot} / ${s.sender}`:`旧档（来源未定） / ${uid}`});
    }
    const claimed=new Set(),buckets=[];
    for(const group of mapping.groups){
      if(!Array.isArray(group)||group.length>20)fail('人工关联来源上限为20');
      const members=[...new Set(group)].filter(uid=>origins.has(uid)&&!origins.get(uid).legacy);
      if(members.some(uid=>claimed.has(uid)))fail('管理关联文件含重叠来源');
      if(members.length>1){members.forEach(uid=>claimed.add(uid));buckets.push({members,manual:true});}
    }
    const automatic=new Map();
    for(const o of origins.values())if(!claimed.has(o.uid)){
      if(!automatic.has(o.base))automatic.set(o.base,[]);automatic.get(o.base).push(o.uid);
    }
    buckets.push(...[...automatic.values()].map(members=>({members,manual:false})));
    const people=buckets.map(({members,manual})=>{
      const rows=members.map(uid=>origins.get(uid)).sort((a,b)=>a.uid.localeCompare(b.uid));
      let last=0;for(const uid of members)for(const row of (histories[uid]||[]).slice(-150))last=Math.max(last,Number(row.ts)||0);
      return {id:'person_'+hash(rows.map(o=>o.uid)),label:rows.find(o=>o.name)?.name||rows[0].label,
        manual,legacy:rows.every(o=>o.legacy),origin_count:rows.length,last_at:last,sources:rows.map(({base,...o})=>o)};
    }).sort((a,b)=>b.last_at-a.last_at||a.id.localeCompare(b.id));
    return {people,sources,histories,mapping,revision:hash(mapping),scope_count:uids.length};
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
        entries.push({...row,scope_uid:o.uid,scene:o.kind,group:o.group,speaker:row.role==='assistant'?'机器人':o.name||o.sender||'旧档发言者（未核验）'});
      }
    }
    entries.sort((a,b)=>(Number(b.ts)||0)-(Number(a.ts)||0)||String(a.id||'').localeCompare(String(b.id||''))||a.scope_uid.localeCompare(b.scope_uid));
    return {ok:true,person:p.id,mode,group,entries:entries.slice(offset,offset+limit),count:entries.length,next_offset:offset+limit<entries.length?offset+limit:null,
      recent_only:true,per_scope_limit:150,source_count:selected.length,excluded_unverified:excluded};
  }
  function mutate(operation,body){
    const s=snapshot();
    if(body.confirm!==true||body.revision!==s.revision)fail('请明确确认来源；列表已变化时须刷新再关联');
    let groups=s.mapping.groups.map(g=>g.slice());
    if(operation==='link'){
      const left=s.people.find(p=>p.id===body.left),right=s.people.find(p=>p.id===body.right);
      if(!left||!right||left.id===right.id||left.legacy||right.legacy)fail('只能关联两个已知来源的不同用户入口，旧档不得猜测关联');
      const members=[...new Set([...left.sources,...right.sources].map(o=>o.uid))];
      if(members.length>20)fail('每个人工关联最多20个来源');
      groups=groups.filter(g=>!g.some(uid=>members.includes(uid)));groups.push(members.sort());
    }else{
      const p=s.people.find(p=>p.id===body.person);
      if(!p||!p.manual||!p.sources.some(o=>o.uid===body.scope))fail('请选择该人工关联中的具体来源');
      groups=groups.map(g=>g.filter(uid=>uid!==body.scope)).filter(g=>g.length>1);
    }
    const mapping={version:1,groups};
    if(Buffer.byteLength(JSON.stringify(mapping))>1024*1024)fail('关联数据超过上限');
    atomicJson(mappingFile,mapping);
    return {ok:true,revision:hash(mapping),note:'仅更新管理展示关联；原身份、权限、积分、历史及发送目标未修改'};
  }
  return {list,history,link:body=>mutate('link',body),unlink:body=>mutate('unlink',body)};
}
module.exports={createUserWorkbench};
