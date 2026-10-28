"""Local, management-only self-selected names and cross-scene pairing.

Never used for model contexts, authorization, points or delivery targets.
Pairing secrets are hashed, short lived and excluded from conversation history.
"""
import base64
import hashlib
import json
import os
import re
import secrets
import tempfile
import unicodedata
from contextlib import contextmanager
from pathlib import Path
import time
from user_profiles import observe

FILE = 'user_directory_v1.json'
HELP = '称呼设置：发送「设置称呼 你的称呼」。关联群聊与私聊：先在私聊发送「关联身份」，按提示验证一次，以后自动归类。'
GRAY_HELP = '称呼设置：发送「设置称呼 你的称呼」。可靠平台身份存在时自动归类，证据不足时保留独立来源。'


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def fingerprint(s, app):
    return _hash([s['platform'], s['instance'], s['bot'], 'private' if s['private'] else 'group', s['group'], s['sender'], app])


def decisions(s, app):
    return [_hash([s['platform'], s['instance'], s['bot'], 'private' if s['private'] else 'group', s['group'], s['sender']]),
            _hash([s['platform'], s['instance'], app, 'user_openid' if s['private'] else 'member_openid', s['group'], s['sender']])]


def _read(file, fallback, cap=2*1024*1024):
    if not file.exists(): return fallback
    if file.stat().st_size > cap: raise ValueError('directory capacity')
    return json.loads(file.read_text(encoding='utf-8-sig'))


@contextmanager
def _store(root):
    file = Path(root)/FILE
    # Exclusive lock also protects against a second plugin process. Fail closed;
    # never remove another process's lock, including after a crash.
    lock = file.with_suffix(file.suffix+'.lock')
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        store = _read(file, dict(version=1, sources={}, pending={}))
        if not isinstance(store, dict) or store.get('version') != 1 or not isinstance(store.get('sources'), dict) or not isinstance(store.get('pending'), dict):
            raise ValueError('unsupported directory')
        before = json.dumps(store, ensure_ascii=False, separators=(',', ':'))
        yield store
        after = json.dumps(store, ensure_ascii=False, separators=(',', ':'))
        if before == after: return
        if len(store['sources']) > 10000 or len(store['pending']) > 128 or len(after.encode()) > 2*1024*1024:
            raise ValueError('directory capacity')
        temp_fd, name = tempfile.mkstemp(prefix='.directory-', dir=file.parent)
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as out:
                out.write(after); out.flush(); os.fsync(out.fileno())
            os.replace(name, file)
        finally:
            if os.path.exists(name): os.unlink(name)
    finally:
        os.close(fd); os.unlink(lock)


def _row(store, scope, observed, now):
    s = {k: scope.source()[k] for k in ('platform', 'instance', 'bot', 'sender', 'group', 'private')}
    key = fingerprint(s, observed['app'])
    if key not in store['sources']:
        store['sources'][key] = dict(source=s, app=observed['app'], person=secrets.token_hex(16), created_at=now)
    return key, store['sources'][key]


def _domain(row):
    s = row['source']
    return [s['platform'], s['instance'], management_bot(s, row['app']), row['app']]


def management_bot(source, app):
    # Installed official adapter uses these two placeholders for group/C2C.
    # App is observed from the authenticated SDK token, never raw client data.
    # Real/unknown bot values retain their own domain. Fingerprints stay intact.
    if (source['platform'] == 'qq_official' and app and source['instance']
            and source['bot'] in ('qq_official', 'unknown_selfid')):
        return ['qq_official_adapter_placeholder']  # tagged value cannot collide with a literal self_id
    return source['bot']


def _code():
    return base64.b32encode(secrets.token_bytes(10)).decode()


def _blocked(root, rows):
    mapping = _read(Path(root)/'console_people_v1.json', {'groups':[], 'denied':[]})
    # Include sources already grouped by the maintainer, so pairing cannot bypass
    # a deny attached to a different member of the same management person.
    scopes = _read(Path(root)/'scopes_v2.json', {}, 32*1024*1024)
    keys = set()
    current = set()
    for row in rows:
        keys.update(decisions(row['source'], row['app']))
        current.update(uid for uid, s in scopes.items() if all(s.get(k)==v for k,v in row['source'].items()))
    for group in mapping.get('groups', []):
        if current.intersection(group):
            for uid in group:
                keys.add(_hash(['legacy',uid]))
                s = scopes.get(uid)
                if s and all(k in s for k in ('platform','instance','bot','sender','group','private')):
                    keys.update(decisions(s, rows[0]['app']))
    return any(a in keys and b in keys for a,b in mapping.get('denied', []))


def _proof_conflict(root, rows):
    profiles = _read(Path(root)/'workbench_profiles_v1.json', {'sources':{}}, 8*1024*1024)
    identities = {}
    for p in profiles['sources'].values():
        if not isinstance(p, dict) or not any(p.get('app')==r['app'] and all(p.get('source',{}).get(k)==v for k,v in r['source'].items()) for r in rows):
            continue
        if p.get('identity_conflict'): return True
        s, i = p['source'], p.get('identity')
        if not isinstance(i, dict): continue
        valid = (s['platform']=='qq_official' and i.get('namespace')=='qq_user_openid' and
                 i.get('basis')==('qq_author_user' if s['private'] else 'qq_author_pair') and
                 (not s['private'] or i.get('value')==s['sender'])) or (
                 s['platform']=='aiocqhttp' and i.get('namespace')=='onebot_qq' and i.get('value')==s['sender'])
        if not valid or not isinstance(i.get('value'), str) or not i['value']: continue
        domain = (s['platform'], s['instance'], p['app'], i['namespace'])
        if domain in identities and identities[domain] != i['value']: return True
        identities[domain] = i['value']
    return False


