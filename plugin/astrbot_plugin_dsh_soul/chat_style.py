"""QQ Chinese chat endings; leave technical/literal blocks intact."""
import re

CHAT_STYLE = ('【QQ聊天标点】这是中文QQ聊天，普通陈述的句末直接结束，不加句号，'
              '也不要用逗号、分号、冒号或省略号作默认收尾。只有明确疑问、惊讶、强调等语气需要时才用问号或感叹号，'
              '不要为了替代句号滥加问号或感叹号。句中按理解需要使用标点，代码、网址、文件名、数字和原文引用保持准确。')

_QUOTES = {'“':'”', '「':'」', '『':'』'}


def preserve_literal_message(text):
    """Keep block/quoted content together so later Plain formatting has context."""
    text=str(text or '')
    return bool(re.search(r'(?m)^(?:\s*(?:`{3,}|~{3,}|>)| {4}|\t)',text) or
                any(c in text for c in (*_QUOTES, *_QUOTES.values(), '"')))


def preserve_sticker_literal(text):
    """Protect code/quote blocks and quoted action examples, not quoted words."""
    text = str(text or '')
    return bool(re.search(r'(?m)^(?: {0,3}(?:`{3,}|~{3,}|>)| {4}|\t)', text) or
                any(protected and re.search(r'动作[:：]', line) for line, protected in _literal_lines(text)))


def _literal_lines(text):
    """Share original-text boundaries across action parsing and punctuation."""
    fence=None
    quotes=[]
    for line in text.splitlines(keepends=True):
        stripped=line.lstrip()
        marker=re.match(r' {0,3}(`{3,}|~{3,})',line)
        if marker:
            mark=marker.group(1)
            if fence is None:
                fence=mark
            elif mark[0]==fence[0] and len(mark)>=len(fence) and not line[marker.end():].rstrip('\r\n').strip(' \t'):
                fence=None
            yield line, True
            continue
        if fence:
            yield line, True
            continue
        if stripped.startswith('>'):
            yield line, True
            continue
        indented=line.startswith(('    ','\t'))
        if indented and not quotes:
            yield line, True
            continue
        quoted=bool(quotes) or any(c in line for c in (*_QUOTES, *_QUOTES.values(), '"'))
        for char in line:
            if char in _QUOTES:
                quotes.append(_QUOTES[char])
            elif quotes and char == quotes[-1]:
                quotes.pop()
            elif char == '"':
                quotes.append('"')
        yield line, quoted or indented


def split_chat_actions(text):
    """Only standalone protocol lines outside code/quotes are instructions."""
    clean,actions=[],[]
    for line,protected in _literal_lines(text):
        action=None if protected else re.fullmatch(r'\s*动作[:：]\s*(.*?)\s*',line.rstrip('\r\n'))
        if action:
            actions.append(action.group(1))
        else:
            clean.append(line)
    return ''.join(clean),actions


def format_qq_text(text):
    if not isinstance(text,str):
        return text
    output=[]
    for line,protected in _literal_lines(text):
        if protected or not re.search(r'[\u3400-\u9fff]',line):
            output.append(line)
            continue
        ending='\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else '\r' if line.endswith('\r') else ''
        body=line[:-len(ending)] if ending else line
        # A final period may belong to a URL/path, not the sentence.
        if not re.search(r'(?:https?://|www\.|[A-Za-z]:[\\/])\S+$',body.rstrip()):
            body=re.sub(r'[。．.，,；;：:、…~～]+\s*$','',body)
        output.append(body+ending)
    return ''.join(output)
