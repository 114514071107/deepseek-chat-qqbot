# SPDX-License-Identifier: AGPL-3.0-only
# Added to this derivative on 2026-10-21.
import ast
import json
from pathlib import Path
import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from .balance_utils import allowed, format_balance

ROOT = Path(__file__).resolve().parents[3]

def owner_id():
    tree = ast.parse((ROOT / 'data/plugins/astrbot_plugin_dsh_soul/main.py').read_text(encoding='utf-8-sig'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'MASTER_OPENID' for t in node.targets):
            return ast.literal_eval(node.value)
    return ''

@register('ds_balance', 'local', '私聊查询 DeepSeek 官方账户余额', '1.0.0')
class DSBalance(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command('ds余额')
    async def balance(self, event: AstrMessageEvent):
        event.stop_event()
        if not allowed(event.get_sender_id(), owner_id(), event.is_private_chat()):
            yield event.plain_result('请主人在私聊中使用 /ds余额')
            return
        try:
            config = json.loads((ROOT / 'data/cmd_config.json').read_text(encoding='utf-8-sig'))
            sources = config.get('provider_sources', [])
            from urllib.parse import urlparse
            source = next((s for s in sources if urlparse(s.get('api_base', '')).hostname == 'api.deepseek.com'), None)
            if source is None:
                yield event.plain_result('未找到 DeepSeek 官方 API 配置。')
                return
            keys = source.get('key', [])
            key = keys if isinstance(keys, str) else next((k for k in keys if k), '')
            if not key:
                yield event.plain_result('DeepSeek API Key 未填写。')
                return
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get('https://api.deepseek.com/user/balance', headers={'Authorization': 'Bearer ' + key}, allow_redirects=False) as response:
                    if response.status != 200:
                        yield event.plain_result(f'余额查询失败（HTTP {response.status}），请检查 API Key 或稍后重试。')
                        return
                    result = format_balance(await response.json())
            yield event.plain_result(result)
        except Exception:
            yield event.plain_result('余额查询失败，请检查网络和 DeepSeek 配置后重试。')
