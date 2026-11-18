"""Generic free feeds from config/feeds.yaml (RSS/Atom, Google News search, Wikimedia, Lichess, Spaceflight News)."""
import datetime as dt, html, re, os, time, email.utils, yaml, requests
import xml.etree.ElementTree as ET
from sources import S, ROOT

GN = {"en": ("en-US", "US", "US:en"), "es": ("es-419", "MX", "MX:es-419"), "pt": ("pt-BR", "BR", "BR:pt-419")}

def _date(s):
    if not s: return None
    try: return email.utils.parsedate_to_datetime(s).astimezone(dt.timezone.utc)
    except Exception: pass
    try: return dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except Exception: return None

def _rss(content):
    out = []
    try:
        root = ET.fromstring(content)
        for it in root.iter():
            tag = it.tag.split("}")[-1]
            if tag not in ("item", "entry"): continue
            g = lambda n: next((c for c in it if c.tag.split("}")[-1] == n), None)
            t = g("title"); l = g("link"); p = g("pubDate") or g("published") or g("updated") or g("date")
            link = (l.text or l.get("href")) if l is not None else None
            out.append({"title": html.unescape((t.text or "") if t is not None else "").strip(), "url": (link or "").strip(), "pub": p.text if p is not None else None})
    except ET.ParseError:
        txt = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
        for blk in re.findall(r"<item\b.*?</item>", txt, re.S)[:60]:
            t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", blk, re.S)
            l = re.search(r"<link>(.*?)</link>", blk, re.S); p = re.search(r"<pubDate>(.*?)</pubDate>", blk, re.S)
            if t: out.append({"title": html.unescape(re.sub("<[^>]+>", "", t.group(1))).strip(), "url": (l.group(1).strip() if l else ""), "pub": p.group(1) if p else None})
    return out

def fetch(f, today):
    k = f["kind"]; items = []
    if k in ("gnews", "gnews_top"):
        hl, gl, ceid = GN[f.get("lang", "en")]
        url = (f"https://news.google.com/rss?hl={hl}&gl={gl}&ceid={ceid}" if k == "gnews_top" else
               "https://news.google.com/rss/search?" + requests.compat.urlencode({"q": f["q"], "hl": hl, "gl": gl, "ceid": ceid}))
        r = S.get(url, timeout=25)
        if r.status_code == 429: time.sleep(3); r = S.get(url, timeout=25)
        r.raise_for_status()
        for rank, x in enumerate(_rss(r.content)[:40]):
            src = re.search(r"\s+-\s+([^-]+)$", x["title"]); title = re.sub(r"\s+-\s+[^-]+$", "", x["title"])
            items.append({"title": title, "url": x["url"], "pub": x["pub"], "rank": rank, "outlet": src.group(1).strip() if src else None})
    elif k == "rss":
        r = S.get(f["url"], timeout=25)
        if r.status_code >= 400:  # some publishers reject non-browser UAs; retry once with a browser UA
            r = requests.get(f["url"], timeout=25, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) TrendsRadar/1.1"})
        r.raise_for_status()
        items = [dict(x, rank=i) for i, x in enumerate(_rss(r.content)[:40])]
    elif k == "wikimostread":
        for back in (0, 1, 2):
            d = today - dt.timedelta(days=back)
            j = S.get(f"https://api.wikimedia.org/feed/v1/wikipedia/{f['lang']}/featured/{d:%Y/%m/%d}", timeout=25).json()
            arts = (j.get("mostread") or {}).get("articles") or []
            if arts: break
        for i, a in enumerate(arts[:40]):
            hist = [h["views"] for h in a.get("view_history", [])]
            base = sum(hist[:-1]) / max(1, len(hist) - 1) if len(hist) > 1 else None
            items.append({"title": a.get("normalizedtitle") or a["title"].replace("_", " "), "url": a["content_urls"]["desktop"]["page"],
                          "pub": None, "rank": i, "views": a["views"], "velocity": (hist[-1] / base) if base else None,
                          "description": a.get("description", ""), "en_title": None})
    elif k == "wikivoyage_top":
        for back in (1, 2, 3):
            d = today - dt.timedelta(days=back)
            r = S.get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikivoyage/all-access/{d:%Y/%m/%d}", timeout=25)
            if r.status_code == 200: break
        arts = [a for a in r.json()["items"][0]["articles"] if not re.match(r"(Special:|Main_Page|Wikivoyage:|File:|User:|Talk:)", a["article"])]
        items = [{"title": a["article"].replace("_", " "), "url": "https://en.wikivoyage.org/wiki/" + a["article"], "pub": None, "rank": i, "views": a["views"]} for i, a in enumerate(arts[:40])]
    elif k == "lichess_broadcasts":
        j = S.get(f["url"], timeout=25).json()
        for i, b in enumerate((j.get("active") or [])[:25]):
            t = b["tour"]; rd = b.get("round") or {}
            items.append({"title": t["name"] + (f" ({rd.get('name')})" if rd.get("name") else ""), "url": t.get("url") or f"https://lichess.org/broadcast/{t['slug']}/{t['id']}",
                          "pub": None, "rank": i, "description": (t.get("info") or {}).get("players", "")})
    elif k == "wikiwatch":  # daily pageviews for a fixed watch-list of articles (yesterday vs prior 7-day avg)
        end = today - dt.timedelta(days=1); start = end - dt.timedelta(days=7)
        for a in f["articles"]:
            lang, title = a.split(":", 1) if ":" in a[:4] else ("en", a)
            r = S.get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{lang}.wikipedia/all-access/user/"
                      f"{requests.utils.quote(title.replace(' ', '_'), safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}", timeout=20)
            if r.status_code != 200: continue
            v = [x["views"] for x in r.json().get("items", [])]
            if not v: continue
            base = sum(v[:-1]) / max(1, len(v) - 1)
            items.append({"title": title, "url": f"https://{lang}.wikipedia.org/wiki/" + title.replace(" ", "_"), "pub": None, "rank": 0,
                          "views": v[-1], "velocity": (v[-1] / base) if base else None, "description": f"{lang}.wikipedia daily views"})
        items.sort(key=lambda x: -x["views"])
        for i, x in enumerate(items): x["rank"] = i
    elif k == "snapi":
        j = S.get(f["url"], timeout=25).json()
        items = [{"title": a["title"], "url": a["url"], "pub": a.get("published_at"), "rank": i, "outlet": a.get("news_site")} for i, a in enumerate(j.get("results", []))]
    return items

