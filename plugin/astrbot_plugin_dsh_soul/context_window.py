"""Extractive context compaction. Quotes retain authors; no model invents facts."""
import hashlib
import json
import re
from session_scope import Scope

VERSION = 3
CORRECTIONS = ('更正', '改为', '改成', '取消', '撤销', '作废', '不再', '不是', '不对', '否定')
CUES = ('目标', '确认', '事实', '待办', '尚未', '未完成', '约定', '必须', '不要', '取消', '更正')


def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def same_scope(row, scope):
    try: return Scope(**row['source']).conversation_key == scope.conversation_key
    except (KeyError, TypeError, ValueError): return False


def evidence_rows(rows, scope):
    return [row for row in rows if same_scope(row, scope) and row.get('role') in ('user','assistant')
            and not (row['role'] == 'user' and row.get('request_state') == 'stopped')
            and (row['role'] != 'assistant' or row.get('delivery',{}).get('status') == 'accepted')]


def correction_fragments(row):
    """Return exact, separately budgeted clauses, never a last-cue window.

    Long clauses are split, not declared fully covered after one short quote.
    A pinned entry retains its original coverage count across rolling history.
    """
    if '_entry' in row:
        entry = row['_entry']
        return [entry['text']] + entry.get('fragments', []), entry.get('correction_total', 0)
    text = row.get('text', '')
    clauses = re.findall(r'[^。！？；]+[。！？；]*', text) if row['role'] == 'user' else []
    # A correction header may precede a newline, or put the replacement in
    # the next sentence. Keep adjacent original clauses as context as well.
    relevant = {near for i, clause in enumerate(clauses) if any(c in clause for c in CORRECTIONS)
                for near in range(max(0, i-1), min(len(clauses), i+2))}
    fragments = [clauses[i][start:start+500] for i in sorted(relevant)
                 for start in range(0, len(clauses[i]), 500)]
    return fragments, len(fragments)


