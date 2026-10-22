"""Chat punctuation is presentation only; no production plugin import."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
import asyncio
import tempfile
from repair_pipeline_support import load_pipeline,ResultChain
from test_repair_session_scope import ScopeEvent


class CapturePipelineRegression(unittest.IsolatedAsyncioTestCase):
    async def test_capture_does_not_treat_code_content_as_a_closing_fence(self):
        for inner in ('```example','    ```','```\u3000'):
            with self.subTest(inner=inner),tempfile.TemporaryDirectory(prefix='dsh-capture-') as tmp:
                code='snippet = """\n'+inner+'\n动作：表情 得意\n"""'
                ast.parse(code)
                text='```python\n'+code+'\n```'
                plugin,ns=load_pipeline(tmp)
                looked_up=[]; ns['_pick_sticker']=lambda query:looked_up.append(query)
                response=SimpleNamespace(result_chain=ResultChain(text))
                event=ScopeEvent('friend')
                await plugin.capture(event,response)
                self.assertEqual(response.result_chain.get_plain_text(),text)
                self.assertEqual(looked_up,[])

    async def test_capture_keeps_literal_action_text_and_parses_only_external_action_line(self):
        literal='```text\n动作：语音\n\n动作：表情开心\n```\n'
        with tempfile.TemporaryDirectory(prefix='dsh-capture-') as tmp:
            plugin,ns=load_pipeline(tmp)
            looked_up=[]
            def sticker(query):
                looked_up.append(query)
                return dict(tag='happy',caption='fixture')
            ns['_pick_sticker']=sticker
            # No voice/file/model sender is provided; reaching it is a failure.
            response=SimpleNamespace(result_chain=ResultChain(literal+'动作：表情 得意\n'))
            event=ScopeEvent('friend')
            await plugin.capture(event,response)
            self.assertEqual(response.result_chain.get_plain_text(),literal)
            self.assertEqual(looked_up,['得意'])
            self.assertEqual(len(plugin.pending_sticker[event.get_extra('_dsh_scope').key]),1)

    async def test_capture_preserves_code_string_literals_and_formats_surrounding_prose(self):
        code='```python\ndef say():\n    print("动作：表情 得意")\n\n    return "中文。"\n```'
        text='这是代码。\n'+code+'\n完成。'
        with tempfile.TemporaryDirectory(prefix='dsh-capture-') as tmp:
            plugin,ns=load_pipeline(tmp)
            looked_up=[]
            ns['_pick_sticker']=lambda query:looked_up.append(query)
            response=SimpleNamespace(result_chain=ResultChain(text))
            other=object(); response.result_chain.chain.insert(0,other)
            event=ScopeEvent('friend')
            await plugin.capture(event,response)
            self.assertEqual(response.result_chain.get_plain_text(),'这是代码\n'+code+'\n完成')
            self.assertIs(response.result_chain.chain[0],other)
            self.assertEqual(looked_up,[])

    async def test_capture_ordinary_chat_still_removes_period_and_hides_action_protocol(self):
        with tempfile.TemporaryDirectory(prefix='dsh-capture-') as tmp:
            plugin,_=load_pipeline(tmp)
            response=SimpleNamespace(completion_text='  知道了。\n\n动作：表情 得意')
            event=ScopeEvent('friend')
            await plugin.capture(event,response)
            self.assertEqual(response.completion_text,'知道了')

    async def test_capture_preserves_indentation_and_blank_lines_in_final_chain(self):
        text='```python\ndef outer():\n    if True:\n        print("中文。")\n\n    return 1\n```'
        with tempfile.TemporaryDirectory(prefix='dsh-capture-') as tmp:
            plugin,_=load_pipeline(tmp)
            response=SimpleNamespace(result_chain=ResultChain(text))
            event=ScopeEvent('friend')
            await plugin.capture(event,response)
            actual=response.result_chain.get_plain_text()
            self.assertEqual(actual,text)
            code=actual.removeprefix('```python\n').removesuffix('\n```')
            ast.parse(code)  # Syntax check only; never execute generated code.

    async def test_capture_completion_text_preserves_indented_code(self):
        text='    if True:\n        print("中文。")\n\n    # 结束。'
        with tempfile.TemporaryDirectory(prefix='dsh-capture-') as tmp:
            plugin,_=load_pipeline(tmp)
            response=SimpleNamespace(completion_text=text)
            event=ScopeEvent('friend')
            await plugin.capture(event,response)
            self.assertEqual(response.completion_text,text)

PLUGIN=Path(__file__).resolve().parents[1]/'plugin/astrbot_plugin_dsh_soul'
sys.path.insert(0,str(PLUGIN))


class ChatStyleRegression(unittest.TestCase):
    def test_existing_public_model_calls_receive_style_without_touching_internal_tasks(self):
        from chat_style import CHAT_STYLE
        tree=ast.parse((PLUGIN/'main.py').read_text(encoding='utf-8-sig'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DshSoul')
        fn=next(n for n in cls.body if getattr(n,'name','')=='_chat')
        fn.decorator_list=[]
        calls=[]
        class Provider:
            async def text_chat(self,**kwargs): calls.append(kwargs); return None
        ns=dict(CHAT_STYLE=CHAT_STYLE,NL='\n')
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'<real auxiliary model request>','exec'),ns)
        obj=SimpleNamespace(context=SimpleNamespace(get_using_provider=lambda:Provider()))
        async def run():
            await ns['_chat'](obj,'react',prompt='fixture',system_prompt='original')
            await ns['_chat'](obj,'safety',prompt='fixture',system_prompt='exact classification')
        asyncio.run(run())
        self.assertIn(CHAT_STYLE,calls[0]['system_prompt'])
        self.assertEqual(calls[1]['system_prompt'],'exact classification')
        self.assertEqual(len(calls),2)

    def test_ordinary_endings_removed_and_questions_exclamations_preserved(self):
        from chat_style import format_qq_text
        for before,after in [('知道了。','知道了'),('行.','行'),('好，','好'),('明白；','明白'),
                             ('嗯……','嗯'),('你确定？','你确定？'),('真的吗?!','真的吗?!'),
                             ('太好了！','太好了！'),('我知道，等一下。','我知道，等一下'),
                             ('第一句。\r\n第二句。','第一句\r\n第二句')]:
            self.assertEqual(format_qq_text(before),after)
            self.assertEqual(format_qq_text(after),after)

    def test_technical_text_and_quoted_original_are_preserved(self):
        from chat_style import format_qq_text
        for text in ['查看 https://example.invalid/a.','路径 D:\\资料\\报告.txt',
                     '版本 1.2.3，金额 3.14','打开 `报告.txt`','他说：“原文不改。”',
                     '```python\n# 中文注释。\nprint("你好。")\n```',
                     '    # 中文缩进代码。','plain English.','> 引用原句。',
                     '“第一句。\n第二句。”']:
            self.assertEqual(format_qq_text(text),text)
        self.assertEqual(format_qq_text('```\n中文。\n```\n回复。'),'```\n中文。\n```\n回复')
        self.assertEqual(format_qq_text('“第一句。\n”\n回复。'),'“第一句。\n”\n回复')

    def test_actual_splitters_do_not_break_literal_block_protection(self):
        import re
        tree=ast.parse((PLUGIN/'main.py').read_text(encoding='utf-8-sig'))
        names={'_cap_bubbles','_bubbles_napcat','_split_bubbles'}
        fns=[n for n in tree.body if getattr(n,'name','') in names]
        ns=dict(re=re,NL='\n',BUBBLE_CAP=2)
        try:
            from chat_style import preserve_literal_message
            ns['preserve_literal_message']=preserve_literal_message
        except ImportError: pass
        exec(compile(ast.fix_missing_locations(ast.Module(body=fns,type_ignores=[])),'<real bubble splitters>','exec'),ns)
        from chat_style import format_qq_text
        for text in ('```python\n# 中文注释。\n```','“第一句。\n第二句。”','> 引用第一句。\n> 第二句。'):
            for name in ('_bubbles_napcat','_split_bubbles'):
                bubbles=ns[name](text)
                self.assertEqual(bubbles,[text])
                self.assertEqual(format_qq_text(bubbles[0]),text)

    def test_actual_plain_wrapper_and_result_chain_keep_other_components(self):
        from chat_style import format_qq_text
        tree=ast.parse((PLUGIN/'main.py').read_text(encoding='utf-8-sig'))
        wrapper=next(n for n in tree.body if getattr(n,'name','')=='_qq_plain')
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DshSoul')
        method=next(n for n in cls.body if getattr(n,'name','')=='_set_first_bubble_result')
        class Plain:
            def __init__(self,text): self.text=text
        ns=dict(format_qq_text=format_qq_text,Plain=Plain)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper,method],type_ignores=[])),'<real text presentation>','exec'),ns)
        other=object()
        response=SimpleNamespace(result_chain=SimpleNamespace(chain=[other,Plain('旧文字。')]))
        ns['_set_first_bubble_result'](SimpleNamespace(_err=lambda *a:None),response,['知道了。'])
        self.assertIs(response.result_chain.chain[0],other)
        self.assertEqual(response.result_chain.chain[1].text,'知道了')
        self.assertEqual(ns['_qq_plain']('真的？').text,'真的？')

    def test_actual_first_bubble_omits_terminal_period(self):
        tree=ast.parse((PLUGIN/'main.py').read_text(encoding='utf-8-sig'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DshSoul')
        fn=next(n for n in cls.body if getattr(n,'name','')=='_set_first_bubble_result')
        ns={}
        try:
            from chat_style import format_qq_text
            ns['format_qq_text']=format_qq_text
        except ImportError: pass
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'<real first bubble>','exec'),ns)
        response=SimpleNamespace(completion_text='')
        ns['_set_first_bubble_result'](SimpleNamespace(_err=lambda *a:None),response,['知道了。'])
        self.assertEqual(response.completion_text,'知道了')


if __name__=='__main__': unittest.main()
