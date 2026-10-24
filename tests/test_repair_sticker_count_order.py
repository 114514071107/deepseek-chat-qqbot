"""Canonical current-message order, independent from retained history prefixes."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from acceptance_sticker_count_order_20261025 import CurrentCountOrderAcceptance
from repair_pipeline_support import load_pipeline, ResultChain
from test_repair_session_scope import ScopeEvent
from task_runtime import work_context
from qq_delivery import DeliveryResult


class CountInputOrderRegression(unittest.IsolatedAsyncioTestCase):
    async def pipeline(self, current, extras=(), *, reinject=False, replace_current=False):
        with tempfile.TemporaryDirectory() as tmp:
            obj, ns = load_pipeline(tmp, names=('inject','capture','send_sticker','_clear_text_result','_set_first_bubble_result'), guarded=True)
            self.addAsyncCleanup(obj.runtime.stop)
            Path(tmp,'persona.md').write_text('fixture',encoding='utf-8')
            picked=[]
            def pick(query):picked.append(query);return dict(pack='fixture',rel=query+'.png')
            ns['_pick_sticker']=pick;ns['random']=SimpleNamespace(random=lambda:1)
            event=ScopeEvent();event.message_str=current;scope=obj._scope(event)
            token=obj.runtime.begin(scope.key);event.set_extra('_dsh_work',token)
            def item(text, identity):return dict(text=text[:2000],count_text=text,images=[],files=[],message_id=identity)
            event.set_extra('_dsh_input',item(current,scope.message_id))
            obj.batch_buf={scope.key:[item(text,scope.message_id if identity=='current' else identity) for identity,text in extras]}
            obj.request_events={scope.key:event};obj.request_owners={scope.key:token.request}
            sent=[]
            async def media(*args):sent.append('image');return DeliveryResult('accepted',message_id=str(len(sent)))
            obj._send_sticker_row=media
            with work_context(token,event):
                req=SimpleNamespace(prompt=current,contexts=[],system_prompt='',image_urls=[],func_tool=None)
                await obj.inject(event,req)
                if replace_current:event.message_str='技术提示中的旧值共三张。'
                if reinject:await obj.inject(event,req)
                for n in range(5):await obj.send_sticker(event,str(n),only_sticker=True)
                limit=obj._sticker_budget(event)['limit'];queued=len(obj.pending_sticker.get(scope.key,[]))
                await obj.capture(event,SimpleNamespace(result_chain=ResultChain('')))
                plan=event.get_extra('_dsh_reply_plan');planned=len(plan.stickers)
                await obj._complete_reply(event)
            return (limit,queued,planned,len(sent),len(plan.results),len(obj.h.get(scope.key,[])),len(picked))

    async def test_current_prefix_duplicate_is_not_a_later_message(self):
        current='只发表情，原方案共三张。'+'合成材料。'*500+'更正：只发两张表情，共两张。'
        self.assertEqual(await self.pipeline(current,[('current',current[:2000])]),(2,)*7)

    async def test_identical_text_with_new_message_identity_is_a_real_supplement(self):
        prefix='只发表情，原方案共三张。'
        current=prefix+'合成材料。'*500+'更正：只发两张表情，共两张。'
        self.assertEqual(await self.pipeline(current,[('new-message',prefix)]),(3,)*7)

    async def test_long_supplement_uses_its_full_user_text(self):
        extra='原方案共四张表情。'+'合成材料。'*500+'更正：只发一张表情，共一张。'
        self.assertEqual(await self.pipeline('只发两张表情，共两张。',[('later',extra)]),(1,)*7)

    async def test_reinject_keeps_later_supplement_order(self):
        current='原方案共三张表情。'+'合成材料。'*500+'更正：共两张表情。'
        self.assertEqual(await self.pipeline(current,[('later','更正：只发一张表情，共一张。')],reinject=True),(1,)*7)

    async def test_canonical_current_text_does_not_follow_later_event_rewrites(self):
        self.assertEqual(await self.pipeline('只发两张表情，共两张。',reinject=True,replace_current=True),(2,)*7)

    async def test_literal_supplements_do_not_change_explicit_total(self):
        for text in ('“只发四张表情，共四张。”','```text\n只发四张表情，共四张。\n```','> 只发四张表情，共四张。'):
            with self.subTest(text=text):self.assertEqual(await self.pipeline('只发两张表情，共两张。',[('later',text)]),(2,)*7)


if __name__=='__main__':unittest.main()