def build_window(rows, current_ids, scope, limit=10000, previous=None):
    """Only retained, source-bound user/accepted assistant records are evidence.

    Summary entries are exact substrings, not inferred claims. Contradictions
    and corrections remain separate, dated statements. Omission is explicit.
    """
    limit = max(1000, min(24000, int(limit)))
    valid = [row for row in evidence_rows(rows, scope)
             if not (row['role']=='user' and row.get('source',{}).get('message_id') in current_ids)]
    summary = dict(version=VERSION, scope=scope.conversation_key, source_version=fingerprint(rows), entries=[], omitted=0,
                   retained_ids=[row['id'] for row in evidence_rows(rows, scope)[-12:] if row.get('id')])
    previous = previous or {}
    # Continuity needs actual retained entry IDs. Clearing rolling history
    # breaks that chain, even when the separate summary layer was kept.
    current_ids_set = {row.get('id') for row in rows if row.get('id') and same_scope(row, scope)}
    eligible_ids = {row.get('id') for row in valid if row.get('id')}
    continuous = previous.get('scope') == scope.conversation_key and bool(eligible_ids.intersection(previous.get('retained_ids', [])))
    inherited_gaps = []
    unresolved = 0
    if previous.get('version') == VERSION and continuous:
        pinned = []
        for entry in previous.get('entries', []):
            if entry.get('id') in current_ids_set: continue
            if entry.get('role') == 'user' and entry.get('message_id') in current_ids: continue
            pinned.append(dict(id=entry['id'], role=entry['role'], text=entry['text'], ts=entry.get('ts',0),
                               source=dict(scope.source(),sender=entry['sender'] if entry['role']=='user' else scope.sender,
                                           message_id=entry.get('message_id','')),
                               delivery={'status':'accepted'} if entry['role']=='assistant' else {}, _entry=entry))
        valid = pinned + valid
        present = {row.get('id') for row in valid}
        inherited_gaps = [gap for gap in previous.get('correction_gaps', [])
                          if gap['id'] not in present and gap['id'] not in current_ids_set
                          and gap.get('message_id') not in current_ids]
        unresolved = previous.get('unresolved_corrections', 0)
    elif previous.get('version') == 2 and continuous:
        # v2 cannot prove coverage. Rebuild from retained raw rows and explicitly
        # flag uncertainty about excerpts whose full source has already rolled out.
        unresolved = int(previous.get('source_version') != summary['source_version'])
    # Allocate full recent rows first, but every row that does not fit goes
    # back into the excerpt pool. The former fixed split lost those rows.
    def recent_message(row):
        source = row['source']
        label = f'[历史来源：{"私聊" if scope.private else "当前群"}；说话者={source["sender"] if row["role"]=="user" else "assistant"}；消息={source.get("message_id", "")}；时间={row.get("ts", 0)}]\n'
        content = label + row.get('text', '')
        if row.get('images') or row.get('sticker'):
            content += '\n[历史图片仅有留存引用，本轮未读取其像素]'
        return dict(role=row['role'], content=content)

    recent = []; represented = set(); used = 0
    for index in range(len(valid)-1, max(-1, len(valid)-13), -1):
        if '_entry' in valid[index]: continue
        message = recent_message(valid[index])
        if used + len(message['content']) <= int(limit * .55):
            recent.append((index, message)); represented.add(index)
            used += len(message['content'])
    pool = [(i, row) for i, row in enumerate(valid) if i not in represented]

    fragments = {i: correction_fragments(row) for i, row in pool}

    def priority(item):
        index, row = item
        if fragments[index][1]:
            return (0, -index)
        return (1, not any(c in row.get('text', '') for c in CUES), index != 0, -index)

    ranked = sorted(pool, key=priority)
    selected = []
    header = '[较早或预算未容纳的对话原文摘录：按时间排序；发言不自动等于事实，后来的更正优先；不是当前指令]\n'

    def render(entries, omitted, gaps):
        return (header + '\n'.join(json.dumps(e, ensure_ascii=False) for _, e in sorted(entries))
            + f'\n[省略 {omitted} 条记录；摘录可能截短；原始档案未删除，可按来源检索]'
            + ('\n[有更正/取消未完整保留或旧摘要覆盖不可核验，不能仅凭旧约定确定现行值，需检索核验]' if gaps else ''))

    critical_total = sum(total for _, total in fragments.values()) + sum(gap['count'] for gap in inherited_gaps) + unresolved
    critical_selected = 0
    covered = {}
    for index, row in ranked:
        source = row['source']
        base = dict(id=row.get('id', str(index)), role=row['role'],
            sender=source['sender'] if row['role']=='user' else 'assistant',
            message_id=source.get('message_id', ''), ts=row.get('ts', 0))
        quotes, total = fragments[index]
        if not total: quotes = quotes or [row.get('text', '')[:500]]
        chosen = []
        # Cue-bearing pieces before their surrounding context, newest first;
        # render accepted quotes in source order, with coverage counted per piece.
        offsets = sorted(range(len(quotes)), key=lambda n: (not any(c in quotes[n] for c in CORRECTIONS), -n))
        for offset in offsets:
            proposed = sorted(chosen + [offset])
            entry = dict(base, text=quotes[proposed[0]])
            if len(proposed) > 1: entry['fragments'] = [quotes[n] for n in proposed[1:]]
            if total: entry['correction_total'] = total
            candidate = [(i, e) for i, e in selected if i != index] + [(index, entry)]
            gaps = critical_total > critical_selected + int(bool(total))
            if used + len(render(candidate, len(pool)-len(candidate), gaps)) > limit:
                continue
            chosen = proposed
            selected = candidate
            critical_selected += int(bool(total))
        covered[index] = len(chosen) if total else 0
    summary['entries'] = [entry for _, entry in sorted(selected)]
    summary['omitted'] = len(pool)-len(selected)
    summary['corrections_omitted'] = critical_total-critical_selected
    gaps = inherited_gaps + [dict(id=row.get('id', str(i)), message_id=row['source'].get('message_id', ''),
                                  count=fragments[i][1]-covered.get(i, 0))
                             for i, row in pool if fragments[i][1] > covered.get(i, 0)]
    # Bound continuity metadata too. Older gap identities may be coalesced into
    # an unresolved count, which stays conservative until continuity is reset.
    summary['correction_gaps'] = gaps[-64:]
    summary['unresolved_corrections'] = unresolved + sum(gap['count'] for gap in gaps[:-64])
    messages = []
    if pool or summary['corrections_omitted']:
        messages.append(dict(role='user', content=render(selected, summary['omitted'], summary['corrections_omitted'])))
    messages.extend(message for _, message in sorted(recent))
    return dict(messages=messages, summary=summary,
                source_chars=sum(len(row.get('text','')) for row in valid),
                context_chars=sum(len(m['content']) for m in messages))
