/* Existing workbench styling; associations affect display only. */
window.UserWorkbench=(()=>{
  const state={person:null,mode:'all',group:'',source:'',offset:0,listOffset:0,anchor:null,query:'',category:'all',outbound:''};
  let epoch=0,controller=null,catalog=null,saving=false,cancelReview=null;
  const outboundCache=new Map();
  const outboundHtml=uid=>(outboundCache.get(uid)||[]).map(row=>'<div data-read-key="outbound:'+esc(uid+':'+(row.id||row.ts))+'"><p class="dim">'+esc(row.delivery?.status||'投递状态未留存，不能认作成功')+' / assistant / 原始出站旧档</p>'+histEntryHtml(row)+'</div>').join('');
  const busy=()=>saving||!!document.querySelector('#people-associations[open], #people-operations[open], #people-metadata[open]');
  const leave=()=>{epoch++;if(controller)controller.abort();if(cancelReview)cancelReview();};
  const selected=()=>catalog?.people.find(p=>p.id===state.person);
  const live=id=>id===epoch&&cur==='users';
  async function get(url,signal){const r=await api(url,{signal});if(r.ok!==true)throw Error(r.error||'未取得有效响应');return r;}
  function review(operation,origins){
    const titles={link:'确认这些来源属于同一人',deny:'确认两个入口不是同一人',unlink:'解除此来源的展示关联',confirm:'确认此来源为独立用户'};
    const dialog=document.createElement('dialog');dialog.id='people-review';dialog.setAttribute('aria-labelledby','people-review-title');
    dialog.innerHTML='<form method="dialog"><h3 id="people-review-title">'+titles[operation]+'</h3><p>仅修改管理展示。认证、权限、积分、历史及发送目标保持各自来源。</p><ul class="source-list">'+origins.map(o=>'<li>'+esc(o.profile?.value||o.name||'昵称未获取')+'<br>'+esc(o.label)+'<br>场景识别：'+esc(o.scene_status==='identified'?'已识别 / '+o.scene_basis:'尚未识别 / '+o.scene_reason)+'<br>人物证据：'+esc(o.identity_basis||o.identity_reason)+(o.identity_at?' / 原观察 '+esc(fmtT(o.identity_at))+' / 消息 '+esc(o.identity_message_id):'')+(o.identity_conflict_count?' / 保留 '+o.identity_conflict_count+' 份冲突证据':'')+(o.projection_only?'<br>历史派生视图，只读，不是管理目标':'')+'<br><span class="mono">'+esc(o.uid)+'</span></li>').join('')+'</ul><p class="dim">旧档仅确认人物，原场景仍未知。解除/否认会阻止旧证据自动合回。请核对每项来源。</p><div class="row"><button class="act" id="people-review-cancel" value="cancel" autofocus>取消</button><button class="act" id="people-review-confirm" value="confirm">明确确认</button></div></form>';
    document.body.append(dialog);
    return new Promise(resolve=>{let done=false;const finish=()=>{if(done)return;done=true;const accepted=dialog.returnValue==='confirm';dialog.remove();cancelReview=null;resolve(accepted);};
      dialog.addEventListener('close',finish,{once:true});cancelReview=()=>{dialog.returnValue='cancel';dialog.close();finish();};dialog.showModal();});
  }
  function clearSource(){state.source='';curUid=null;scopeDetailVersion++;const label=$('#people-operation-source');if(label)label.textContent='未选择操作来源';const pane=$('#u-detail');if(pane)pane.innerHTML='<p class="dim">未选择操作来源。开关、积分、删除均不会作用于聚合入口；发送请到通知页另选目标。</p>';}
  async function render({refresh=false,manual=false}={}){
    if(saving)return;
    if(!refresh)leave();else if(controller)controller.abort();
    const id=epoch;controller=new AbortController();
    if(cur!=='users')return;
    if(!refresh){_lastHtml=null;$('#view').innerHTML='<div class="card" role="status">正在加载用户入口…</div>';}
    try{
      const [r,switches]=await Promise.all([get('/api/people?limit=100&offset='+state.listOffset+'&category='+state.category+(state.query?'&q='+encodeURIComponent(state.query):''),controller.signal),api('/api/switches',{signal:controller.signal})]);
      if(!live(id))return;
      const nextState={...state},nextPerson=()=>r.people.find(p=>p.id===nextState.person);
      if(nextState.anchor){nextState.person=r.people.find(p=>p.sources.some(o=>o.uid===nextState.anchor))?.id||null;nextState.anchor=null;}
      if(!r.people.some(p=>p.id===nextState.person)&&selected()){
        const previousSources=new Set(selected().sources.map(o=>o.uid));
        nextState.person=r.people.find(p=>p.sources.some(o=>previousSources.has(o.uid)))?.id||nextState.person;
      }
      if(!r.people.some(p=>p.id===nextState.person)){
        nextState.person=r.people[0]?.id||null;nextState.mode='all';
        nextState.group='';nextState.source='';nextState.offset=0;
      }
      if(nextState.group&&!nextPerson()?.sources.some(o=>o.group===nextState.group)){nextState.group='';nextState.source='';}
      const historyData=refresh&&nextPerson()?await get('/api/people/history?'+new URLSearchParams({person:nextState.person,mode:nextState.mode,group:nextState.group,limit:'150',offset:String(nextState.offset)}),controller.signal):null;
      if(!live(id))return;
      // A user may begin reviewing or typing while these requests are pending.
      if(state.outbound&&r.outbound_archives?.some(a=>a.uid===state.outbound)){const a=await get('/api/people/outbound?uid='+encodeURIComponent(state.outbound),controller.signal);if(!live(id))return;outboundCache.set(state.outbound,a.entries);}
      if(saving||refresh&&!manual&&(busy()||window.ReadingState.hasDraft($('#view'))||/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName)))return;
      nextState.outbound=state.outbound;
      if(nextState.person===state.person&&nextState.mode===state.mode&&nextState.group===state.group)nextState.source=state.source;
      Object.assign(state,nextState);catalog=r;swCache=switches;
      const reading=refresh?window.ReadingState.capture($('#view')):null,minimum=$('#view').style.minHeight;
      if(reading)$('#view').style.minHeight=$('#view').getBoundingClientRect().height+'px';
      $('#people-refresh-error')?.remove();
      const counts=r.counts;
      $('#view').innerHTML='<div class="stat-row" id="people-counts">'+[['用户',counts.confirmed_users],['关联待核来源',counts.pending_sources],['历史旧档',counts.legacy_archives],['会话来源',counts.conversation_sources]].map(([label,value])=>'<div class="stat"><div class="lb">'+label+'</div><div class="vl">'+value+'</div></div>').join('')+'</div>'+
        '<p class="dim">未知来源可能属于已有用户，以上数字不能相加作为真实人数。旧档不代表已识别的人物或场景；'+counts.metadata_keys+' 个无聊天资料键另列，不计用户。</p>'+
        (r.unresolved_mapping_references?'<p role="status">'+r.unresolved_mapping_references+' 个旧关联引用尚无法唯一对应来源，原决定已保留，请核对后重新确认。</p>':'')+
        '<form id="people-search-form" class="row"><label for="people-search">搜索用户</label><input id="people-search" maxlength="256" value="'+esc(state.query)+'" placeholder="昵称、备注或来源"><label for="people-category">分类</label><select id="people-category">'+[['all','全部分类'],['confirmed','用户'],['pending','关联证据待核对'],['legacy','历史旧档 / 来源未定']].map(([key,label])=>'<option value="'+key+'" '+(state.category===key?'selected':'')+'>'+label+'</option>').join('')+'</select><button class="act" type="submit">查找用户</button></form>'+
        [['confirmed','用户','新来源自动建档；本人验证后跨场景归到同一人。资料缺失可发送「设置称呼 你的称呼」'],['pending','关联证据待核对','仅在证据冲突或人工解除时列出；新来源自动建档，无需逐个确认'],['legacy','历史旧档 / 来源未定','有消息但无可靠场景；可人工确认人物，场景继续未知']].filter(([key])=>state.category==='all'||state.category===key).map(([key,title,note])=>'<section class="people-section" aria-label="'+title+'"><h3>'+title+'</h3><p class="dim">'+note+'</p><div class="uchips" id="people-list-'+key+'">'+r.people.filter(p=>p.category===key).map(p=>'<button type="button" class="uchip'+(p.id===state.person?' on':'')+'" aria-pressed="'+(p.id===state.person)+'" data-person="'+esc(p.id)+'"><div class="un">'+esc(p.display_name||p.label)+'</div><div class="uu">'+p.origin_count+' 个来源 / '+esc([...new Set(p.sources.map(o=>({group:'群聊',private:'私聊',legacy:'场景未知'}[o.kind])))].join('、'))+' / '+esc(p.status_label)+(p.conflict?'（证据冲突）':'')+'<br>最近活动 '+esc(fmtT(p.last_at))+'</div></button>').join('')+'</div>'+(!r.people.some(p=>p.category===key)?'<p class="dim">本页没有此类入口。</p>':'')+'</section>').join('')+
        '<p class="dim">当前筛选 '+r.total+' 个展示入口；已加载 '+r.people.length+' 个。此数不是自然人数。</p><div class="row"><button class="act" id="people-prev" '+(state.listOffset?'':'disabled')+'>上一页用户</button><button class="act" id="people-next" '+(r.next_offset===null?'disabled':'')+'>下一页用户</button></div>'+
        '<details class="card" id="people-metadata"><summary>无聊天资料键（'+r.metadata_total+'）</summary><p class="dim">这些键只用于备注、积分或设置；未列作用户，原数据未移动。精确对应多个来源时不猜测归属。</p><ul class="source-list">'+r.metadata.map(m=>'<li>'+esc(m.label||'无称呼')+' / '+(m.related_count?'精确关联 '+m.related_count+' 个来源':'未找到会话来源')+'<br><span class="mono">'+esc(m.uid)+'</span></li>').join('')+'</ul><span class="dim">最多显示 100 项；更多可按资料键搜索。</span></details><div id="people-detail"></div>';
      $('#people-archive-indexes')?.remove();
      if(r.archive_indexes?.length)$('#view').insertAdjacentHTML('beforeend','<details class="card" id="people-archive-indexes"><summary>混合旧档索引（'+r.archive_indexes.length+'）</summary><p class="dim">按记录分场景，原文件索引不计用户或纯资料；不能把整个混合文件当作一项确定人物证据。</p><ul class="source-list">'+r.archive_indexes.map(a=>'<li>'+esc(a.uid)+' → '+a.related_sources.map(esc).join('、')+'</li>').join('')+'</ul></details>');
      $('#people-outbound-archives')?.remove();
      if(r.outbound_archives?.length){
        $('#view').insertAdjacentHTML('beforeend','<details class="card" id="people-outbound-archives"><summary>仅 Bot 出站旧档（'+r.outbound_archives.length+'）</summary><p class="dim">保留原记录。目标场景与用户入站来源分开：缺少可信入站或唯一原会话时不增加用户、待确认来源或会话来源，也不猜任务。</p>'+r.outbound_archives.map(a=>'<p>'+esc(a.source?(a.source.private?'私聊目标 '+a.source.sender:'群目标 '+a.source.group):'目标来源未获取')+' / '+a.count+' 条 / '+esc(a.reason)+' <button class="act" data-outbound="'+esc(a.uid)+'">查看出站记录</button></p>').join('')+'<div id="people-outbound-records">'+outboundHtml(state.outbound)+'</div></details>');
        document.querySelectorAll('[data-outbound]').forEach(button=>button.onclick=async()=>{try{const a=await get('/api/people/outbound?uid='+encodeURIComponent(button.dataset.outbound),controller.signal);if(!live(id))return;state.outbound=button.dataset.outbound;outboundCache.set(state.outbound,a.entries);$('#people-outbound-records').innerHTML=outboundHtml(state.outbound);}catch(error){if(live(id))$('#people-outbound-records').textContent='读取失败：'+error.message;}});
      }
      document.querySelectorAll('[data-person]').forEach(button=>button.onclick=()=>{
        state.person=button.dataset.person;state.group='';state.source='';state.offset=0;curUid=null;
        const p=selected();state.mode='all';render();
      });
      $('#people-prev').onclick=()=>{state.listOffset=Math.max(0,state.listOffset-100);render();};
      $('#people-next').onclick=()=>{state.listOffset=r.next_offset;render();};
      $('#people-search-form').onsubmit=e=>{e.preventDefault();state.query=$('#people-search').value.trim();state.listOffset=0;state.person=null;clearSource();render();};
      $('#people-category').onchange=e=>{state.category=e.target.value;state.listOffset=0;state.person=null;clearSource();render();};
      if(!selected()){$('#people-detail').innerHTML='<div class="card">暂无用户来源。收到并保存消息后再刷新。</div>';if(reading)queueMicrotask(()=>{$('#view').style.minHeight=minimum;reading.restore();});return;}
      detail(id,historyData);
      if(reading)queueMicrotask(()=>{if(!live(id))return;$('#view').style.minHeight=minimum;reading.restore();});
    }catch(error){if(!live(id)||error.name==='AbortError')return;
      if(refresh){let note=$('#people-refresh-error');if(!note){note=document.createElement('p');note.id='people-refresh-error';note.setAttribute('role','status');$('#view').append(note);}note.innerHTML='本轮刷新失败，保留当前内容和输入，下轮重试：'+esc(error.message)+' <button class="act" id="people-retry">重试</button>';$('#people-retry').onclick=()=>render({refresh:true});return;}
      $('#view').innerHTML='<div class="card" role="alert">用户列表加载失败：'+esc(error.message)+' <button class="act" id="people-retry">重试</button></div>';$('#people-retry').onclick=render;}
  }
  function detail(id,historyData){
    const p=selected();
    const previousSource=state.source;
    if(state.group&&!p.sources.some(o=>o.group===state.group))state.group='';
    let others=catalog.people.filter(other=>other.id!==p.id);
    const groups=[...new Set(p.sources.filter(o=>o.kind==='group').map(o=>o.group))];
    $('#people-detail').innerHTML='<div class="card"><h3>'+esc(p.display_name||p.label)+'</h3>'+
      '<p class="dim" id="people-status">'+esc(p.status_label)+(p.conflict?' / 证据冲突，自动归类已受阻':'')+'；'+esc(p.profile_kind==='self_selected'?'本人设置的称呼':p.profile_kind==='qq_nickname'?'QQ 昵称':p.profile_kind==='platform_name'?'平台用户名，不能认作全局 QQ 昵称':'昵称未获取')+(p.profile_at?' / 资料更新 '+esc(fmtT(p.profile_at)):'')+(p.nickname_conflict?' / 多来源称呼不同：优先最新本人称呼，其次平台资料；称呼不作为合并依据':'')+(p.profile_source_uid?' / 主称呼来源 '+esc(p.profile_source_uid):'')+'</p>'+
      '<ul class="dim">'+p.basis.map(b=>'<li>'+esc(b)+'</li>').join('')+'</ul>'+
      '<div class="row" role="group" aria-label="查看场景">'+['all','private','group',...(p.sources.some(o=>o.legacy)?['legacy']:[])].map(mode=>'<button class="act scene-button" data-mode="'+mode+'" aria-pressed="'+(state.mode===mode)+'" '+(p.legacy&&!['all','legacy'].includes(mode)?'disabled':'')+'>'+({all:'全部消息',private:'私聊',group:'群聊',legacy:'旧档（场景未知）'}[mode])+'</button>').join('')+
      (state.mode==='group'?'<label for="people-group">具体群</label><select id="people-group"><option value="">全部群聊</option>'+groups.map(group=>'<option '+(state.group===group?'selected ':'')+'value="'+esc(group)+'">'+esc(group)+'</option>').join('')+'</select>':'')+'</div>'+
      '<p class="dim">仅查看各来源最近最多 150 条滚动记录，未加载完整归档。群回复仅展示可核验关联的已接受消息。</p>'+
      '<div id="people-history" aria-live="polite"></div><div class="row"><button class="act" id="people-history-prev" '+(state.offset?'':'hidden')+'>上一页记录</button><button class="act" id="people-more" hidden>加载下一页记录</button><span id="people-range" class="dim"></span></div></div>'+
      '<details class="card" id="people-associations"><summary>来源与人工关联</summary><p class="dim">只改变管理展示；不更改认证、主人权限、积分账本或发送目标。旧档可确认人物，场景仍未知。展开关联或管理面板时暂缓自动刷新，收起后恢复。</p>'+
      '<ul class="source-list">'+p.sources.map(o=>'<li><b>'+esc(o.profile?.value||'昵称未获取')+'</b> '+esc(o.profile?.kind==='self_selected'?'本人设置的称呼':o.profile?.kind==='qq_nickname'?'QQ 昵称':o.profile?'平台用户名（非已核验 QQ 昵称）':'')+(o.profile?' / '+esc(o.profile.source)+' / '+esc(fmtT(o.profile.at)):'')+(o.group_card?'<br>群名片/群备注：'+esc(o.group_card.value)+' / '+esc(o.group_card.source):'')+(o.name?'<br>备注/历史称呼（性质未核验）：'+esc(o.name):'')+'<br>'+esc(o.label)+'<br>场景识别：'+esc(o.scene_status==='identified'?'已识别 / '+o.scene_basis:'尚未识别 / '+o.scene_reason)+'<br>人物证据：'+esc(o.identity_basis||o.identity_reason)+(o.identity_at?' / 原观察 '+esc(fmtT(o.identity_at))+' / 消息 '+esc(o.identity_message_id):'')+(o.identity_conflict_count?' / 保留 '+o.identity_conflict_count+' 份冲突证据':'')+(o.projection_only?'<br>历史派生视图，只读，不是管理目标':'')+'<br><span class="mono">'+esc(o.platform+' / '+o.bot+' / '+o.uid)+'</span>'+(o.observed_app?'<br>身份应用/帐号：'+esc(o.observed_app):' / 应用未观测')+'</li>').join('')+'</ul>'+
      '<div class="row"><label for="people-link-search">查找待关联入口</label><input id="people-link-search" placeholder="备注或来源标识" maxlength="256"><button class="act" id="people-link-find">查找</button></div><div class="row"><label for="people-associate">确认同一用户入口</label><select id="people-associate"><option value="">选择另一个入口</option>'+others.map(other=>'<option value="'+esc(other.id)+'">'+esc(other.label+' — '+other.sources.map(o=>o.label).join('；'))+'</option>').join('')+'</select><button class="act" id="people-link">关联展示</button></div>'+
      '<p class="source-list dim">'+p.sources.flatMap(o=>(o.index_aliases||[]).map(a=>'资料别名 '+a.uid+' → '+o.uid+'（对应 '+a.related_count+' 个来源，仅作资料索引）')).map(esc).join('<br>')+'</p>'+
      '<button class="act" id="people-deny">确认所选另一入口不是此人</button>'+
      (!p.manual&&p.sources.length===1&&!p.conflict?'<button class="act" id="people-confirm">确认此来源为独立用户</button>':'')+
      (p.sources.length>1||p.manual?'<div class="row"><label for="people-unlink-source">解除关联的来源</label><select id="people-unlink-source">'+p.sources.map(o=>'<option value="'+esc(o.uid)+'">'+esc(o.label)+'</option>').join('')+'</select><button class="act danger" id="people-unlink">解除此来源关联</button><span class="dim">同时记住不自动合回；重新人工确认可解除该限制。</span></div>':'')+
      '<p id="people-link-result" role="status"></p></details>'+
      '<details class="card" id="people-operations"><summary>管理具体来源</summary><p class="dim">查看记录不会自动选择操作或发送目标。共享积分按原账本操作一次，不相加；开关及删除仍按所选来源处理。来源不明旧档不能作为群/私聊操作目标。</p><div class="row"><label for="people-source">操作来源</label><select id="people-source"><option value="">未选择来源（管理操作停用）</option>'+p.sources.filter(o=>!o.legacy&&!o.projection_only).map(o=>'<option value="'+esc(o.uid)+'">'+esc(o.label)+'</option>').join('')+'</select></div><p id="people-operation-source" class="source-list dim" aria-live="polite"></p><div id="u-detail"></div></details>';
    clearSource();
    if(p.sources.some(o=>!o.legacy&&!o.projection_only&&o.uid===previousSource)){state.source=previousSource;curUid=previousSource;$('#people-source').value=previousSource;$('#people-operation-source').textContent=p.sources.find(o=>o.uid===previousSource).label+' / 会话 '+previousSource;renderUserDetail();}
    document.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>{state.mode=button.dataset.mode;state.group='';state.offset=0;clearSource();render();});
    if($('#people-group'))$('#people-group').onchange=e=>{state.group=e.target.value;state.offset=0;clearSource();render();};
    $('#people-source').onchange=e=>{state.source=e.target.value;curUid=state.source||null;
      if(!curUid){clearSource();return;}$('#people-operation-source').textContent=p.sources.find(o=>o.uid===curUid).label+' / 会话 '+curUid;renderUserDetail();};
    async function associate(operation){
      const right=$('#people-associate')?.value,scope=$('#people-unlink-source')?.value;
      if(saving)return;
      if(['link','deny'].includes(operation)&&!right){$('#people-link-result').textContent='请先选择另一个入口并核对来源。';return;}
      const other=others.find(o=>o.id===right);
      saving=true;
      const origins=['link','deny'].includes(operation)?p.sources.concat(other.sources):operation==='unlink'?[p.sources.find(o=>o.uid===scope)]:p.sources;
      if(!await review(operation,origins)||!live(id)){saving=false;return;}
      const button=$('#people-'+operation);button.disabled=true;
      let uncertain=false;
      try{let r;try{r=await post('/api/people/'+operation,{left:p.id,right,person:p.id,scope,revision:catalog.revision,confirm:true});}catch(error){uncertain=true;throw error;}
        if(!live(id))return;if(!r.ok)throw Error(r.error||'关联未保存');state.anchor=p.sources[0].uid;state.listOffset=0;state.query='';state.category='all';clearSource();saving=false;await render();
      }catch(error){if(live(id)){document.querySelectorAll('#people-associations button').forEach(b=>b.disabled=uncertain);$('#people-link-result').textContent=(uncertain?'结果尚未确认，请刷新核对后再操作，勿重复提交：':'未保存：')+error.message;}}
      finally{saving=false;if(button.isConnected&&!uncertain)button.disabled=false;}
    }
    if($('#people-link'))$('#people-link').onclick=()=>associate('link');
    let searchVersion=0;
    if($('#people-link-find'))$('#people-link-find').onclick=async()=>{
      const search=++searchVersion;
      try{const r=await get('/api/people?limit=100&q='+encodeURIComponent($('#people-link-search').value.trim()),controller.signal);
        if(!live(id)||search!==searchVersion)return;others=r.people.filter(other=>other.id!==p.id);
        $('#people-associate').innerHTML='<option value="">选择另一个入口</option>'+others.map(other=>'<option value="'+esc(other.id)+'">'+esc(other.label+' — '+other.sources.map(o=>o.label).join('；'))+'</option>').join('');
        $('#people-link-result').textContent=others.length?'请核对来源后确认关联。':'没有匹配入口，请换一个来源标识查找。';
      }catch(error){if(live(id)&&error.name!=='AbortError')$('#people-link-result').textContent='查找失败：'+error.message;}
    };
    if($('#people-unlink'))$('#people-unlink').onclick=()=>associate('unlink');
    if($('#people-deny'))$('#people-deny').onclick=()=>associate('deny');
    if($('#people-confirm'))$('#people-confirm').onclick=()=>associate('confirm');
    $('#people-history-prev').onclick=()=>{state.offset=Math.max(0,state.offset-150);render();};
    loadHistory(id,historyData);
  }
  async function loadHistory(id,initial=null){
    const p=selected(),target=$('#people-history');if(!initial)target.innerHTML='<p role="status">正在加载所选场景记录…</p>';
    $('#people-more').hidden=true;
    try{const q=new URLSearchParams({person:p.id,mode:state.mode,group:state.group,limit:'150',offset:String(state.offset)});
      const r=initial||await get('/api/people/history?'+q,controller.signal);if(!live(id))return;
      target.innerHTML=r.entries.length?r.entries.map(row=>'<div data-read-key="'+esc(row.scope_uid+':'+(row.view_key||row.id||[row.request_id,row.role,row.ts].join(':')))+'"><div class="h-note">'+esc((row.scene==='group'?'群 '+row.group:row.scene==='private'?'私聊':'来源未定旧档')+' / '+row.speaker+' / 消息 '+(row.source?.message_id||row.id||'未留存')+' / 来源 '+row.scope_uid)+'</div>'+(row.provenance?'<div class="h-note">触发：'+esc(row.provenance.trigger)+' / '+esc(row.provenance.request_id?'原请求 '+row.provenance.request_id:'无原用户请求')+' / '+esc(row.provenance.job_id?'后台任务 '+row.provenance.job_id:'无后台任务标识')+' / QQ 接口 accepted，客户端到达未由此证明</div>':'')+histEntryHtml(row)+'</div>').join(''):
        '<p class="dim">'+(r.source_count===0?'该用户入口没有所选场景的来源。可先核对来源并关联。':'所选来源暂无可核验的近期记录。')+'</p>';
      if(r.delivery_outcomes?.length)target.insertAdjacentHTML('beforeend','<details id="people-deliveries"><summary>投递记录（'+r.delivery_outcomes.length+'）</summary><p class="dim">accepted 表示 QQ 接口接受；unknown/failed 不表示送达，历史保存与客户端到达需分别核验。</p>'+r.delivery_outcomes.map(d=>'<div class="h-note">'+esc(d.status)+' / 尝试 '+esc(d.attempt_id)+' / '+esc(d.provenance?.request_id?'原请求 '+d.provenance.request_id:'无原用户请求')+' / '+esc(d.provenance?.job_id?'后台任务 '+d.provenance.job_id:'无后台任务标识')+'</div>').join('')+'</details>');
      $('#people-range').textContent='本页 '+r.entries.length+' 条，近期可读 '+r.count+' 条'+(r.excluded_unverified?'；已排除 '+r.excluded_unverified+' 条来源/回复关联不明记录':'');
      $('#people-more').hidden=r.next_offset===null;$('#people-more').onclick=()=>{state.offset=r.next_offset;render();};
      hydrateStickerSamples(target);
    }catch(error){if(!live(id)||error.name==='AbortError')return;target.innerHTML='<p role="alert">记录加载失败：'+esc(error.message)+' <button class="act" id="people-history-retry">重试记录</button></p>';$('#people-history-retry').onclick=()=>loadHistory(id);}
  }
  return {render,leave,busy,version:'20261028-identity-2'};
})();
