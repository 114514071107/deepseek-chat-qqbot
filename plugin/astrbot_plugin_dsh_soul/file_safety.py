"""Small, non-executable owner workspace; this is not a process sandbox."""
import os
import re

TEXT_EXTS = ('.txt', '.md', '.csv')
_SECRET = re.compile(r'(^\.|secret|credential|token|password|private.?key|api.?key|密钥|令牌|密码)', re.I)


def _inside(path, root):
    try:
        return os.path.commonpath([path,root]) == root
    except ValueError:
        return False


def _has_link(path):
    current = os.path.abspath(path)
    while True:
        if os.path.islink(current) or os.path.isjunction(current):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def safe_assistant_path(value, *, root, forbidden_roots, exts=TEXT_EXTS, must_exist=True):
    denied = (None, '（权限拒绝：只能访问独立工作目录内的普通文本文件，禁止秘密、脚本、链接和运行目录）')
    if not root or not os.path.isabs(root) or root.startswith(('\\\\','//')) or _has_link(root) or not os.path.isdir(root):
        return denied
    root = os.path.normcase(os.path.realpath(root))
    for forbidden in forbidden_roots:
        forbidden = os.path.normcase(os.path.realpath(forbidden))
        if _inside(root,forbidden) or _inside(forbidden,root):
            return denied
    value = (value or '').strip().strip('"').strip("'")
    if not value or value.startswith(('\\\\','//')) or ':' in os.path.splitdrive(value)[1]:
        return denied
    for part in os.path.splitdrive(value)[1].replace('\\', '/').split('/'):
        if part in ('', '.', '..'):
            continue
        stem = part.split('.')[0].upper()
        if part.rstrip(' .') != part or stem in ('CON','PRN','AUX','NUL','CLOCK$','CONIN$','CONOUT$') or re.fullmatch(r'(COM|LPT)[1-9¹²³]',stem):
            return denied
    raw = os.path.abspath(value if os.path.isabs(value) else os.path.join(root,value))
    resolved = os.path.normcase(os.path.realpath(raw))
    if not _inside(resolved,root) or _has_link(raw):
        return denied
    parts = os.path.relpath(resolved,root).split(os.sep)
    if any(_SECRET.search(part) for part in parts if part != '.'):
        return denied
    if os.path.isfile(resolved) and os.stat(resolved).st_nlink > 1:
        return denied
    if not os.path.isdir(resolved):
        allowed = set(exts or TEXT_EXTS) & set(TEXT_EXTS + ('.bak',))
        if os.path.splitext(resolved)[1].lower() not in allowed:
            return denied
    if must_exist and not os.path.exists(resolved):
        return None, '（工作目录中没有这个文件）'
    return resolved, None
