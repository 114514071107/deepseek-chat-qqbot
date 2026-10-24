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


def _literal_lines(text, mask_quotes=False):
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
        visible=[]
        for char in line:
            inside=bool(quotes)
            if char in _QUOTES:
                quotes.append(_QUOTES[char])
            elif quotes and char == quotes[-1]:
                quotes.pop()
            elif char == '"' or (mask_quotes and char == "'"):
                quotes.append(char)
            visible.append(' ' if inside or quotes or char in _QUOTES.values() else char)
        yield (''.join(visible), indented) if mask_quotes else (line, quoted or indented)


def request_prose(text):
    prose = '\n'.join(line for line, protected in _literal_lines(str(text or ''), mask_quotes=True) if not protected)
    return re.sub(r'(`+).*?\1', ' ', prose, flags=re.S)


def sticker_count_request(text):
    """Explicit 0..99 totals in current prose; ambiguous choices have no cap."""
    prose = request_prose(text)
    number = r'[0-9零一二两三四五六七八九十]{1,3}'
    if re.search(number+r'张?\s*(?:或|或者|到|至|[-~～—–])\s*'+number, prose): return None
    if not re.search(r'表情|贴图|图片', prose): return None
    totals = re.findall(r'(?:总共|一共|总计|合计|共)\s*('+number+r')\s*张', prose)
    requests = re.findall(r'(?:发|给|来|要)\s*('+number+r')\s*张[^。！？；\n]{0,16}?(?:表情包?|贴图|图片)', prose)
    choices = totals[-1:] or requests or re.findall(r'('+number+r')\s*张[^。！？；\n]{0,16}?(?:表情包?|贴图|图片)', prose)
    choices = choices or re.findall(r'(?:表情包?|贴图|图片)[^。！？；\n]{0,12}?('+number+r')\s*张', prose)
    if not choices: return None
    def value(raw):
        if raw.isascii() and raw.isdigit(): return int(raw)
        digits={c:n for n,c in enumerate('零一二三四五六七八九')};digits['两']=2
        if raw=='十': return 10
        if '十' in raw:
            left,right=raw.split('十',1)
            return digits.get(left,1)*10+digits.get(right,0) if len(left)<=1 and len(right)<=1 else 100
        return digits.get(raw,100)
    values=[value(raw) for raw in choices]
    return values[0] if len(set(values))==1 and 0<=values[0]<=99 else None


def sticker_only_request(text):
    """Recognize explicit request prose only, never quoted/code examples.

    This suppresses optional progress text; it does not execute an action or
    infer how many stickers a model/tool should select.
    """
    prose = request_prose(text)
    sticker = r'(?:表情包?|贴图)'
    negated = r'(?:不要|别|不用|不需要|不能|不想)\s*$'
    pure = r'(?:只(?:要|发|用|给|回(?:复)?)|仅(?:要|发|用|给|回(?:复)?)?|纯)[^。！？；\n]{0,32}?' + sticker
    if any(not re.search(negated, prose[:m.start()]) for m in re.finditer(pure, prose)):
        return True
    no_text = r'(?:不要|不用|别|无需|不需要|不带|不加)\s*(?:发(?:送)?|加|带|有)?\s*(?:任何|额外|附加)?\s*(?:文字|文本|气泡)'
    request = r'(?:发|给|回(?:复)?|来|要)[^。！？；\n]{0,32}?' + sticker
    return bool(re.search(no_text, prose) and
                any(not re.search(negated, prose[:m.start()]) for m in re.finditer(request, prose)))


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
