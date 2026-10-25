// Read-only management catalog. Metadata keys are not conversations or people.
const crypto=require('node:crypto');
const hash=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex');
const memoryKey=s=>'p2_'+hash([s.platform,s.instance,s.bot,s.sender]);
function collectSources({sources,histories,names,friends,points,sourceValid,profileFor,profiles}){
  const keys=[...new Set([...Object.keys(sources),...Object.keys(histories),...Object.keys(names),...Object.keys(friends),...Object.keys(points)])];
  if(keys.length>10000)throw Object.assign(new Error('来源及资料键超过工作台一万条上限'),{statusCode:400});
  const origins=new Map(),metadata=[],aliasOwners=new Map();
  for(const uid of keys){
    const s=sources[uid],rows=Array.isArray(histories[uid])?histories[uid].filter(r=>r&&['user','assistant'].includes(r.role)):[];
    const known=sourceValid(s)&&!!(s.message_id||rows.some(r=>sourceValid(r.source)&&['platform','instance','bot','sender','group','private'].every(k=>r.source[k]===s[k])));
    if(!known&&!rows.length){metadata.push({uid,label:String(names[uid]||'').slice(0,256),has_name:uid in names,has_points:uid in points,has_switches:uid in friends,has_scope:uid in sources,related_sources:[]});continue;}
    const base=known?hash([s.platform,s.instance,s.bot,s.private?'private':'group',s.private?'':s.group,s.sender]):hash(['legacy',uid]);
    origins.set(uid,{uid,base,legacy:!known,name:String(names[uid]||'').slice(0,256),index_aliases:[],...(known?profileFor(s,profiles[uid]):{}),kind:known?(s.private?'private':'group'):'legacy',
      platform:known?s.platform:'',instance:known?s.instance:'',bot:known?s.bot:'',sender:known?s.sender:'',group:known?s.group:'',
      user_messages:rows.filter(r=>r.role==='user').length,has_inbound:known&&!!s.message_id,
      label:known?`${s.private?'私聊':'群 '+s.group} / ${s.platform} / ${s.instance} / ${s.bot} / ${s.sender}`:`旧档（来源未定） / ${uid}`});
  }
  const memoryOwners=new Map();
  for(const [uid,o] of origins)if(!o.legacy){const key=memoryKey(sources[uid]);if(!memoryOwners.has(key))memoryOwners.set(key,[]);memoryOwners.get(key).push(uid);}
  for(const item of metadata){
    const owners=memoryOwners.get(item.uid)||[];aliasOwners.set(item.uid,owners);
    item.related_count=owners.length;item.related_sources=owners.slice(0,20);item.kind=owners.length?'derived_profile':'settings_only';
    for(const uid of owners){
      const o=origins.get(uid);o.index_aliases.push({uid:item.uid,kind:'derived_profile',related_count:owners.length,has_name:item.has_name,has_points:item.has_points});
      if(owners.length===1)o.decision_aliases=[...(o.decision_aliases||[]),hash(['legacy',item.uid])];
      if(owners.length===1&&!o.name&&item.label){o.name=item.label;o.name_basis='names_all 的精确 memory_key 资料别名；称呼性质未核验';}
    }
  }
  return {origins,metadata,aliasOwners,raw_key_count:keys.length};
}
module.exports={collectSources,memoryKey};
