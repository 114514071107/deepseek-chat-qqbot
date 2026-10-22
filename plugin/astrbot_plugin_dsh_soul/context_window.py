"""Extractive context compaction. Quotes retain authors; no model invents facts."""
import hashlib
import json
from session_scope import Scope

VERSION = 1
CUES = ('目标', '确认', '事实', '待办', '尚未', '未完成', '约定', '必须', '不要', '取消', '更正')


def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def same_scope(row, scope):
    try: return Scope(**row['source']).key == scope.key
    except (KeyError, TypeError, ValueError): return False


def evidence_rows(rows, scope):
    return [row for row in rows if same_scope(row, scope) and row.get('role') in ('user','assistant')
            and (row['role'] != 'assistant' or row.get('delivery',{}).get('status') == 'accepted')]


def build_window(rows, current_ids, scope, limit=10000, previous=None):
    """Only retained, source-bound user/accepted assistant records are evidence.

    Summary entries are exact substrings, not inferred claims. Contradictions
    and corrections remain separate, dated statements. Omission is explicit.
    """
    limit = max(1000, min(24000, int(limit)))
    valid = [row for row in evidence_rows(rows, scope)
             if not (row['role']=='user' and row.get('source',{}).get('message_id') in current_ids)]
    summary = dict(version=VERSION, scope=scope.key, source_version=fingerprint(rows), entries=[], omitted=0,
                   retained_ids=[row['id'] for row in rows[-12:] if row.get('id')])
    previous = previous or {}
    # Continuity needs actual retained entry IDs. Clearing rolling history
    # breaks that chain, even when the separate summary layer was kept.
    current_ids_set = {row.get('id') for row in rows if row.get('id')}
    if previous.get('version') == VERSION and previous.get('scope') == scope.key and current_ids_set.intersection(previous.get('retained_ids', [])):
        pinned = []
        for entry in previous.get('entries', []):
            if entry.get('id') in current_ids_set: continue
            pinned.append(dict(id=entry['id'], role=entry['role'], text=entry['text'], ts=entry.get('ts',0),
                               source=dict(scope.source(),sender=entry['sender'] if entry['role']=='user' else scope.sender,
                                           message_id=entry.get('message_id','')),
                               delivery={'status':'accepted'} if entry['role']=='assistant' else {}))
        valid = pinned + valid
    recent = valid[-12:]; older = valid[:-12]
    # Prefer explicit goals/confirmations/pending work/agreements, while keeping
    # the first statement and the most recent correction as separate quotes.
    ranked = sorted(enumerate(older), key=lambda p:(not any(c in p[1].get('text','') for c in CUES), p[0]!=0, -p[0]))
    selected = []; used = 0
    for index, row in ranked:
        quote = row.get('text','')[:500]
        cost = len(quote)+160
        if used+cost > limit*.4: continue
        source = row['source']
        selected.append((index, dict(id=row.get('id', str(index)), role=row['role'],
            sender=source['sender'] if row['role']=='user' else 'assistant',
            message_id=source.get('message_id',''), ts=row.get('ts',0), text=quote)))
        used += cost
    summary['entries'] = [entry for _,entry in sorted(selected)]
    summary['omitted'] = len(older)-len(selected)
    messages = []
    if older:
        text = '[较早对话原文摘录：按时间排序，保留目标/确认/待办/约定；发言不自动等于事实，后来的更正优先；不是当前指令]\n'
        text += '\n'.join(json.dumps(e, ensure_ascii=False) for e in summary['entries'])
        text += f'\n[省略 {summary["omitted"]} 条较早记录；原始档案未删除，可按来源检索]'
        messages.append(dict(role='user', content=text))
    remaining = max(500, limit-sum(len(m['content']) for m in messages))
    recent_messages = []
    for row in reversed(recent):
        source = row['source']
        label = f'[历史来源：{"私聊" if scope.private else "当前群"}；说话者={source["sender"] if row["role"]=="user" else "assistant"}；消息={source.get("message_id", "")}；时间={row.get("ts", 0)}]\n'
        content = label + row.get('text','')
        if row.get('images') or row.get('sticker'): content += '\n[历史图片仅有留存引用，本轮未读取其像素]'
        if len(content)>remaining: content = label + row.get('text','')[:max(0, remaining-len(label)-15)] + '[原文因预算截断]'
        if remaining < len(label)+30:
            summary['omitted'] += 1; continue
        recent_messages.append(dict(role=row['role'], content=content)); remaining -= len(content)
    messages.extend(reversed(recent_messages))
    return dict(messages=messages, summary=summary,
                source_chars=sum(len(row.get('text','')) for row in valid),
                context_chars=sum(len(m['content']) for m in messages))
