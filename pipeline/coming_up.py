"""COMING UP: events in the next N days from real, sourced data. Every event carries source_url."""
import datetime as dt, re, os, yaml, concurrent.futures as cf
from sources import S, ROOT

def wiki_text(title):
    j = S.get("https://en.wikipedia.org/w/api.php", params=dict(action="query", prop="extracts", explaintext=1, titles=title,
              format="json", formatversion=2, redirects=1), timeout=25).json()
    return j["query"]["pages"][0].get("extract") or ""

def pageviews(article, start, end):
    """daily views list for [start,end] (dates)."""
    import requests
    a = article.replace(" ", "_")
    url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
           f"{requests.utils.quote(a, safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
    r = S.get(url, timeout=25)
    if r.status_code != 200: return None
    return [i["views"] for i in r.json().get("items", [])]

def hype_and_last_year(ev, today):
    out = {}
    art = ev.get("wiki_article")
    if art:
        v = pageviews(art, today - dt.timedelta(days=35), today - dt.timedelta(days=1))
        if v and len(v) >= 14:
            last7 = sum(v[-7:]) / 7; prior = sum(v[:-7]) / max(1, len(v) - 7)
            out["hype_now"] = {"article": art, "avg_daily_views_7d": round(last7), "avg_daily_views_prior_28d": round(prior),
                               "trend_ratio": round(last7 / prior, 2) if prior else None,
                               "url": f"https://pageviews.wmcloud.org/?project=en.wikipedia.org&pages={art}&range=latest-60"}
    d = dt.date.fromisoformat(str(ev["date"]))
    recurring = ev.get("_recurring", False)
    ly_art = ev.get("last_year_article") or (art if recurring else None)
    if ly_art:
        s, e = d.replace(year=d.year - 1) - dt.timedelta(days=3), d.replace(year=d.year - 1) + dt.timedelta(days=3)
        if e < today:
            v = pageviews(ly_art, s, e)
            if v:
                out["last_year"] = {"article": ly_art, "window": f"{s}..{e}", "peak_daily_views": max(v), "total_views": sum(v),
                                    "url": f"https://pageviews.wmcloud.org/?project=en.wikipedia.org&pages={ly_art}&start={s}&end={e}"}
    return out

def curated(today, horizon):
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "events.yaml")))["events"]
    out, cache = [], {}
    for ev in cfg:
        d = dt.date.fromisoformat(str(ev["date"]))
        if not (today <= d <= today + dt.timedelta(days=horizon)): continue
        v = ev.get("verify") or {}
        ok = False; note = ""
        try:
            key = v.get("wiki") or v.get("url")
            if key not in cache: cache[key] = wiki_text(v["wiki"]) if v.get("wiki") else S.get(v["url"], timeout=25).text
            ok = bool(re.search(v["pattern"], cache[key]))
            note = "date text found on source" if ok else "pattern NOT found on source today"
        except Exception as e: note = f"verify failed: {e}"
        out.append({"name": ev["name"], "date": str(d), "category": ev["category"], "source_url": ev["source_url"],
                    "verified": ok, "verify_note": note, "rule": ev.get("rule"), "tags": ev.get("tags", []),
                    "origin": "curated", "_ev": {**ev, "_recurring": ev["category"] in RECURRING}})
    return out

def nager(today, horizon):
    out = []
    for y in {today.year, (today + dt.timedelta(days=horizon)).year}:
        url = f"https://date.nager.at/api/v3/PublicHolidays/{y}/US"
        for h in S.get(url, timeout=25).json():
            d = dt.date.fromisoformat(h["date"])
            if today <= d <= today + dt.timedelta(days=horizon) and h.get("global", True):
                out.append({"name": h["name"] + " (US federal holiday)", "date": h["date"], "category": "holiday", "source_url": url,
                            "verified": True, "verify_note": "from Nager.Date API", "tags": ["holiday", h["name"].lower()], "origin": "nager",
                            "_ev": {"wiki_article": {"Thanksgiving Day": "Thanksgiving_(United_States)", "Christmas Day": "Christmas",
                                    "New Year's Day": "New_Year's_Day", "Martin Luther King, Jr. Day": "Martin_Luther_King_Jr._Day"}.get(h["name"]), "date": h["date"], "_recurring": True}})
    return out

