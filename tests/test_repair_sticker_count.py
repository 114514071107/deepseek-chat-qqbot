import asyncio
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from acceptance_sticker_count_20261025 import StickerCountAcceptance
from repair_pipeline_support import load_pipeline, ResultChain
from test_repair_session_scope import ScopeEvent
from task_runtime import work_context
from qq_delivery import DeliveryResult, failure


class StickerCountRegression(unittest.IsolatedAsyncioTestCase):
    async def run_count(self, text, expected, *, group='', concurrent=False, outcome='accepted', action=False, corrupt=False):
        with tempfile.TemporaryDirectory() as tmp:
            obj, ns = load_pipeline(tmp, names=('capture','send_sticker','_clear_text_result','_set_first_bubble_result'))
            self.addAsyncCleanup(obj.runtime.stop)
            ns['random'] = SimpleNamespace(random=lambda:1)
            picked=[]
            def pick(q): picked.append(q); return dict(pack='fixture',rel=q+'.png',caption='fixture')
            ns['_pick_sticker']=pick
            event=ScopeEvent(group=group); event.message_str=text
            scope=obj._scope(event); token=obj.runtime.begin(scope.key);event.set_extra('_dsh_work',token)
            obj.request_owners={scope.key:token.request};obj.request_events={scope.key:event}
            sends=[]
            async def media(target,row):
                sends.append('image')
                return DeliveryResult('accepted',message_id=str(len(sends))) if outcome=='accepted' else failure(outcome,'upload','media')
            async def send(*args): sends.append('text');return DeliveryResult('accepted',message_id='fallback')
            obj._send_sticker_row=media;obj._send=send
            with work_context(token,event):
                if not action:
                    calls=[obj.send_sticker(event,'same',only_sticker=True) for _ in range(7)]
                    if concurrent: await asyncio.gather(*calls)
                    else:
                        for call in calls: await call
                    self.assertEqual(len(obj.pending_sticker[scope.key]),expected)
                    self.assertEqual(len(picked),expected)
                await obj.capture(event,SimpleNamespace(result_chain=ResultChain('动作：仅表情 same' if action else '')))
                plan=event.get_extra('_dsh_reply_plan')
                self.assertEqual(len(plan.stickers),1 if action else expected)
                if corrupt: plan.stickers.extend([dict(pack='fixture',rel='extra.png')]*5)
                await obj._complete_reply(event)
                await obj._complete_reply(event)
            delivered=1 if action else expected
            self.assertEqual(sends,['image']*delivered if outcome=='accepted' else ['image','text'] if outcome=='failed' else ['image'])
            self.assertEqual(len(plan.results),delivered if outcome=='accepted' else 2 if outcome=='failed' else 1)
            hist=obj.h.get(scope.key,[])
            self.assertEqual(len(hist),delivered if outcome=='accepted' else 1 if outcome=='failed' else 0)
            self.assertTrue(all(row['delivery']['status']=='accepted' for row in hist))
            self.assertEqual(plan.results[0].status,outcome)
            self.assertNotIn(scope.key,obj.pending_sticker)

    async def test_private_group_counts_and_same_images_across_concurrent_rounds(self):
        for group in ('','fixture-group'):
            for number,text in ((1,'只发一张表情'),(2,'只发两张相同表情'),(3,'只发3张表情'),(4,'发四张表情，共四张')):
                with self.subTest(group=group,text=text):await self.run_count(text,number,group=group,concurrent=True)

    async def test_final_send_guard_and_failure_unknown_do_not_fill_or_retry(self):
        for outcome in ('accepted','failed','unknown'):
            with self.subTest(outcome=outcome):await self.run_count('只发两张表情',2,outcome=outcome,corrupt=True)

    async def test_action_fallback_uses_same_limit(self):
        await self.run_count('只发一张表情',1,action=True)

    def test_quantity_parser_ignores_literal_and_requires_unambiguous_total(self):
        from chat_style import sticker_count_request
        for text,expected in [('两张相同的开心表情，共两张',2),('一张开心、一张无语，共两张表情',2),
                              ('只发两张表情，一张开心表情，一张无语表情',2),
                              ('请发十二张表情',12),('表情包发3张',3),('只发十张图片',10),
                              ('请解释“发两张表情”',None),('```\n发2张表情\n```',None),
                              ('> 发两张表情',None),('请发表情',None),('发两张或三张表情',None),('发2—3张表情',None)]:
            with self.subTest(text=text):self.assertEqual(sticker_count_request(text),expected)

    async def test_new_request_scope_and_reset_do_not_reuse_quota_or_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp,names=('send_sticker',),guarded=True)
            self.addAsyncCleanup(obj.runtime.stop)
            ns['_pick_sticker']=lambda q:dict(pack='fixture',rel=q+'.png')
            events=[ScopeEvent(),ScopeEvent(group='g1'),ScopeEvent()]
            for event,count in zip(events,(2,3,1)):
                event.message_str=f'只发{count}张表情'
                scope=obj._scope(event); token=obj.runtime.begin(scope.key);event.set_extra('_dsh_work',token)
                obj.request_events=getattr(obj,'request_events',{});obj.request_events[scope.key]=event
                with work_context(token,event):
                    for n in range(5):await obj.send_sticker(event,str(n),only_sticker=True)
                self.assertEqual(len(obj.pending_sticker[scope.key]),count)
            private=obj._scope(events[-1]);obj._reset_request(private.key)
            self.assertNotIn(private.key,obj.pending_sticker)
            self.assertTrue(events[-1].get_extra('_dsh_sticker_budget')['closed'])
            self.assertIn('已结束',obj._queue_sticker(events[-1],'late'))

    async def test_batch_count_and_cancel_during_media_clear_request_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp,names=('inject','capture','send_sticker','_clear_text_result','_set_first_bubble_result'),guarded=True)
            self.addAsyncCleanup(obj.runtime.stop)
            Path(tmp,'persona.md').write_text('fixture',encoding='utf-8')
            ns['_pick_sticker']=lambda q:dict(pack='fixture',rel=q+'.png')
            event=ScopeEvent();event.message_str='请发表情'
            scope=obj._scope(event);token=obj.runtime.begin(scope.key);event.set_extra('_dsh_work',token)
            event.set_extra('_dsh_input',dict(text=event.message_str,images=[],files=[],message_id='first'))
            obj.batch_buf={scope.key:[dict(text='共三张表情，不要文字',images=[],files=[],message_id='extra')]}
            obj.request_owners={scope.key:token.request};obj.request_events={scope.key:event}
            entered=asyncio.Event(); calls=[]
            async def blocked(*args):calls.append('upload');entered.set();await asyncio.Event().wait()
            obj._send_sticker_row=blocked
            with work_context(token,event):
                req=SimpleNamespace(prompt=event.message_str,contexts=[],system_prompt='',image_urls=[],func_tool=None)
                await obj.inject(event,req)
                for _ in range(5):await obj.send_sticker(event,'same',only_sticker=True)
                await obj.capture(event,SimpleNamespace(result_chain=ResultChain('')))
                plan=event.get_extra('_dsh_reply_plan');self.assertEqual(len(plan.stickers),3)
                task=asyncio.create_task(obj._complete_reply(event));await entered.wait();task.cancel()
                await asyncio.gather(task,return_exceptions=True)
            self.assertEqual(calls,['upload']);self.assertEqual(plan.results,[])
            self.assertTrue(plan.finished);self.assertNotIn(scope.key,obj.pending_sticker)

    async def test_old_completion_does_not_rewrite_new_request_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp)
            old=ScopeEvent();old.message_obj.message_id='old-message';scope=obj._scope(old)
            old.set_extra('_dsh_work',obj.runtime.begin(scope.key));obj._sticker_budget(old)
            new=ScopeEvent();new.message_obj.message_id='new-message';obj._scope(new)
            obj._finish_reply(old)
            self.assertEqual(obj.scopes[scope.key]['message_id'],'new-message')

    async def test_long_current_message_tail_is_not_replaced_by_retained_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp,names=('send_sticker',))
            self.addAsyncCleanup(obj.runtime.stop)
            ns['_pick_sticker']=lambda q:dict(pack='fixture',rel=q+'.png')
            event=ScopeEvent();event.message_str='合成附件。'*500+'只发两张表情'
            event.set_extra('_dsh_request_texts',[event.message_str[:2000]])
            scope=obj._scope(event)
            for _ in range(5):await obj.send_sticker(event,'same',only_sticker=True)
            self.assertEqual(len(obj.pending_sticker[scope.key]),2)

    async def test_intermediate_captures_keep_selected_slots_until_final_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp,names=('capture','send_sticker','_clear_text_result','_set_first_bubble_result'))
            self.addAsyncCleanup(obj.runtime.stop)
            ns['_pick_sticker']=lambda q:dict(pack='fixture',rel=q+'.png')
            ns['random']=SimpleNamespace(random=lambda:1)
            event=ScopeEvent();event.message_str='只发两张相同表情，不要文字'
            scope=obj._scope(event);token=obj.runtime.begin(scope.key);event.set_extra('_dsh_work',token)
            obj.request_owners={scope.key:token.request};obj.request_events={scope.key:event}
            sent=[]
            async def media(*args):sent.append('image');return DeliveryResult('accepted',message_id=str(len(sent)))
            obj._send_sticker_row=media
            with work_context(token,event):
                for n in range(5):
                    await obj.send_sticker(event,'same',only_sticker=True)
                    await obj.capture(event,SimpleNamespace(result_chain=ResultChain('')))
                    self.assertEqual(len(event.get_extra('_dsh_reply_plan').stickers),min(n+1,2))
                    await obj.capture(event,SimpleNamespace(result_chain=ResultChain('动作：仅表情 same')))
                    self.assertEqual(len(event.get_extra('_dsh_reply_plan').stickers),min(n+1,2))
                await obj._complete_reply(event)
            self.assertEqual(sent,['image','image']);self.assertEqual(len(obj.h[scope.key]),2)


if __name__=='__main__':unittest.main()
