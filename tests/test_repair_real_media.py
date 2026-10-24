import tempfile
from types import SimpleNamespace
import unittest
from repair_pipeline_support import load_pipeline, ResultChain
from test_repair_session_scope import ScopeEvent
from task_runtime import work_context
from qq_delivery import DeliveryResult, failure
import test_repair_qq_delivery as delivery_tests


class RealMediaRegression(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_sticker_only_plan_has_no_text_and_one_safe_fallback(self):
        for outcome in ('accepted', 'failed', 'unknown'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as tmp:
                obj, ns = load_pipeline(tmp)
                ns['random'] = SimpleNamespace(random=lambda:1)
                ns['_pick_sticker'] = lambda q:dict(pack='fixture', rel='happy.png', tag='happy', caption='合成图')
                sent=[]
                async def sticker(*a):
                    sent.append('sticker')
                    return DeliveryResult('accepted', message_id='image') if outcome == 'accepted' else failure(outcome,'upload','media')
                async def text(target, chain):
                    sent.append('text'); return DeliveryResult('accepted', message_id='fallback')
                obj._send_sticker_row=sticker; obj._send=text
                event=ScopeEvent(); scope=obj._scope(event); token=obj.runtime.begin(scope.key)
                event.set_extra('_dsh_work',token)
                with work_context(token,event):
                    await obj.capture(event, SimpleNamespace(result_chain=ResultChain('给你一个表情\n动作：仅表情 得意')))
                    await obj._complete_reply(event)
                self.assertEqual(sent, ['sticker','text'] if outcome=='failed' else ['sticker'])
                self.assertEqual(len(obj.h.get(scope.key, [])),0 if outcome=='unknown' else 1)

    async def test_unsupported_native_quote_never_forwards_untrusted_reference(self):
        helper=delivery_tests.QQDeliveryRegression()
        for kind in ('private','group'):
            sender,calls=helper.sender()
            async def parse(chain): return ('来源明确的文本摘录',None,None,None,None,None,None)
            sender.parse=parse
            chain=SimpleNamespace(chain=[SimpleNamespace(type='Reply',id='REFIDX_foreign')])
            result=await sender.send(helper.target(kind),chain)
            self.assertEqual(result.status,'accepted')
            self.assertNotIn('message_reference',calls[0][2])
            self.assertEqual(result.persistence.get('reference'),'unsupported')

    async def test_sticker_intent_never_deletes_code_or_parses_quoted_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _=load_pipeline(tmp)
            event=ScopeEvent();event.set_extra('_dsh_sticker_only',True)
            code='```python\n    动作：仅表情 得意\n    print("原文。")\n```'
            await obj.capture(event,SimpleNamespace(result_chain=ResultChain(code)))
            plan=event.get_extra('_dsh_reply_plan')
            self.assertEqual(plan.bubbles,[code]);self.assertEqual(plan.stickers,[])

    async def test_textless_explicit_sticker_plan_does_not_send_target_mention_as_extra_bubble(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp);ns['random']=SimpleNamespace(random=lambda:1)
            event=ScopeEvent();scope=obj._scope(event);token=obj.runtime.begin(scope.key)
            event.set_extra('_dsh_work',token);event.set_extra('_dsh_sticker_only',True)
            obj.pending_sticker[scope.key]=[dict(pack='fixture',rel='happy.png',caption='fixture')]
            sent=[]
            async def sticker(*a):sent.append('sticker');return failure('failed','prepare','media')
            async def text(target,chain):sent.append('text');return DeliveryResult('accepted',message_id='fallback')
            obj._send_sticker_row=sticker;obj._send=text
            chain=ResultChain('');chain.chain.append(SimpleNamespace(type='At',qq='fixture'))
            with work_context(token,event):
                await obj.capture(event,SimpleNamespace(result_chain=chain))
                await obj._complete_reply(event)
            self.assertEqual(sent,['sticker','text'])


if __name__ == '__main__':unittest.main()
