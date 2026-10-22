"""Bounded, source-bound incoming attachments. No framework or network import."""
import base64
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse, unquote

MAX_IMAGES = 8
MAX_ITEMS = 8
MAX_BYTES = 15 * 1024 * 1024


def normalize_image(data):
    from PIL import Image
    if not data or len(data) > MAX_BYTES:
        raise ValueError('image size limit')
    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > 16_000_000:
            raise ValueError('image pixel limit')
        frames = getattr(image, 'n_frames', 1)
        if frames > 1:
            count = min(frames, 9)
            canvas = Image.new('RGB', (1536, ((count+2)//3)*512), 'white')
            for n in range(count):
                image.seek(round(n*(frames-1)/(count-1)))
                if image.width*image.height > 16_000_000: raise ValueError('image pixel limit')
                frame = image.convert('RGB'); frame.thumbnail((512,512))
                canvas.paste(frame, ((n%3)*512, (n//3)*512))
            image = canvas
        else:
            image.load()
            image.thumbnail((1536, 1536))
            image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
        output = BytesIO(); image.save(output, format='PNG')
        result = output.getvalue()
        if len(result) > MAX_BYTES:
            raise ValueError('converted image size limit')
        return result


def read_local_image(source):
    if source.startswith('base64://'):
        if len(source) > MAX_BYTES * 4 // 3 + 100:
            raise ValueError('image size limit')
        return normalize_image(base64.b64decode(source[9:], validate=True))
    if source.startswith('file:'):
        parsed = urlparse(source)
        if parsed.netloc: raise ValueError('remote file host')
        source = unquote(parsed.path).lstrip('/') if __import__('os').name == 'nt' else unquote(parsed.path)
    with open(source, 'rb') as stream:
        return normalize_image(stream.read(MAX_BYTES + 1))


def merge_request(req, items, root):
    """Replace original raw refs with exact retained bytes; preserve ordered text."""
    refs = []; errors = []; ids = []
    for number, item in enumerate(items):
        if item.get('message_id'): ids.append(item['message_id'])
        if number and item.get('text'):
            req.prompt = (req.prompt or '') + '\n[同一发言者补充] ' + item['text'][:2000]
        if item.get('error'): errors.append(item['error'])
        for rel in item.get('images', []):
            if len(refs) >= MAX_IMAGES:
                errors.append('图片数量超过本轮上限'); break
            try:
                path = (Path(root) / rel).resolve()
                if not path.is_relative_to(Path(root).resolve()): raise ValueError('outside data root')
                with path.open('rb') as stream: data = stream.read(MAX_BYTES + 1)
                if not data or len(data) > MAX_BYTES: raise ValueError('image size limit')
                ref = 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')
                if ref not in refs: refs.append(ref)
            except (OSError, ValueError):
                errors.append('图片快照不可用')
        if number and item.get('files'):
            req.prompt = (req.prompt or '') + '\n[补充附件，仅留存，未读取正文] ' + ', '.join(n for _, n in item['files'])[:500]
    req.image_urls = refs
    if refs:
        req.prompt = (req.prompt or '') + '\n[图片准备说明] 图片输入为静态PNG；原图若为动画则按时间采样成拼图，仅可依据这些帧判断，不能假设覆盖全部动画。'
    if errors:
        req.prompt = (req.prompt or '') + '\n[图片状态] 部分图片未能读取：' + '；'.join(dict.fromkeys(errors)) + '。不能声称看到了未读取的图片；应明确说明限制。'
    return ids, errors
