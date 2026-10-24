"""Acceptance probes for model tool repetitions beyond an explicit image count.

Uses the existing isolated real-method harness; no production instance or QQ calls.
"""
import unittest

import test_repair_sticker_selection as selection


class StickerCountAcceptance(unittest.IsolatedAsyncioTestCase):
    reply = selection.StickerSelectionRegression.reply

    async def test_two_tool_choices_satisfy_two_requested_images(self):
        planned, sent, _ = await self.reply(
            ['happy', 'sad'], '', user_text='只发两张表情，一张开心、一张无语，各一张，共两张，不要文字')
        self.assertEqual(len(planned), 2)
        self.assertEqual([kind for kind, _ in sent], ['sticker', 'sticker'])

    async def test_repeated_tool_rounds_cannot_exceed_two_requested_images(self):
        planned, sent, _ = await self.reply(
            ['happy', 'neutral', 'happy', 'sad', 'sad'], '',
            user_text='明确只发两张表情，一张开心、一张无语，各一张，共两张，不要文字')
        self.assertEqual(len(planned), 2, 'Repeated model tool rounds exceeded the explicit count')
        self.assertEqual([kind for kind, _ in sent], ['sticker', 'sticker'])

    async def test_explicit_two_identical_choices_remain_allowed(self):
        planned, sent, _ = await self.reply(
            ['happy', 'happy'], '', user_text='只发两张相同的开心表情，共两张，不要文字')
        self.assertEqual(planned, ['happy.png', 'happy.png'])
        self.assertEqual(sent, [('sticker', 'happy.png'), ('sticker', 'happy.png')])


if __name__ == '__main__':
    unittest.main()
