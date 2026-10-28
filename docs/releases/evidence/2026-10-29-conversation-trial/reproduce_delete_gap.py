"""Synthetic reproduction only: trusted actor history without its scopes index."""
import asyncio,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,r'D:\DSH Workspace\deepseek-chat-qqbot\tests')
from repair_pipeline_support import load_pipeline
from test_repair_session_scope import ScopeEvent
from session_scope import bind_scope
from state_store import StateController,write_json
async def main():
    with tempfile.TemporaryDirectory(prefix='dsh-review-delete-') as tmp:
        obj,ns=load_pipeline(tmp,names=());obj.th={};obj.t_path=str(Path(tmp)/'thoughts_v2.json')
        a=obj._scope(ScopeEvent('synthetic-a','synthetic-group'))
        missing=bind_scope(ScopeEvent('synthetic-b','synthetic-group'))
        assert missing.key not in obj.scopes
        obj.h[missing.key]=[dict(id='synthetic-orphan-source',role='user',text='SYNTHETIC-ORPHAN-ROW',source=missing.source(),ts=1)]
        write_json(obj.h_path,obj.h)
        state=StateController(obj,tmp,lambda k:asyncio.sleep(0))
        before=len(obj._dialogue_rows(a.key));result=await state.delete(a.group_key,['rolling']);after=obj._dialogue_rows(a.key)
        output=dict(synthetic_only=True,rows_before=before,delete_reported_ok=result['ok'],rows_after=len(after),orphan_still_in_model_dialogue=any(r['id']=='synthetic-orphan-source' for r in after))
        await obj.runtime.stop();await obj.resources.close()
        assert output['delete_reported_ok'] and output['orphan_still_in_model_dialogue']
        target=Path(__file__).with_name('reproduced-delete-gap.json');target.write_text(json.dumps(output,indent=2),encoding='utf-8');print(json.dumps(output))
asyncio.run(main())