def handle(event, scope, root, text, *, now=None):
    """Return a local reply only for an explicit command; ordinary chat is inert."""
    command = re.fullmatch(r'(设置称呼|关联身份|确认关联|身份帮助|取消关联验证)(?:\s+(.*))?', text.strip(), re.S)
    if not command: return None
    from union_rollout import policy_for
    policy = policy_for(event, scope, root)
    gray = bool(policy and policy['mode'] == 'apply')
    help_text = GRAY_HELP if gray else HELP
    if gray and command[1] in ('关联身份', '确认关联', '取消关联验证'):
        return '用户自行取码与确认流程已停用。可靠平台身份存在时自动归类，证据不足时保留独立来源。'
    if gray and command[1] == '身份帮助':
        return help_text
    if gray:
        from union_user_profiles import observe as observe_selected
        observed = observe_selected(event, scope)
    else:
        observed = observe(event, scope)
    if observed is None or not observed.get('app'):
        return '当前消息身份资料未通过核验，请稍后重试；未修改称呼或关联。'
    now = time.time() if now is None else now
    op, arg = command[1], (command[2] or '').strip()
    if op == '身份帮助': return help_text
    try:
        with _store(root) as store:
            key, row = _row(store, scope, observed, now)
            pending = store['pending']
            # Keep expired requests until the next command only; they never bind.
            expired = {k for k,p in pending.items() if p['expires'] <= now}
            for k in expired: del pending[k]
            if op == '设置称呼':
                if not 1 <= len(arg) <= 32 or any(unicodedata.category(c).startswith('C') for c in arg):
                    return '称呼需为 1–32 个可见字符。'+help_text
                name = dict(value=arg, kind='self_selected', source='dsh.self_selected', at=now)
                for r in store['sources'].values():
                    if r['person'] == row['person'] and _domain(r) == _domain(row): r['nickname'] = name
                return '已将你的称呼设为「'+arg+'」。这是你本人设置的称呼。'
            if op == '取消关联验证':
                for k in [k for k,p in pending.items() if p['owner']==key]: del pending[k]
                return '已取消由当前私聊发起的关联验证。已有关联未改变。'
            if op == '关联身份' and not arg:
                if not scope.private: return '请先在与我的私聊中发送「关联身份」。'
                issued = [at for at in row.get('issued', []) if at > now-600]
                if len(issued) >= 5: return '关联请求较频繁，请稍后再试。'
                row['issued'] = issued+[now]
                for k in [k for k,p in pending.items() if p['owner']==key]: del pending[k]
                if len(pending) >= 128: return '关联验证繁忙，请稍后再试。'
                code = _code()
                pending[_hash(code)] = dict(owner=key, domain=_domain(row), expires=now+300)
                return '请在你本人所在群中向我发送「关联身份 '+code+'」。5 分钟有效。群聊认领后，仍须回到本私聊确认；不要替别人确认。'
            if not re.fullmatch(r'[A-Z2-7]{16}', arg): return '验证码格式无效。'+help_text
            if op == '关联身份':
                if scope.private: return '此步骤需在你本人的群聊中发送；私聊发起请只发「关联身份」。'
                p = pending.get(_hash(arg))
                if not p or p['domain'] != _domain(row): return '关联码无效或已过期，请从原私聊重新发起。'
                if p.get('claim'):
                    if p['claim'] != key: del pending[_hash(arg)]
                    return '关联码已被认领；多来源竞争时已取消，请从原私聊重新发起。'
                challenge = _code(); p.update(claim=key, confirmation=_hash(challenge))
                return '尚未关联。请由发起者回到原私聊发送「确认关联 '+challenge+'」。仅在这条回复对应你本人发出的群消息时确认；有其他人抢用关联码请取消并重试。'
            if not scope.private: return '最终确认只能由发起者在原私聊完成。'
            match = next(((k,p) for k,p in pending.items() if p.get('confirmation')==_hash(arg) and p['owner']==key and p['domain']==_domain(row)), None)
            if not match: return '确认码无效或已过期，请从原私聊重新发起。'
            token, p = match; candidate = store['sources'][p['claim']]
            rows = [r for r in store['sources'].values() if r['person'] in (row['person'],candidate['person']) and _domain(r)==_domain(row)]
            del pending[token]
            if _blocked(root, rows): return '这些来源已有人工解除或否认记录，未自动关联，请联系维护者核对。'
            if _proof_conflict(root, rows): return '平台身份资料存在冲突，未关联，请联系维护者核对。'
            if len(rows) > 20: return '每个人物最多关联 20 个来源，未修改。'
            names = [r.get('nickname') for r in rows if r.get('nickname')]
            chosen = max(names, key=lambda n:n['at']) if names else None
            for r in rows:
                r['person'] = row['person']
                if chosen: r['nickname'] = chosen
            return '已关联。以后这些来源自动归到同一用户，消息仍分别标记私聊和具体群聊。'+('' if chosen else ' '+help_text)
    except (OSError, ValueError, TypeError, KeyError):
        return '身份资料暂时不可用，请稍后重试；未覆盖已有资料。'


def onboarding(event, scope, root, *, now=None):
    """One local hint per unnamed source; called only for an ordinary text reply."""
    observed = observe(event, scope)
    if observed is None or not observed.get('app') or observed.get('nickname'): return None
    now = time.time() if now is None else now
    try:
        with _store(root) as store:
            _, row = _row(store, scope, observed, now)
            if row.get('nickname') or row.get('hinted_at'): return None
            row['hinted_at'] = now
            from union_rollout import policy_for
            policy = policy_for(event, scope, root)
            return '我还没有你的称呼。'+(GRAY_HELP if policy and policy['mode'] == 'apply' else HELP)
    except (OSError, ValueError, TypeError, KeyError):
        return None