def hebcal(today, horizon):
    out, seen = [], set()
    for y in {today.year, (today + dt.timedelta(days=horizon)).year}:
        url = f"https://www.hebcal.com/hebcal?v=1&cfg=json&maj=on&min=off&mod=off&nx=off&year={y}&month=x&ss=off&mf=off&c=off&geo=none&s=off"
        for i in S.get(url, timeout=25).json()["items"]:
            d = dt.date.fromisoformat(i["date"][:10])
            base = re.sub(r":.*", "", i["title"])
            if base in seen or not (today <= d <= today + dt.timedelta(days=horizon)): continue
            if base not in ("Chanukah", "Purim", "Passover", "Rosh Hashana", "Yom Kippur"): continue
            seen.add(base)
            out.append({"name": f"{base} begins", "date": str(d), "category": "holiday", "source_url": url, "verified": True,
                        "verify_note": "from Hebcal API", "tags": ["holiday", base.lower(), "hanukkah"], "origin": "hebcal",
                        "_ev": {"wiki_article": "Hanukkah" if base == "Chanukah" else None, "date": str(d), "_recurring": True}})
    return out

def usno(today, horizon):
    out = []
    for y in {today.year, (today + dt.timedelta(days=horizon)).year}:
        url = f"https://aa.usno.navy.mil/api/seasons?year={y}"
        for p in S.get(url, timeout=25).json()["data"]:
            d = dt.date(p["year"], p["month"], p["day"])
            if p["phenom"] in ("Solstice", "Equinox") and today <= d <= today + dt.timedelta(days=horizon):
                nm = ("Winter" if p["month"] == 12 else "Summer" if p["month"] == 6 else "Spring" if p["month"] == 3 else "Autumn")
                out.append({"name": f"{p['phenom']} ({nm.lower()} begins, N. Hemisphere) {p['time']} UTC", "date": str(d), "category": "astronomy",
                            "source_url": url, "verified": True, "verify_note": "from US Naval Observatory API",
                            "tags": ["solstice", "winter", "sun", "space", "astronomy"], "origin": "usno",
                            "_ev": {"wiki_article": "December_solstice" if p["month"] == 12 else None, "date": str(d), "_recurring": True}})
    return out

def launches(today, horizon, limit=6):
    url = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=40&mode=list"
    out = []
    for x in S.get(url, timeout=30).json().get("results", []):
        d = dt.date.fromisoformat(x["net"][:10])
        if not (today <= d <= today + dt.timedelta(days=horizon)): continue
        st = (x.get("status") or {}).get("abbrev")
        out.append({"name": f"Rocket launch: {x['name']}", "date": str(d), "category": "launch",
                    "source_url": f"https://ll.thespacedevs.com/2.2.0/launch/{x['id']}/", "verified": True,
                    "verify_note": f"The Space Devs Launch Library, status {st}, NET {x['net']}",
                    "tags": ["rocket", "launch", "space", "spacex" if "Falcon" in x["name"] or "Starship" in x["name"] else "space"],
                    "origin": "spacedevs", "_ev": {"date": str(d)}, "_rank": 0 if any(k in x["name"] for k in ("Starship", "Artemis", "New Glenn", "Crew", "Starliner")) else 1})
    out.sort(key=lambda e: (e["_rank"], e["date"]))
    return out[:limit]

RECURRING = {"shopping", "seasonal", "holiday", "awards", "astronomy", "sports"}
MONTHS = {"01": 1, "02": 2, "03": 3, "04": 4, "05": 5, "06": 6, "07": 7, "08": 8, "09": 9, "10": 10, "11": 11, "12": 12}
def films(today, horizon, top=8):
    """Parse Wikipedia 'List of American films of YYYY' release tables; rank by recent pageviews (hype)."""
    end = today + dt.timedelta(days=horizon); cand = []
    for y in sorted({today.year, end.year}):
        page = f"List_of_American_films_of_{y}"
        j = S.get("https://en.wikipedia.org/w/api.php", params=dict(action="parse", page=page, prop="wikitext", format="json", formatversion=2), timeout=30).json()
        t = (j.get("parse") or {}).get("wikitext") or ""
        month = day = None
        for line in t.split("\n"):
            m = re.search(r'data-sort-value="(\d\d)"', line)
            if line.startswith("!") and m and "aria-label" in line: month = MONTHS.get(m.group(1)); day = None; continue
            m = re.match(r"\|[^|\n]*\|\s*'''(\d{1,2})'''\s*$", line)
            if m: day = int(m.group(1)); continue
            m = re.match(r"\|\s*''\[\[([^\]|]+)(?:\|([^\]]+))?\]\]''", line)
            if m and month and day:
                try: d = dt.date(y, month, day)
                except ValueError: continue
                if today <= d <= end:
                    cand.append({"article": m.group(1).replace(" ", "_"), "title": m.group(2) or m.group(1), "date": d, "page": page})
    def pv(c):
        v = pageviews(c["article"], today - dt.timedelta(days=8), today - dt.timedelta(days=1))
        c["views7"] = sum(v) if v else 0; return c
    with cf.ThreadPoolExecutor(8) as ex: cand = list(ex.map(pv, cand))
    cand.sort(key=lambda c: -c["views7"])
    out = []
    for c in cand[:top]:
        out.append({"name": f"Film release: {c['title']}", "date": str(c["date"]), "category": "film",
                    "source_url": f"https://en.wikipedia.org/wiki/{c['page']}", "verified": True,
                    "verify_note": f"listed in Wikipedia {c['page'].replace('_',' ')} release table", "tags": ["movie", "film", "box office"],
                    "origin": "wikipedia-films", "_ev": {"wiki_article": c["article"], "date": str(c["date"])}})
    return out

