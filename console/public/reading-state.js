// Capture at DOM commit time, after network waits and any intervening scrolling.
window.ReadingState=(()=>{
  const key=e=>e.id?'id:'+e.id:e.dataset.readKey?'row:'+e.dataset.readKey:e.dataset.person?'person:'+e.dataset.person:e.dataset.mode?'mode:'+e.dataset.mode:null;
  const nodes=root=>[root,...root.querySelectorAll('[id],[data-read-key],[data-person],[data-mode]')];
  function capture(root){
    const all=nodes(root),lookup=()=>new Map(nodes(root).map(e=>[key(e),e]).filter(([k])=>k));
    const scrollers=all.filter(e=>e.clientHeight&&e.scrollHeight>e.clientHeight+1&&/(auto|scroll)/.test(getComputedStyle(e).overflowY));
    function position(container){
      const viewport=container?container.getBoundingClientRect():{top:0,bottom:innerHeight};
      const items=all.filter(e=>e!==container&&key(e)&&(!container||container.contains(e))&&
        !scrollers.some(sc=>sc!==container&&sc.contains(e)));
      const visible=items.filter(e=>{const r=e.getBoundingClientRect();return r.bottom>viewport.top&&r.top<viewport.bottom;});
      // Prefer fine-grained messages over enclosing panels. Keep neighbours if the first row is deleted.
      const fine=visible.filter(e=>e.hasAttribute('data-read-key')||e.hasAttribute('data-person'));
      return {key:container?key(container):null,x:container?container.scrollLeft:scrollX,y:container?container.scrollTop:scrollY,
        anchors:(fine.length?fine:visible).slice(0,12).map(e=>({key:key(e),top:e.getBoundingClientRect().top-viewport.top}))};
    }
    const positions=[position(null),...scrollers.map(position)],open=all.filter(e=>e.tagName==='DETAILS'&&e.open).map(key);
    const active=document.activeElement,focus=root.contains(active)?key(active):null;
    return {restore(){
      const map=lookup();for(const k of open){const e=map.get(k);if(e)e.open=true;}
      for(const p of positions){const target=p.key?map.get(p.key):null;if(p.key&&!target)continue;
        const set=(x,y)=>target?target.scrollTo(x,y):window.scrollTo(x,y);set(p.x,p.y);
        const a=p.anchors.find(a=>map.has(a.key));if(a){const e=map.get(a.key),top=target?target.getBoundingClientRect().top:0;
          const delta=e.getBoundingClientRect().top-top-a.top;set(p.x,(target?target.scrollTop:scrollY)+delta);}
      }
      if(focus&&map.get(focus))map.get(focus).focus({preventScroll:true});
    }};
  }
  const hasDraft=root=>[...root.querySelectorAll('input:not([type=checkbox]):not([type=button]),textarea')].some(e=>e.value!==e.defaultValue);
  return {capture,hasDraft};
})();