def collect(today=None):
    today = today or dt.date.today()
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "feeds.yaml")))["feeds"]
    now = dt.datetime.now(dt.timezone.utc)
    all_items, status, channel_feeds, recent = [], {}, {}, []
    for f in cfg:
        try:
            raw = fetch(f, today)
            kept = []
            for x in raw:
                if not x.get("title"): continue
                pdt = _date(x.get("pub"))
                if pdt and (now - pdt).days > 7: continue
                age_h = max(0.5, (now - pdt).total_seconds() / 3600) if pdt else None
                n = len(raw)
                metric = x.get("views") or (max(1, n - x["rank"]) / (age_h ** 0.3 if age_h else 1))
                label = f"{f['id']} #{x['rank']+1}" + (f", {x['views']:,} views" if x.get("views") else "") + (f", {age_h:.0f}h old" if age_h else "") + (f", {x['outlet']}" if x.get("outlet") else "")
                if x.get("velocity"): label += f", {x['velocity']:.1f}x vs prior-days avg"
                it = {"source": f["group"], "title": x["title"], "url": x["url"], "metric": float(metric), "metric_label": label,
                      "extra": {"feed": f["id"], "geo": f.get("geo"), "published": pdt.isoformat() if pdt else None,
                                "description": x.get("description", ""), "velocity": x.get("velocity"), "lang": f.get("lang", "en")}}
                kept.append(it)
            all_items += kept
            for ch in f.get("channels", []):
                channel_feeds.setdefault(ch, []).extend(kept)
            if f.get("recent"): recent += kept
            status[f["id"]] = {"status": "ok" if kept else "empty", "items": len(kept), "note": f.get("note", "")}
        except Exception as e:
            status[f["id"]] = {"status": "error", "items": 0, "note": (str(e)[:200] + (" | " + f["note"] if f.get("note") else ""))}
        if f["kind"].startswith("gnews"): time.sleep(1.0)
    return all_items, status, channel_feeds, recent
