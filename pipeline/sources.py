"""Collectors. Each returns (items, status). Items are dicts:
{source, title, url, metric(float), metric_label, extra{}}.
Never invent data: on failure return [] and an error status."""
import datetime as dt, html, json, re, time, os
import xml.etree.ElementTree as ET
import requests

UA = "TrendsRadar/1.0 (personal research dashboard; contact pascalicchio@gmail.com)"
S = requests.Session(); S.headers["User-Agent"] = UA
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _get(url, **kw):
    kw.setdefault("timeout", 25)
    r = S.get(url, **kw); r.raise_for_status(); return r

def _ok(n, note=""): return {"status": "ok", "items": n, "note": note}
def _err(e): return {"status": "error", "items": 0, "note": str(e)[:300]}

# ---------------- Hacker News ----------------
def hackernews(limit=60):
    try:
        ids = _get("https://hacker-news.firebaseio.com/v0/topstories.json").json()[:limit]
        now = time.time(); out = []
        for i in ids:
            it = _get(f"https://hacker-news.firebaseio.com/v0/item/{i}.json").json() or {}
            if not it.get("title"): continue
            age_h = max(0.5, (now - it.get("time", now)) / 3600)
            out.append({"source": "hackernews", "title": it["title"],
                        "url": f"https://news.ycombinator.com/item?id={i}",
                        "metric": it.get("score", 0) / age_h ** 0.8,
                        "metric_label": f"{it.get('score',0)} pts, {it.get('descendants',0)} comments, {age_h:.0f}h old",
                        "extra": {"link": it.get("url"), "score": it.get("score", 0)}})
        return out, _ok(len(out))
    except Exception as e: return [], _err(e)

# ---------------- Wikipedia most-read (with 5-day view history) ----------------
SKIP_WIKI = re.compile(r"^(Main_Page|Special:|Wikipedia:|Portal:|File:|Help:|Talk:|Deaths_in_|List_of_.*deaths|XXX|Pornhub|xHamster|Cleopatra)", re.I)
def wikipedia_mostread():
    for back in (1, 2, 3):
        d = dt.datetime.utcnow().date() - dt.timedelta(days=back - 1)
        try:
            j = _get(f"https://api.wikimedia.org/feed/v1/wikipedia/en/featured/{d:%Y/%m/%d}").json()
        except Exception as e:
            last = e; continue
        arts = (j.get("mostread") or {}).get("articles") or []
        if not arts: continue
        out = []
        for a in arts:
            t = a["title"]
            if SKIP_WIKI.search(t): continue
            hist = [h["views"] for h in a.get("view_history", [])]
            base = sum(hist[:-1]) / max(1, len(hist) - 1) if len(hist) > 1 else None
            vel = (hist[-1] / base) if base else None
            out.append({"source": "wikipedia", "title": t.replace("_", " "),
                        "url": "https://en.wikipedia.org/wiki/" + t,
                        "metric": a["views"], "metric_label": f"{a['views']:,} views" + (f", {vel:.1f}x vs prior 4-day avg" if vel else ""),
                        "extra": {"velocity": vel, "history": hist, "description": a.get("description", ""), "date": j["mostread"].get("date")}})
        return out, _ok(len(out), f"most-read for {j['mostread'].get('date')}")
    return [], _err(last if 'last' in dir() else "no mostread data")

# ---------------- Google News RSS ----------------
GN_TOPICS = ["", "NATION", "WORLD", "BUSINESS", "TECHNOLOGY", "SCIENCE", "HEALTH", "ENTERTAINMENT", "SPORTS"]
def google_news():
    out, errs = [], []
    for t in GN_TOPICS:
        url = ("https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en" if not t else
               f"https://news.google.com/rss/headlines/section/topic/{t}?hl=en-US&gl=US&ceid=US:en")
        try:
            root = ET.fromstring(_get(url).content)
        except Exception as e: errs.append(f"{t or 'TOP'}: {e}"); continue
        for rank, it in enumerate(root.findall(".//item")[:30]):
            title = it.findtext("title") or ""
            title = re.sub(r"\s+-\s+[^-]+$", "", title)  # strip publisher
            desc = it.findtext("description") or ""
            coverage = max(1, desc.count("<li>"))
            out.append({"source": "googlenews", "title": html.unescape(title), "url": it.findtext("link"),
                        "metric": coverage + max(0, 30 - rank) / 30, "metric_label": f"{t.title() or 'Top'} #{rank+1}, {coverage} outlets in cluster",
                        "extra": {"section": t or "TOP", "rank": rank + 1, "pub": it.findtext("pubDate")}})
    # de-dupe same headline across sections
    seen, ded = set(), []
    for x in out:
        k = x["title"].lower()[:80]
        if k in seen: continue
        seen.add(k); ded.append(x)
    st = _ok(len(ded), "; ".join(errs)) if ded else _err("; ".join(errs) or "empty")
    return ded, st

