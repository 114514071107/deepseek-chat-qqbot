"""Real inject method, fixed one-pixel PNG and temporary data only."""
import base64
from io import BytesIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from repair_pipeline_support import load_pipeline
from test_repair_session_scope import ScopeEvent

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


class BatchRegression(unittest.IsolatedAsyncioTestCase):
    async def prepare(self, root, first, extra=(), group=''):
        obj, ns = load_pipeline(root)
        event = ScopeEvent(group=group)
        scope = obj._scope(event)
        event.set_extra('_dsh_input', first)
        obj.batch_wait[scope.key] = 1
        obj.batch_buf = {scope.key: list(extra)}
        obj.batch_skipwait = {}; obj.last_msg_at = {}
        ns.update(BATCH_WAIT=.001, BATCH_QUICK_WAIT=.001, BATCH_MAX_WAIT=.01,
                  BATCH_DONE_MINLEN=8, REST_IDLE=999999, REST_MAX_WAIT=.01)
        errors = []; obj._err = lambda *a: errors.append(a)
        req = SimpleNamespace(prompt=first['text'], contexts=[], system_prompt='', image_urls=[], func_tool=None)
        await obj.inject(event, req)
        return obj, event, req, errors

    async def test_single_mixed_and_later_images_reach_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'image.png').write_bytes(PNG)
            for text, initial, later in [('', ['image.png'], []), ('question', ['image.png'], []),
                                          ('question', [], ['image.png'])]:
                with self.subTest(text=text, initial=initial):
                    first = dict(text=text, images=initial, files=[], message_id='first', error='')
                    extra = [dict(text='', images=later, files=[], message_id='later', error='')] if later else []
                    obj, event, req, errors = await self.prepare(tmp, first, extra)
                    self.assertEqual(len(req.image_urls), 1, errors)
                    self.assertEqual(base64.b64decode(req.image_urls[0].split(',', 1)[1]), PNG)
                    self.assertEqual(obj.batch_buf, {})

    async def test_multiple_images_and_scope_do_not_mix(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'one.png').write_bytes(PNG); Path(tmp, 'two.png').write_bytes(PNG + b'fixture')
            first = dict(text='look', images=['one.png'], files=[], message_id='m1', error='')
            second = dict(text='and this', images=['two.png'], files=[], message_id='m2', error='')
            obj, event, req, errors = await self.prepare(tmp, first, [second], group='g1')
            self.assertEqual(len(req.image_urls), 2, errors)
            _, other, other_req, _ = await self.prepare(tmp, dict(first, images=[]), group='g2')
            self.assertEqual(other_req.image_urls, [])
            self.assertIn('and this', req.prompt)
            self.assertNotIn('and this', other_req.prompt)

    async def test_failed_image_and_missing_snapshot_explicitly_limit_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = dict(text='describe', images=['gone.png'], files=[], message_id='m', error='图片下载失败')
            obj, event, req, errors = await self.prepare(tmp, first)
            self.assertEqual(req.image_urls, [])
            self.assertIn('未能读取', req.prompt)
            self.assertIn('不能声称', req.prompt)
            self.assertTrue(event.get_extra('_dsh_image_errors'))

    async def test_animated_input_preserves_sampled_later_frame(self):
        from PIL import Image
        from batch_input import normalize_image
        output=BytesIO()
        Image.new('RGB',(2,2),'red').save(output,format='GIF',save_all=True,
            append_images=[Image.new('RGB',(2,2),'blue')],duration=100,loop=0)
        prepared=Image.open(BytesIO(normalize_image(output.getvalue()))).convert('RGB')
        colors={color for _,color in prepared.getcolors(prepared.width*prepared.height)}
        self.assertIn((0,0,255),colors,'animation was silently reduced to the first frame')


if __name__ == '__main__': unittest.main()
