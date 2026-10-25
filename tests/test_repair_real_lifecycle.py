import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from repair_pipeline_support import load_pipeline, ResultChain
from test_repair_session_scope import ScopeEvent
from task_runtime import work_context
from qq_delivery import DeliveryResult
from state_store import StateController, read_json, write_json


class RealLifecycleRegression(unittest.IsolatedAsyncioTestCase):
    def setup(self, tmp):
        obj, ns = load_pipeline(tmp, names=('inject', 'capture', '_clear_text_result', '_set_first_bubble_result',
            '_react_and_send', '_make_react', '_busy_notice'), guarded=True)
        ns.update(_load=read_json, _save=write_json)
        ns['random'] = SimpleNamespace(random=lambda:1, choice=lambda rows:rows[0], uniform=lambda *a:0)
        Path(tmp, 'persona.md').write_text('fixture', encoding='utf-8')
        event = ScopeEvent(); scope = obj._scope(event)
        token = obj.runtime.begin(scope.key)
        event.set_extra('_dsh_work', token)
        obj.request_owners = {scope.key:token.request}; obj.request_events = {scope.key:event}
        obj._drip_interval = lambda:(0,0)
        sent = []
        async def send(target, chain):
            sent.append(''.join(getattr(c, 'text', '') for c in chain.chain))
            return DeliveryResult('accepted', message_id=f'sent{len(sent)}')
        obj._send = send
        return obj, ns, event, scope, token, sent

    async def test_feedback_finishing_after_main_answer_never_dispatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _, event, scope, token, sent = self.setup(tmp)
            started = asyncio.Event(); release = asyncio.Event()
            async def react(*a): started.set(); await release.wait(); return '没看到图片'
            obj._make_react = react
            with work_context(token, event):
                task = asyncio.create_task(obj._react_and_send(scope.target, scope.key, 'quick', 'question'))
                await asyncio.wait_for(started.wait(),3)
                await obj.capture(event, SimpleNamespace(result_chain=ResultChain('已根据图片回答')))
                release.set()
                await asyncio.gather(task, return_exceptions=True)
                await obj._complete_reply(event)
            self.assertEqual(sent, ['已根据图片回答'])
            await obj.runtime.stop()

    async def test_accepted_feedback_not_repeated_by_same_request_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _, event, scope, token, sent = self.setup(tmp)
            async def react(*a): return '正在处理这条消息'
            obj._make_react = react
            with work_context(token, event):
                await obj._react_and_send(scope.target, scope.key, 'fetch', 'fixture')
                await obj.capture(event, SimpleNamespace(result_chain=ResultChain('正在处理这条消息')))
                await obj._complete_reply(event)
            self.assertEqual(sent, ['正在处理这条消息'])
            self.assertEqual(len(obj.h[scope.key]), 1)
            await obj.runtime.stop()

    async def test_disable_resume_new_input_excludes_stopped_instruction_but_keeps_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _, event, scope, token, _ = self.setup(tmp)
            state = StateController(obj, tmp, lambda key:asyncio.sleep(0))
            obj.th = {}; obj.t_path = str(Path(tmp, 'thoughts_v2.json'))
            with work_context(token, event):
                obj._record_user_turn(scope.key, 'STOPPED-OLD-TASK', scope=scope)
                obj._record_assistant_turn(scope.key, 'ALREADY-ACCEPTED', DeliveryResult('accepted', message_id='ok'))
            await state.apply('user', dict(uid=scope.key, key='reply', value=False))
            await state.apply('user', dict(uid=scope.key, key='reply', value=True))
            self.assertEqual(read_json(Path(tmp,'history.json'),{})[scope.key][0]['request_state'],'stopped')
            new = ScopeEvent(); new.message_obj.message_id = 'new'
            request = SimpleNamespace(prompt='NEW-INDEPENDENT-TASK', contexts=[], system_prompt='', func_tool=None)
            await obj.inject(new, request)
            self.assertNotIn('STOPPED-OLD-TASK', str(vars(request)))
            self.assertIn('ALREADY-ACCEPTED', str(request.contexts))
            self.assertIn('STOPPED-OLD-TASK', Path(tmp, 'archive.jsonl').read_text())
            # A legacy unmatched user is not guessed to have been cancelled.
            obj.h[scope.key].append(dict(id='legacy', role='user', text='LEGACY-RECORD', source=scope.source()))
            newer = ScopeEvent(); newer.message_obj.message_id = 'newer'
            await obj.inject(newer, request)
            self.assertIn('LEGACY-RECORD', str(request.contexts))
            await obj.runtime.stop()

    async def test_media_unknown_claim_becomes_neutral_and_parallel_scopes_keep_own_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _, event, scope, token, sent = self.setup(tmp)
            group=ScopeEvent(group='g1'); group_scope=obj._scope(group); group_token=obj.runtime.begin(group_scope.key)
            group.set_extra('_dsh_work',group_token)
            obj.request_owners[group_scope.key]=group_token.request;obj.request_events[group_scope.key]=group
            async def claim(*a): return '没看到图片'
            obj._make_react=claim
            targets=[]
            original=obj._send
            async def send(target,chain): targets.append(target);return await original(target,chain)
            obj._send=send
            async def feedback(event,scope,token):
                with work_context(token,event): await obj._react_and_send(scope.target,scope.key,'fetch','fixture')
            await asyncio.gather(feedback(event,scope,token),feedback(group,group_scope,group_token))
            self.assertEqual(sent,['正在处理这条消息','正在处理这条消息'])
            self.assertEqual(set(targets),{scope.target,group_scope.target})
            await obj.runtime.stop()

    async def test_global_shutdown_closes_active_history_before_revoking_control_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _, event, scope, token, _ = self.setup(tmp)
            owner=obj._scope(ScopeEvent('owner')); control=obj.runtime.begin(owner.key,'control')
            obj.scopes={owner.key:obj.scopes[owner.key],scope.key:obj.scopes[scope.key]}
            state=StateController(obj,tmp,lambda key:asyncio.sleep(0))
            with work_context(token,event):obj._record_user_turn(scope.key,'STOP-ON-GLOBAL-SWITCH',scope=scope)
            try:
                with work_context(control):result=await state.apply('switch',{'key':'enabled','value':False})
            except asyncio.CancelledError:self.fail('control epoch was revoked before cancellation state could be saved')
            self.assertTrue(result['ok'])
            self.assertEqual(obj.h[scope.key][0]['request_state'],'stopped')
            await obj.runtime.stop()


if __name__ == '__main__': unittest.main()
