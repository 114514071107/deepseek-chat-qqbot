/* Existing workbench styling; associations affect display only. */
window.UserWorkbench=(()=>{
  const state={person:null,mode:'private',group:'',source:'',offset:0,listOffset:0,anchor:null};
  let epoch=0,controller=null,catalog=null;
  const leave=()=>{epoch++;if(controller)controller.abort();};
  const selected=()=>catalog?.people.find(p=>p.id===state.person);
  const live=id=>id===epoch&&cur==='users';
  async function get(url,signal){const r=await api(url,{signal});if(r.ok!==true)throw Error(r.error||'未取得有效响应');return r;}
  function clearSource(){state.source='';curUid=null;scopeDetailVersion++;const label=$('#people-operation-source');if(label)label.textContent='未选择操作来源';const pane=$('#u-detail');if(pane)pane.innerHTML='<p class="dim">未选择操作来源。开关、积分、删除均不会作用于聚合入口；发送请到通知页另选目标。</p>';}
  async function render(){
    leave();const id=epoch;controller=new AbortController();
    if(cur!=='users')return;
    $('#view').innerHTML='<div class="card" role="status">正在加载用户入口…</div>';
    try{
      const [r,switches]=await Promise.all([get('/api/people?limit=100&offset='+state.listOffset,controller.signal),api('/api/switches',{signal:controller.signal})]);
      if(!live(id))return;
      catalog=r;swCache=switches;
      if(state.anchor){state.person=r.people.find(p=>p.sources.some(o=>o.uid===state.anchor))?.id||null;state.anchor=null;}
      if(!r.people.some(p=>p.id===state.person)){
        state.person=r.people[0]?.id||null;state.mode=selected()?.legacy?'legacy':selected()?.sources.some(o=>o.kind==='private')?'private':'group';
        state.group='';state.source='';state.offset=0;
      }
      $('#view').innerHTML='<div class="row"><b>'+r.total+' 个用户入口</b><span class="dim">'+r.scope_count+' 个来源会话</span></div>'+
        '<p class="dim">不同场景的身份无法确认时保持分开。确认是同一人后可关联展示，原会话和权限继续独立。</p>'+
        '<div class="uchips" aria-label="用户入口">'+r.people.map(p=>'<button type="button" class="uchip'+(p.id===state.person?' on':'')+'" aria-pressed="'+(p.id===state.person)+'" data-person="'+esc(p.id)+'"><div class="un">'+esc(p.label)+'</div><div class="uu">'+p.origin_count+' 个来源'+(p.legacy?' / 旧档未关联':p.manual?' / 人工确认关联':' / 来源独立')+'</div></button>').join('')+'</div>'+
        '<div class="row"><button class="act" id="people-prev" '+(state.listOffset?'':'disabled')+'>上一页用户</button><button class="act" id="people-next" '+(r.next_offset===null?'disabled':'')+'>下一页用户</button></div><div id="people-detail"></div>';
      document.querySelectorAll('[data-person]').forEach(button=>button.onclick=()=>{
        state.person=button.dataset.person;state.group='';state.source='';state.offset=0;curUid=null;
        const p=selected();state.mode=p.legacy?'legacy':p.sources.some(o=>o.kind==='private')?'private':'group';render();
      });
      $('#people-prev').onclick=()=>{state.listOffset=Math.max(0,state.listOffset-100);render();};
      $('#people-next').onclick=()=>{state.listOffset=r.next_offset;render();};
      if(!selected()){$('#people-detail').innerHTML='<div class="card">暂无用户来源。收到并保存消息后再刷新。</div>';return;}
      detail(id);
    }catch(error){if(!live(id)||error.name==='AbortError')return;$('#view').innerHTML='<div class="card" role="alert">用户列表加载失败：'+esc(error.message)+' <button class="act" id="people-retry">重试</button></div>';$('#people-retry').onclick=render;}
  }
  function detail(id){
    const p=selected();
    const previousSource=state.source;
    if(state.group&&!p.sources.some(o=>o.group===state.group))state.group='';
    let others=catalog.people.filter(other=>other.id!==p.id&&!other.legacy);
    const groups=[...new Set(p.sources.filter(o=>o.kind==='group').map(o=>o.group))];
    $('#people-detail').innerHTML='<div class="card"><h3>'+esc(p.label)+'</h3>'+
      '<div class="row" role="group" aria-label="查看场景">'+['private','group',...(p.legacy?['legacy']:[])].map(mode=>'<button class="act scene-button" data-mode="'+mode+'" aria-pressed="'+(state.mode===mode)+'" '+(p.legacy&&mode!=='legacy'?'disabled':'')+'>'+({private:'私聊',group:'群聊',legacy:'旧档未关联'}[mode])+'</button>').join('')+
      (state.mode==='group'?'<label for="people-group">具体群</label><select id="people-group"><option value="">全部群聊</option>'+groups.map(group=>'<option '+(state.group===group?'selected ':'')+'value="'+esc(group)+'">'+esc(group)+'</option>').join('')+'</select>':'')+'</div>'+
      '<p class="dim">仅查看各来源最近最多 150 条滚动记录，未加载完整归档。群回复仅展示可核验关联的已接受消息。</p>'+
      '<div id="people-history" aria-live="polite"></div><div class="row"><button class="act" id="people-history-prev" '+(state.offset?'':'hidden')+'>上一页记录</button><button class="act" id="people-more" hidden>加载下一页记录</button><span id="people-range" class="dim"></span></div></div>'+
      '<details class="card"><summary>来源与人工关联</summary><p class="dim">只改变管理展示；不更改认证、主人权限、积分账本或发送目标。旧档来源未定时不能关联。</p>'+
      '<ul class="source-list">'+p.sources.map(o=>'<li><b>'+esc(o.name||'未备注')+'</b> '+esc(o.label)+'<br><span class="mono">'+esc(o.platform+' / '+o.bot+' / '+o.uid)+'</span></li>').join('')+'</ul>'+
      (!p.legacy?'<div class="row"><label for="people-link-search">查找待关联入口</label><input id="people-link-search" placeholder="备注或来源标识" maxlength="256"><button class="act" id="people-link-find">查找</button></div><div class="row"><label for="people-associate">确认同一用户入口</label><select id="people-associate"><option value="">选择另一个入口</option>'+others.map(other=>'<option value="'+esc(other.id)+'">'+esc(other.label+' — '+other.sources.map(o=>o.label).join('；'))+'</option>').join('')+'</select><button class="act" id="people-link">关联展示</button></div>':'')+
      (p.manual?'<div class="row"><label for="people-unlink-source">解除关联的来源</label><select id="people-unlink-source">'+p.sources.map(o=>'<option value="'+esc(o.uid)+'">'+esc(o.label)+'</option>').join('')+'</select><button class="act danger" id="people-unlink">解除此来源关联</button></div>':'')+
      '<p id="people-link-result" role="status"></p></details>'+
      '<details class="card" id="people-operations"><summary>管理具体来源</summary><p class="dim">查看记录不会自动选择操作或发送目标。共享积分按原账本操作一次，不相加；开关及删除仍按所选来源处理。</p><div class="row"><label for="people-source">操作来源</label><select id="people-source"><option value="">未选择来源（管理操作停用）</option>'+p.sources.map(o=>'<option value="'+esc(o.uid)+'">'+esc(o.label)+'</option>').join('')+'</select></div><p id="people-operation-source" class="source-list dim" aria-live="polite"></p><div id="u-detail"></div></details>';
    clearSource();
    if(p.sources.some(o=>o.uid===previousSource)){state.source=previousSource;curUid=previousSource;$('#people-source').value=previousSource;$('#people-operation-source').textContent=p.sources.find(o=>o.uid===previousSource).label+' / 会话 '+previousSource;renderUserDetail();}
    document.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>{state.mode=button.dataset.mode;state.group='';state.offset=0;clearSource();render();});
    if($('#people-group'))$('#people-group').onchange=e=>{state.group=e.target.value;state.offset=0;clearSource();render();};
    $('#people-source').onchange=e=>{state.source=e.target.value;curUid=state.source||null;
      if(!curUid){clearSource();return;}$('#people-operation-source').textContent=p.sources.find(o=>o.uid===curUid).label+' / 会话 '+curUid;renderUserDetail();};
    async function associate(operation){
      const right=$('#people-associate')?.value,scope=$('#people-unlink-source')?.value;
      if(operation==='link'&&!right){$('#people-link-result').textContent='请先选择另一个入口并核对来源。';return;}
      const other=others.find(o=>o.id===right);
      const description=operation==='link'?p.sources.concat(other.sources).map(o=>o.label).join('\n'):p.sources.find(o=>o.uid===scope).label;
      if(!confirm((operation==='link'?'确认这些来源属于同一人，仅关联管理展示？\n':'确认解除这个来源的展示关联？\n')+description))return;
      const button=$('#people-'+operation);button.disabled=true;
      try{const r=await post('/api/people/'+operation,{left:p.id,right,person:p.id,scope,revision:catalog.revision,confirm:true});
        if(!live(id))return;if(!r.ok)throw Error(r.error||'关联未保存');state.anchor=p.sources[0].uid;clearSource();await render();
      }catch(error){if(live(id))$('#people-link-result').textContent='未保存：'+error.message;}
      finally{if(button.isConnected)button.disabled=false;}
    }
    if($('#people-link'))$('#people-link').onclick=()=>associate('link');
    let searchVersion=0;
    if($('#people-link-find'))$('#people-link-find').onclick=async()=>{
      const search=++searchVersion;
      try{const r=await get('/api/people?limit=100&q='+encodeURIComponent($('#people-link-search').value.trim()),controller.signal);
        if(!live(id)||search!==searchVersion)return;others=r.people.filter(other=>other.id!==p.id&&!other.legacy);
        $('#people-associate').innerHTML='<option value="">选择另一个入口</option>'+others.map(other=>'<option value="'+esc(other.id)+'">'+esc(other.label+' — '+other.sources.map(o=>o.label).join('；'))+'</option>').join('');
        $('#people-link-result').textContent=others.length?'请核对来源后确认关联。':'没有匹配入口，请换一个来源标识查找。';
      }catch(error){if(live(id)&&error.name!=='AbortError')$('#people-link-result').textContent='查找失败：'+error.message;}
    };
    if($('#people-unlink'))$('#people-unlink').onclick=()=>associate('unlink');
    $('#people-history-prev').onclick=()=>{state.offset=Math.max(0,state.offset-150);render();};
    loadHistory(id);
  }
  async function loadHistory(id){
    const p=selected(),target=$('#people-history');target.innerHTML='<p role="status">正在加载所选场景记录…</p>';
    $('#people-more').hidden=true;
    try{const q=new URLSearchParams({person:p.id,mode:state.mode,group:state.group,limit:'150',offset:String(state.offset)});
      const r=await get('/api/people/history?'+q,controller.signal);if(!live(id))return;
      target.innerHTML=r.entries.length?r.entries.map(row=>'<div class="h-note">'+esc((row.scene==='group'?'群 '+row.group:row.scene==='private'?'私聊':'来源未定旧档')+' / '+row.speaker+' / 消息 '+(row.source?.message_id||row.id||'未留存')+' / 来源 '+row.scope_uid)+'</div>'+histEntryHtml(row)).join(''):
        '<p class="dim">'+(r.source_count===0?'该用户入口没有所选场景的来源。可先核对来源并关联。':'所选来源暂无可核验的近期记录。')+'</p>';
      $('#people-range').textContent='本页 '+r.entries.length+' 条，近期可读 '+r.count+' 条'+(r.excluded_unverified?'；已排除 '+r.excluded_unverified+' 条来源/回复关联不明记录':'');
      $('#people-more').hidden=r.next_offset===null;$('#people-more').onclick=()=>{state.offset=r.next_offset;render();};
      hydrateStickerSamples(target);
    }catch(error){if(!live(id)||error.name==='AbortError')return;target.innerHTML='<p role="alert">记录加载失败：'+esc(error.message)+' <button class="act" id="people-history-retry">重试记录</button></p>';$('#people-history-retry').onclick=()=>loadHistory(id);}
  }
  return {render,leave,version:'20261025-users-1'};
})();
