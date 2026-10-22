# -*- coding: utf-8 -*-
"""多引擎并行竞速搜索（原样移植自 brain.js 的 FREE_SEARCH_ENGINES 体系）"""
import asyncio
import html as html_mod
import re
import time

import aiohttp
from network_safety import fetch_public_bytes

FREE_ENGINES = ["so360", "bing-cn", "sogou"]
STALE_SITES_RE = re.compile(
    r"baike\.[a-z0-9.-]*\.com|wenku\.baidu\.com|zhidao\.baidu\.com|docin\.com|doc88\.com|book118\.com|renrendoc\.com", re.I)
CALENDAR_JUNK_RE = re.compile(
    r"黄历|老黄历|万年历|宜忌|日历网|rili\.com\.cn|tthuangli|历史上的今天|农历查询", re.I)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html_mod.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


async def fetch_text(session, url, timeout_ms, headers=None):
    hdrs = {"User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache"}
    if headers:
        hdrs.update(headers)
    raw = await asyncio.to_thread(fetch_public_bytes, url, timeout=timeout_ms / 1000, headers=hdrs)
    return raw.decode('utf-8', errors='replace')


def parse_bing_cn(html, top_n):
    results = []
    for block in re.split(r'<li class="b_algo[^"]*"', html, flags=re.I)[1:]:
        tm = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>\s*</h2>', block, re.I)
        if not tm:
            continue
        url = strip_html(tm.group(1))
        title = strip_html(tm.group(2))
        sm = (re.search(r'<div class="b_caption"[^>]*>[\s\S]*?<p[^>]*>([\s\S]*?)</p>', block, re.I)
              or re.search(r'<p[^>]*>([\s\S]*?)</p>', block, re.I))
        snippet = strip_html(sm.group(1)) if sm else ""
        if not title and not snippet:
            continue
        results.append({"title": title, "snippet": snippet, "url": url, "engine": "bing-cn"})
        if len(results) >= top_n:
            break
    return results