# ---------------- Google Trends "trending now" RSS ----------------
def google_trends(geos=("US", "MX", "GB")):
    out, errs = [], []
    ns = {"ht": "https://trends.google.com/trending/rss"}
    for g in geos:
        url = f"https://trends.google.com/trending/rss?geo={g}"
        try: root = ET.fromstring(_get(url).content)
        except Exception as e: errs.append(f"{g}: {e}"); continue
        for rank, it in enumerate(root.findall(".//item")):
            q = it.findtext("title") or ""
            traffic = it.findtext("ht:approx_traffic", namespaces=ns) or "0"
            n = int(re.sub(r"[^0-9]", "", traffic) or 0)
            news = [{"title": html.unescape(ni.findtext("ht:news_item_title", namespaces=ns) or ""),
                     "url": ni.findtext("ht:news_item_url", namespaces=ns),
                     "source": ni.findtext("ht:news_item_source", namespaces=ns)} for ni in it.findall("ht:news_item", ns)]
            out.append({"source": "googletrends", "title": q,
                        "url": f"https://trends.google.com/trends/explore?geo={g}&q=" + requests.utils.quote(q),
                        "metric": n, "metric_label": f"{g}: {traffic} searches",
                        "extra": {"geo": g, "rank": rank + 1, "news": news[:3], "pub": it.findtext("pubDate")}})
    st = _ok(len(out), "; ".join(errs)) if out else _err("; ".join(errs) or "empty")
    return out, st

# ---------------- Reddit public JSON ----------------
def reddit(subs):
    out, errs = [], []
    for sub, listing in subs:
        url = f"https://www.reddit.com/r/{sub}/{listing}.json?limit=25&raw_json=1" + ("&t=day" if listing == "top" else "")
        try:
            r = S.get(url, timeout=20)
            if r.status_code != 200: errs.append(f"r/{sub}/{listing}: HTTP {r.status_code}"); continue
            for c in r.json()["data"]["children"]:
                d = c["data"]
                if d.get("over_18") or d.get("stickied"): continue
                age_h = max(0.5, (time.time() - d["created_utc"]) / 3600)
                out.append({"source": "reddit", "title": d["title"], "url": "https://www.reddit.com" + d["permalink"],
                            "metric": d.get("score", 0) / age_h ** 0.8,
                            "metric_label": f"r/{d['subreddit']} {listing}: {d.get('score',0)} upvotes, {d.get('num_comments',0)} comments, {age_h:.0f}h old",
                            "extra": {"subreddit": d["subreddit"], "listing": listing, "score": d.get("score", 0)}})
        except Exception as e: errs.append(f"r/{sub}: {e}")
        time.sleep(1.2)
    if out: return out, _ok(len(out), "; ".join(errs[:5]))
    return [], {"status": "blocked", "items": 0, "note": ("; ".join(errs[:4]) + " ... Reddit blocks anonymous requests from this network; needs a free Reddit API (script) app + OAuth credentials.")[:400]}

# ---------------- Snapshots written by a Grok Bot routine (X, YouTube via MCP) ----------------
def _snapshot(name, max_age_h=36):
    p = os.path.join(ROOT, "snapshots", f"{name}.json")
    if not os.path.exists(p): return None, {"status": "missing", "items": 0, "note": f"snapshots/{name}.json not present (written by Grok Bot routine)"}
    j = json.load(open(p))
    ts = dt.datetime.fromisoformat(j["captured_at"].replace("Z", "+00:00"))
    age = (dt.datetime.now(dt.timezone.utc) - ts).total_seconds() / 3600
    if age > max_age_h: return None, {"status": "stale", "items": 0, "note": f"snapshot is {age:.0f}h old (captured {j['captured_at']})"}
    return j, {"status": "ok", "items": 0, "note": f"snapshot captured {j['captured_at']} ({age:.0f}h ago)"}

def x_snapshot():
    j, st = _snapshot("x")
    if not j: return [], st
    out = []
    for geo, trends in (j.get("trends") or {}).items():
        for rank, t in enumerate(trends):
            name = t.get("trend_name") or t.get("name")
            if not name: continue
            out.append({"source": "x", "title": name, "url": t.get("url") or "https://x.com/search?q=" + requests.utils.quote(name),
                        "metric": (t.get("tweet_count") or 0) or max(1, 50 - rank),
                        "metric_label": f"X trend {geo} #{rank+1}" + (f", {t['tweet_count']:,} posts" if t.get("tweet_count") else ""),
                        "extra": {"geo": geo, "rank": rank + 1, "kind": "trend"}})
    for rank, n in enumerate(j.get("news") or []):
        out.append({"source": "x", "title": n.get("name", ""), "url": n.get("url"),
                    "metric": max(1, 40 - rank), "metric_label": f"X news story ({', '.join((n.get('contexts') or {}).get('topics', [])[:2]) or n.get('category','')})",
                    "extra": {"kind": "news", "summary": (n.get("hook") or n.get("summary") or "")[:400], "keywords": n.get("keywords", []), "query": n.get("_query")}})
    st["items"] = len(out); return out, st

def youtube_snapshot():
    j, st = _snapshot("youtube")
    if not j: return [], st
    out = []
    for feed, vids in (j.get("feeds") or {}).items():
        for rank, v in enumerate(vids):
            if not v.get("title"): continue
            out.append({"source": "youtube", "title": v["title"], "url": f"https://www.youtube.com/watch?v={v['id']}",
                        "metric": v.get("view_count_int") or 0,
                        "metric_label": f"YouTube {feed} #{rank+1}: {v.get('view_count_text','')}, {v.get('published_time_text','')}",
                        "extra": {"feed": feed, "channel": (v.get("channel") or {}).get("title"), "published": v.get("published_time_text")}})
    st["items"] = len(out); return out, st
