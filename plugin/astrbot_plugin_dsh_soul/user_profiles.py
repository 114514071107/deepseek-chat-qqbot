"""Management-only observations from matching adapter events; never auth/memory."""
import datetime
import json
import os
import re
import tempfile
import time
from pathlib import Path


def _text(value):
    if not isinstance(value, str):
        return ''
    return re.sub(r'[\x00-\x1f\x7f]', '', value).strip()[:128]


def _identifier(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return ''
    text = str(value)
    return text if 0 < len(text) <= 256 else ''


def _at(raw, fallback):
    try:
        return min(float(raw), time.time()) if isinstance(raw, (int, float)) else min(
            datetime.datetime.fromisoformat(str(raw).replace('Z', '+00:00')).timestamp(), time.time())
    except (ValueError, TypeError, OverflowError):
        return fallback


def observe(event, scope):
    """Accept an already bound Scope plus its matching platform message only."""
    raw = getattr(getattr(event, 'message_obj', None), 'raw_message', None)
    data = raw if isinstance(raw, dict) else getattr(raw, 'raw_data', None)
    if not isinstance(data, dict):
        return None
    identity = None
    nickname = card = None
    app = ''
    message_id = _identifier(data.get('message_id', data.get('id')))
    if not message_id or message_id != scope.message_id:
        return None
    if scope.platform == 'qq_official':
        author = data.get('author')
        if not isinstance(author, dict):
            return None
        field = 'user_openid' if scope.private else 'member_openid'
        if _identifier(author.get(field)) != scope.sender:
            return None
        if not scope.private and _identifier(data.get('group_openid')) != scope.group:
            return None
        http = getattr(getattr(getattr(event, 'bot', None), 'api', None), '_http', None)
        app = _identifier(getattr(getattr(http, '_token', None), 'app_id', None))
        user = _identifier(author.get('user_openid'))
        if app and user:
            identity = dict(namespace='qq_user_openid', value=user,
                            basis='qq_author_user' if scope.private else 'qq_author_pair')
        name = _text(author.get('username'))
        if name and name != scope.sender:
            nickname = dict(value=name, kind='platform_name', source='qq.author.username')
        member = data.get('member')
        if not scope.private and isinstance(member, dict) and _text(member.get('nick')):
            card = dict(value=_text(member['nick']), kind='group_card', source='qq.member.nick')
        stamp = data.get('timestamp')
    elif scope.platform == 'aiocqhttp':
        sender = data.get('sender')
        if (not isinstance(sender, dict) or data.get('post_type') != 'message'
                or data.get('anonymous') is not None or data.get('sub_type') == 'anonymous'):
            return None
        if (_identifier(sender.get('user_id')) != scope.sender or _identifier(data.get('user_id')) != scope.sender
                or _identifier(data.get('self_id')) != scope.bot
                or not re.fullmatch(r'[0-9]+', scope.sender) or not re.fullmatch(r'[0-9]+', scope.bot)):
            return None
        if (data.get('message_type') != ('private' if scope.private else 'group')
                or (not scope.private and _identifier(data.get('group_id')) != scope.group)):
            return None
        app = scope.bot
        identity = dict(namespace='onebot_qq', value=scope.sender, basis='onebot_message_sender')
        name = _text(sender.get('nickname'))
        if name and name != scope.sender:
            nickname = dict(value=name, kind='qq_nickname', source='onebot.sender.nickname')
        if not scope.private and _text(sender.get('card')):
            card = dict(value=_text(sender['card']), kind='group_card', source='onebot.sender.card')
        stamp = data.get('time')
    else:
        return None
    at = _at(stamp, scope.received_at)
    if not 0 < at <= time.time():
        return None
    for field in (nickname, card):
        if field:
            field.update(at=at, message_id=message_id)
    return dict(source=scope.source(), app=app, observed_at=at, message_id=message_id,
                identity=identity, nickname=nickname, group_card=card)


def record_profile(event, scope, directory):
    if event.get_extra('_dsh_profile_observed'):
        return
    row = observe(event, scope)
    if row is None:
        return
    file = Path(directory) / 'workbench_profiles_v1.json'
    if file.exists():
        if file.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('management profiles exceed read limit')
        store = json.loads(file.read_text(encoding='utf-8-sig'))
    else:
        store = dict(version=1, sources={})
    if store.get('version') != 1 or not isinstance(store.get('sources'), dict):
        raise ValueError('unsupported management profile store')
    old = store['sources'].get(scope.key, {})
    row['first_seen_at'] = old.get('first_seen_at', old.get('observed_at', time.time()))
    if old.get('app') and row.get('app') and old['app'] != row['app']:
        row['identity_conflict'] = True
    if old.get('identity') and row.get('identity') and old['identity'] != row['identity']:
        # The basis can improve from one event to another without conflict.
        if any(old['identity'].get(k) != row['identity'].get(k) for k in ('namespace', 'value')):
            row['identity_conflict'] = True
    if old.get('identity_conflict'):
        row['identity_conflict'] = True
    if (row['observed_at'], row['message_id']) < (old.get('observed_at', 0), old.get('message_id', '')):
        if row.get('identity_conflict') and not old.get('identity_conflict'):
            row = {**old, 'identity_conflict': True}
        else:
            event.set_extra('_dsh_profile_observed', True)
            return
    elif old.get('app', '') == row.get('app', ''):
        for field in ('nickname', 'group_card', 'identity'):
            if row.get(field) is None and old.get(field) is not None:
                row[field] = old[field]
    if row != old:
        if len(store['sources']) >= 10000 and scope.key not in store['sources']:
            raise ValueError('management profile source limit')
        store['sources'][scope.key] = row
        payload = json.dumps(store, ensure_ascii=False)
        if len(payload.encode('utf-8')) > 8 * 1024 * 1024:
            raise ValueError('management profile write limit')
        fd, temporary = tempfile.mkstemp(prefix=file.name+'.', suffix='.tmp', dir=file.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                out.write(payload)
            os.replace(temporary, file)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    event.set_extra('_dsh_profile_observed', True)