def anniversaries(today, horizon, years=(25, 50, 75, 100, 150, 200, 250)):
    """Round-number anniversaries from Wikipedia 'On this day' (selected events)."""
    out = []
    def day(i):
        d = today + dt.timedelta(days=i)
        url = f"https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/selected/{d:%m/%d}"
        try: j = S.get(url, timeout=25).json()
        except Exception: return []
        res = []
        for e in j.get("selected", []):
            age = d.year - int(e.get("year", 0))
            if age in years:
                pages = e.get("pages") or []
                link = pages[0]["content_urls"]["desktop"]["page"] if pages else url
                res.append({"name": f"{age}th anniversary: {e['text'][:160]}", "date": str(d), "category": "anniversary",
                            "source_url": link, "verified": True, "verify_note": f"Wikipedia On This Day ({e['year']})",
                            "tags": ["anniversary", "history"], "origin": "wikipedia-onthisday",
                            "_ev": {"wiki_article": pages[0]["title"] if pages else None, "date": str(d)}})
        return res
    with cf.ThreadPoolExecutor(6) as ex:
        for r in ex.map(day, range(1, horizon + 1)): out += r
    return out

def build(today=None, horizon=56):
    today = today or dt.date.today()
    status, events = {}, []
    for name, fn in [("curated", curated), ("nager_holidays", nager), ("hebcal", hebcal), ("usno_seasons", usno),
                     ("launch_library", launches), ("wikipedia_films", films), ("wikipedia_onthisday", anniversaries)]:
        try:
            ev = fn(today, horizon); events += ev; status[name] = {"status": "ok", "items": len(ev), "note": ""}
        except Exception as e:
            status[name] = {"status": "error", "items": 0, "note": str(e)[:300]}
    # de-dupe by (date, name) and by (date, wiki article)
    seen, ded = set(), []
    for e in events:
        art = (e.get("_ev") or {}).get("wiki_article")
        ks = [(e["date"], re.sub(r"\W", "", e["name"].lower())[:30])] + ([(e["date"], art)] if art and e["origin"] != "wikipedia-onthisday" else [])
        if any(k in seen for k in ks): continue
        seen.update(ks); ded.append(e)
    def enrich(e):
        try: e.update(hype_and_last_year(e["_ev"], today))
        except Exception as ex: e["enrich_error"] = str(ex)[:200]
        return e
    with cf.ThreadPoolExecutor(8) as ex: ded = list(ex.map(enrich, ded))
    for e in ded:
        e.pop("_ev", None); e.pop("_rank", None)
        e["days_until"] = (dt.date.fromisoformat(e["date"]) - today).days
        e["likely_heat"] = likely_heat(e, horizon)
    ded.sort(key=lambda e: -e["likely_heat"])
    return ded, status

import math
def likely_heat(e, horizon):
    """0-100. Magnitude = Wikipedia attention now (or last year's peak for recurring events),
    momentum = 7d vs prior 28d views, proximity = sooner is hotter."""
    h, ly = e.get("hype_now") or {}, e.get("last_year") or {}
    mag_views = max(h.get("avg_daily_views_7d") or 0, (ly.get("peak_daily_views") or 0) * 0.5)
    mag = min(1.0, math.log10(1 + mag_views) / 5.5)
    ratio = h.get("trend_ratio") or 1.0
    mom = max(0.0, min(1.0, (ratio - 1) / 2))
    prox = 1.0 if e["days_until"] <= 14 else max(0.5, 1 - (e["days_until"] - 14) / (horizon * 1.5))
    return round(100 * (0.6 * mag + 0.2 * mom + 0.2 * prox), 1)