def parse_sogou(html, top_n):
    results = []
    for block in re.split(r'<div class="(?:vrwrap|rb)[^"]*"', html, flags=re.I)[1:]:
        tm = re.search(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>\s*</h3>', block, re.I)
        if not tm:
            continue
        url = strip_html(tm.group(1))
        title = strip_html(tm.group(2))
        rm = re.search(r"[?&]url=([^&]+)", url, re.I)
        if rm:
            try:
                import urllib.parse
                url = urllib.parse.unquote(rm.group(1))
            except Exception:
                pass
        sm = (re.search(r'<div class="str-text-info"[^>]*>([\s\S]*?)</div>', block, re.I)
              or re.search(r'<p class="str_info"[^>]*>([\s\S]*?)</p>', block, re.I)
              or re.search(r'<span class="str_info"[^>]*>([\s\S]*?)</span>', block, re.I))
        snippet = strip_html(sm.group(1)) if sm else ""
        if not title and not snippet:
            continue
        results.append({"title": title, "snippet": snippet, "url": url, "engine": "sogou"})
        if len(results) >= top_n:
            break
    return results


def parse_so360(html, top_n):
    results = []
    for block in re.split(r'<h3 class="res-title[^"]*"', html, flags=re.I)[1:]:
        tm = re.search(r'<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', block, re.I)
        if not tm:
            continue
        url = strip_html(tm.group(1))
        md = re.search(r'data-mdurl="([^"]+)"', block, re.I)
        if md:
            url = strip_html(md.group(1))
        title = strip_html(tm.group(2))
        sm = (re.search(r'<p class="res-desc[^"]*"[^>]*>([\s\S]*?)</p>', block, re.I)
              or re.search(r'<p[^>]*>([\s\S]*?)</p>', block, re.I))
        snippet = strip_html(sm.group(1)) if sm else ""
        if not title and not snippet:
            continue
        results.append({"title": title, "snippet": snippet, "url": url, "engine": "so360"})
        if len(results) >= top_n:
            break
    return results


def decode_json_string(s):
    try:
        return json_mod_loads('"' + s + '"')
    except Exception:
        return s


def json_mod_loads(s):
    import json
    try:
        return json.loads(s)
    except Exception:
        return s


async def search_baidu_hot(session, top_n, timeout_ms):
    html = await fetch_text(session, "https://top.baidu.com/board?tab=realtime", timeout_ms,
                            {"Referer": "https://www.baidu.com/"})
    results = []
    item_re = re.compile(
        r'"desc":"((?:[^"\\]|\\.)*)","hotChange":"[^"]*","hotScore":"\d+"[\s\S]{0,700}?"rawUrl":"((?:[^"\\]|\\.)*)"(?:[\s\S]{0,700}?)"word":"((?:[^"\\]|\\.)*)"')
    for m in item_re.finditer(html):
        if len(results) >= top_n:
            break
        title = html_mod.unescape(decode_json_string(m.group(3))).strip()
        snippet = html_mod.unescape(decode_json_string(m.group(1))).strip()
        url = html_mod.unescape(decode_json_string(m.group(2))).strip()
        if not title:
            continue
        results.append({"title": title, "snippet": snippet, "url": url, "engine": "baidu-top"})
    return results


async def search_one_engine(session, engine, query, top_n, timeout_ms):
    import urllib.parse
    q = urllib.parse.quote(query)
    if engine == "so360":
        html = await fetch_text(session, "https://www.so.com/s?q=" + q + "&pn=1", timeout_ms,
                                {"Referer": "https://www.so.com/"})
        return parse_so360(html, top_n)
    if engine == "bing-cn":
        html = await fetch_text(session, "https://cn.bing.com/search?q=" + q + "&setmkt=zh-CN&setlang=zh-CN",
                                timeout_ms, {"Referer": "https://cn.bing.com/"})
        return parse_bing_cn(html, top_n)
    if engine == "sogou":
        html = await fetch_text(session, "https://www.sogou.com/web?query=" + q, timeout_ms,
                                {"Referer": "https://www.sogou.com/"})
        return parse_sogou(html, top_n)
    return []


def char_bigrams(s):
    t = re.sub(r"\s+", "", (s or "").lower())
    return {t[i:i + 2] for i in range(len(t) - 1)}


def freshness_score(text, now=None):
    t = str(text or "")
    now = now or time.time() * 1000
    age_min = None
    m = re.search(r"(\d{1,3})\s*分钟(?:前|之前)", t)
    if m:
        age_min = int(m.group(1))
    if age_min is None:
        m = re.search(r"(\d{1,2})\s*小时(?:前|之前)", t)
        if m:
            age_min = int(m.group(1)) * 60
    if age_min is None:
        m = re.search(r"(\d{1,3})\s*天(?:前|之前)", t)
        if m:
            age_min = int(m.group(1)) * 1440
    if age_min is None and re.search(r"今天|刚刚", t):
        age_min = 720
    if age_min is None and re.search(r"昨天", t):
        age_min = 1440
    if age_min is None:
        m = re.search(r"(20\d{2})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})", t)
        if m:
            try:
                import datetime
                d = datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if d.timestamp() * 1000 <= now:
                    age_min = (now - d.timestamp() * 1000) / 60000
            except Exception:
                pass
    if age_min is None:
        # 只有"8月30日"没有年份：按当前年解析，若结果在未来超过 2 天则回退为上一年
        m = re.search(r"([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日", t)
        if m:
            try:
                import datetime
                y = datetime.datetime.fromtimestamp(now / 1000).year
                d = datetime.datetime(y, int(m.group(1)), int(m.group(2)))
                if d.timestamp() * 1000 - now > 2 * 86400000:
                    d = datetime.datetime(y - 1, int(m.group(1)), int(m.group(2)))
                if d.timestamp() * 1000 <= now:
                    age_min = (now - d.timestamp() * 1000) / 60000
            except Exception:
                pass
    if age_min is None:
        return 0
    if age_min <= 180:
        return 1.5
    if age_min <= 2880:
        return 1.2
    if age_min <= 43200:
        return 1.0
    if age_min <= 129600:
        return 0.7
    if age_min <= 525600:
        return 0.4
    return 0


NEWS_INTENT_RE = re.compile(r"新闻|热点|头条|时事|大事|发生了什么|最近.{0,8}(新闻|大事)|今天.{0,8}(新闻|大事|热点)")
TIME_SENSITIVE_RE = re.compile(r"推荐|最近|最新|新闻|天气|电影|电视剧|综艺|歌曲|热点|事件|比赛|股价|行情|发布|上映|播出|评分|票房", re.I)


def score_result(r, query, opts):
    s = 0
    title = str(r.get("title") or "")
    snippet = str(r.get("snippet") or "")
    text = title + " " + snippet
    if title:
        s += 1
    if len(snippet) >= 12:
        s += 0.5
    qb = char_bigrams(query)
    if qb:
        rb = char_bigrams(text)
        hit = sum(1 for g in qb if g in rb)
        s += 1.2 * (hit / len(qb))
    s += freshness_score(text)
    if opts.get("news_intent") and r.get("engine") == "baidu-top":
        s += 0.8
    if opts.get("news_intent") and CALENDAR_JUNK_RE.search(text):
        s -= 5
    elif opts.get("time_sensitive") and re.search(r"黄历|老黄历|万年历|宜忌", text):
        s -= 3
    if opts.get("time_sensitive") and STALE_SITES_RE.search(str(r.get("url") or "")):
        s -= 3
    return s


def dedup_key(r):
    url = str(r.get("url") or "")
    if url and not re.search(r"(so\.com/link|baidu\.com/link|baidu\.com/s\?wd=|baidu\.com/s\?ie=)", url, re.I):
        return re.sub(r"^https?://", "", url).rstrip("/").lower()
    return "t:" + re.sub(r"\s+", "", str(r.get("title") or "")).lower()


async def web_search(query, top_n=6, timeout_ms=10000):
    q0 = (query or "").strip()
    if not q0:
        return []
    time_sensitive = bool(TIME_SENSITIVE_RE.search(q0))
    news_intent = bool(NEWS_INTENT_RE.search(q0))
    async with aiohttp.ClientSession() as session:
        tasks = [asyncio.create_task(search_one_engine(session, e, q0, top_n, timeout_ms)) for e in FREE_ENGINES]
        if news_intent:
            tasks.append(asyncio.create_task(search_baidu_hot(session, top_n, timeout_ms)))
        results = await asyncio.gather(*tasks, return_exceptions=True)
    merged = []
    for r in results:
        if isinstance(r, list):
            merged.extend(r)
    seen = set()
    out = []
    for r in merged:
        k = dedup_key(r)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    scored = sorted(out, key=lambda r: -score_result(r, q0, {"time_sensitive": time_sensitive, "news_intent": news_intent}))
    return scored[:top_n]
