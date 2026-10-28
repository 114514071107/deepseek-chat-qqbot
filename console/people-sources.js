// Source-bound history projection only; no person directory or profile aliases.
const crypto=require('node:crypto');
const hash=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex');
function collectSources({sources,histories,sourceValid,receipts={}}){
  const keys=[...new Set([...Object.keys(sources),...Object.keys(histories)])];
  if(keys.length>10000)throw Object.assign(new Error('来源及资料键超过工作台一万条上限'),{statusCode:400});
  const origins=new Map(),projectedHistories=Object.create(null),projectedSources=Object.create(null),outboundArchives=[];
  const identity=s=>[s.platform,s.instance,s.bot,s.private?'private':'group',s.private?'':s.group,s.sender];
  const nativeKey=s=>(s.private?'p2_':'c2_')+hash(s.private?[s.platform,s.instance,s.bot,s.sender]:[s.platform,s.instance,s.bot,s.group,s.sender]);
  for(const uid of keys){
    const stored=sources[uid],rows=Array.isArray(histories[uid])?histories[uid].filter(r=>r&&['user','assistant'].includes(r.role)):[];
    const tableKnown=sourceValid(stored)&&!!stored.message_id;
    if(!tableKnown&&!rows.length)continue;
    const requests=new Map();for(const row of rows)if(row.role==='user'&&row.request_id&&sourceValid(row.source)){
      if(!requests.has(row.request_id))requests.set(row.request_id,new Map());requests.get(row.request_id).set(hash(identity(row.source)),row.source);
    }
    const buckets=new Map();
    for(const row of rows){
      let s=null,basis='',provenance=null;
      const receipt=row.role==='assistant'&&row.delivery?.attempt_id?(receipts[uid]||[]).find(r=>{
        const p=r.provenance,t=p?.target,a=p?.source;
        return r.attempt_id===row.delivery.attempt_id&&r.status===row.delivery.status&&(!row.delivery.message_id||r.message_id===row.delivery.message_id)&&
          p?.scope_key===uid&&sourceValid(a)&&t&&['platform','instance','bot'].every(k=>a[k]===t[k])&&
          t.kind===(a.private?'private':'group')&&t.address===(a.private?a.sender:a.group);
      }):null;
      if(receipt){s=receipt.provenance.source;provenance=receipt.provenance;basis='同 attempt/message_id 回执冻结的 source 与 Target 一致';}
      else if(sourceValid(row.source)){s=row.source;basis='逐条 record.source 原始来源';}
      else if(!row.source&&tableKnown&&uid===nativeKey(stored)){s={...stored,message_id:'',event_id:'',received_at:0};basis='原 scope 表与 v2 生成键哈希逐项核对（旧消息标识未恢复）';}
      else if(!row.source&&row.role==='assistant'&&requests.get(row.request_id)?.size===1){s=[...requests.get(row.request_id).values()][0];basis='同文件唯一原请求 request_id 的 user.source';}
      const signature=s?hash(identity(s)):'unknown';
      if(!buckets.has(signature))buckets.set(signature,{source:s,rows:[],basis});
      const recovered=s&&(!sourceValid(row.source)||hash(identity(row.source))!==signature||row.source.message_id!==s.message_id);
      buckets.get(signature).rows.push(recovered||receipt?{...row,source:s,...(provenance?{provenance}:{}),...(recovered?{source_projection:{basis,original_uid:uid,...(row.source?{original_source:row.source}:{})}}:{})}:row);
    }
    if(tableKnown&&!buckets.has(hash(identity(stored))))buckets.set(hash(identity(stored)),{source:stored,rows:[],basis:'已接收入站的原 scope 表；该来源暂无匹配的已存记录'});
    const preferred=tableKnown&&buckets.has(hash(identity(stored)))?hash(identity(stored)):buckets.size===1?[...buckets.keys()][0]:null;
    for(const [signature,bucket]of buckets){
      const id=signature===preferred?uid:'legacy_'+hash([uid,signature]),s=bucket.source,known=!!s;
      if(bucket.rows.length&&bucket.rows.every(r=>r.role==='assistant')&&!(tableKnown&&known&&signature===hash(identity(stored)))){
        outboundArchives.push({uid:id,original_uid:uid,source:s,entries:bucket.rows,reason:'仅有 Bot 出站记录，缺少已核入站来源；不将发送者视为新用户'});continue;
      }
      const base=known?signature:hash(['legacy',uid]);
      projectedHistories[id]=bucket.rows; if(known)projectedSources[id]=s;
      if(origins.size>=10000)throw Object.assign(new Error('逐条场景来源超过工作台一万条上限；原数据未修改'),{statusCode:400});
      origins.set(id,{uid:id,original_uid:uid,base,source:s,legacy:!known,
        projection_only:!(id===uid&&tableKnown&&signature===hash(identity(stored))),
        scene_status:known?'identified':'unknown',scene_basis:bucket.basis,
        scene_reason:known?'':rows.some(r=>r.source&&!sourceValid(r.source))?'source 字段缺项或冲突，无法恢复完整平台/实例/机器人/场景':'缺少逐条 source；裸发送者键及末次路由不能恢复私聊或具体群',
        kind:known?(s.private?'private':'group'):'legacy',
        platform:known?s.platform:'',instance:known?s.instance:'',bot:known?s.bot:'',sender:known?s.sender:'',group:known?s.group:'',
        user_messages:bucket.rows.filter(r=>r.role==='user').length,has_inbound:known&&bucket.rows.some(r=>r.role==='user'),
        label:known?`${s.private?'私聊':'群 '+s.group} / ${s.platform} / ${s.instance} / ${s.bot} / ${s.sender}`:`旧档（来源未定） / ${uid}`});
    }
  }
  for(const archive of outboundArchives.slice()){
    if(!archive.source)continue;
    const matches=[...origins.values()].filter(o=>!o.legacy&&o.base===hash(identity(archive.source)));
    if(matches.length!==1)continue;
    const o=matches[0];projectedHistories[o.uid].push(...archive.entries);
    o.history_aliases=[...(o.history_aliases||[]),archive.original_uid];
    outboundArchives.splice(outboundArchives.indexOf(archive),1);
  }
  // Canonical bucket wins over reattached outbound aliases. Only full source
  // plus stable record/attempt/platform-message evidence can collapse rows.
  // Keep divergent versions on the projected row for audit, never edit storage.
  for(const uid of Object.keys(projectedHistories)){
    const seen=new Map(),result=[];
    for(const row of projectedHistories[uid]){
      if(row.role!=='assistant'||!sourceValid(row.source)){result.push(row);continue;}
      const base=hash(identity(row.source)),keys=[['record',row.id],['attempt',row.delivery?.attempt_id],['message',row.delivery?.message_id]]
        .filter(([,value])=>typeof value==='string'&&value).map(([kind,value])=>hash([base,kind,value]));
      const existing=keys.map(k=>seen.get(k)).find(Boolean);
      if(existing){
        if(hash(row)!==existing.originalHash){
          existing.row.projection_conflicts||=[];
          if(!existing.row.projection_conflicts.some(v=>hash(v)===hash(row)))existing.row.projection_conflicts.push(row);
        }
        keys.forEach(k=>seen.set(k,existing));continue;
      }
      const copy={...row},item={row:copy,originalHash:hash(row)};result.push(copy);keys.forEach(k=>seen.set(k,item));
    }
    projectedHistories[uid]=result;
  }
  return {origins,raw_key_count:keys.length,projectedHistories,projectedSources,outboundArchives};
}
module.exports={collectSources};
