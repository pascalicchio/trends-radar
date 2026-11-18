"""Run all collectors, cluster/score, write out/trends.json, out/TRENDS.md, out/latest-grok.md, history/<date>.jsonl."""
import json, os, re, sys, datetime as dt, concurrent.futures as cf, yaml
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(__file__))
import sources as S, hot_now as H, coming_up as C, footage as F, feeds as FD, entity as EN

ROOT = S.ROOT; OUT = os.path.join(ROOT, "out"); ET = ZoneInfo("America/New_York")
PUBLIC_BASE = os.environ.get("PUBLIC_BASE", "https://trends-radar.pascalicchio.workers.dev")
REDDIT_SUBS = [("popular", "hot"), ("all", "rising"), ("UFOs", "hot"), ("space", "hot"), ("Damnthatsinteresting", "hot"),
               ("todayilearned", "hot"), ("Paleontology", "hot"), ("preppers", "hot"), ("weather", "hot"),
               ("technology", "hot"), ("ChatGPT", "hot"), ("news", "rising"), ("worldnews", "rising")]
PARADOX = ["mystery", "mysterious", "unexplained", "paradox", "impossible", "baffl", "puzzl", "strange", "secret", "hidden", "lost",
           "ancient", "discover", "first ever", "never before", "record", "anomal", "ufo", "uap", "why ", "how "]

def channels():
    return yaml.safe_load(open(os.path.join(ROOT, "config", "channels.yaml")))["channels"]

def kw_hit(text, kw):
    return re.search(r"(?<![a-z0-9])" + re.escape(kw.lower()) + r"(?![a-z0-9])", text) is not None

GATED = {"athlete", "sports_team", "sports_event", "actor", "musician", "music_work", "video_game", "film", "tv_series", "chess_player", "sports_heuristic"}
SPORTS_RX = re.compile(r"(?<![a-z])(nba|nfl|nhl|mlb|ncaa|wnba|mls|premier league|la liga|serie a|bundesliga|champions league|playoffs?|touchdowns?|quarterback|"
                       r"rebounds|assists|head coach|trade deadline|free agent|roster|box score|innings|wide receiver|point guard|linebacker|fifa|uefa|ufc|wwe|"
                       r"super bowl|grand prix|formula 1|world cup qualifier|qualifiers|basketball|football|soccer|baseball|hockey|tennis|golf|"
                       r"lakers|celtics|warriors|knicks|yankees|dodgers|cowboys|blue devils)(?![a-z])")

def entity_type(ent, headlines):
    et = (ent or {}).get("type")
    if et in (None, "other", "person"):
        hits = set(SPORTS_RX.findall(headlines.lower()))
        if len(hits) >= 2: return "sports_heuristic", sorted(hits)[:5]
    return et, None

def fit(text, label, chans, core=None, etype=None):
    """Informational channel fit. text = everything known about the topic; core = label + Wikipedia/Wikidata descriptions.
    Needs >=1 strong keyword in core, or >=2 distinct strong keywords anywhere. Gated entity types (sports, celebrity,
    video game, film...) need the type allowed by the channel AND a strong keyword in core."""
    t = " " + text.lower() + " "; c0 = " " + (core if core is not None else text).lower() + " "; res = {}
    # if the topic itself (label/description) is a strong keyword of some channel(s), other channels that only match via headlines get 0
    owners = [c["id"] for c in chans if any(kw_hit(c0, k) for k in c.get("strong", []))]
    for c in chans:
        strong = [k for k in c.get("strong", []) if kw_hit(t, k)]
        strong_core = [k for k in strong if kw_hit(c0, k)]
        weak = [k for k in c.get("weak", []) if kw_hit(t, k)]
        note = None
        if not strong: sc = 0
        elif not strong_core and len(set(strong)) < 2: sc = 0; note = "only one strong keyword, and only in headlines"
        else: sc = min(100, 45 * min(2, len(set(strong))) + 8 * min(3, len(set(weak))))
        if sc and etype in GATED and (etype not in c.get("entity_types_ok", []) or not strong_core):
            sc = 0; note = f"gated: entity type '{etype}' not a fit for this channel"
        if sc and owners and c["id"] not in owners: sc = 0; note = "topic itself matches " + ", ".join(owners) + "; only headline matches here"
        if sc and any(kw_hit(t, k) for k in c.get("exclude", [])): sc = 0; note = "excluded keyword"
        angle = None
        if sc > 0:
            for rule in c.get("angles", []):
                if not rule["match"] or any(kw_hit(t, k) for k in rule["match"]):
                    angle = rule["angle"].replace("{topic}", label); break
        res[c["id"]] = {"score": sc, "strong": strong[:6], "weak": weak[:6], "angle_hint": angle}
        if note: res[c["id"]]["note"] = note
    return res

def topic_text(t):
    parts = [t["label"]]
    for it in t["items"]:
        parts += [it["title"], it["extra"].get("description") or "", it["extra"].get("summary") or ""]
        parts += [n.get("title", "") for n in it["extra"].get("news", [])]
    return " ".join(parts)

def why(t):
    bits = [f"{t['n_sources']} source(s): " + ", ".join(t["sources"])]
    bits += t["velocity_notes"][:2]
    for s in ["wikipedia", "googletrends", "x", "googlenews", "hackernews", "reddit", "youtube"]:
        its = [i for i in t["items"] if i["source"] == s]
        if its: bits.append(max(its, key=lambda i: i["metric"])["metric_label"])
    return "; ".join(bits[:6])

def main():
    now = dt.datetime.now(dt.timezone.utc); today_et = now.astimezone(ET).date()
    collectors = {"hackernews": S.hackernews, "wikipedia": S.wikipedia_mostread, "googlenews": S.google_news,
                  "googletrends": S.google_trends, "reddit": lambda: S.reddit(REDDIT_SUBS),
                  "x": S.x_snapshot,
                  "youtube": S.youtube_api}
    items, status = [], {}
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {k: ex.submit(f) for k, f in collectors.items()}
        ffut = ex.submit(FD.collect, today_et)
        for k, fu in futs.items():
            try: its, st = fu.result()
            except Exception as e: its, st = [], {"status": "error", "items": 0, "note": str(e)[:300]}
            items += its; status[k] = st
        try: fitems, fstatus, chfeeds, recent = ffut.result()
        except Exception as e: fitems, fstatus, chfeeds, recent = [], {"feeds": {"status": "error", "items": 0, "note": str(e)[:300]}}, {}, []
    items += fitems
    for k, v in fstatus.items(): status["feed:" + k] = v
    H.add_percentiles(items)
    groups, _ = H.cluster(items)
    topics = H.score(groups, {})
    chans = channels()
    for n, t in enumerate(topics): t["_rank"] = n + 1
    # typed + fit-scored: the top 200 by heat, plus up to 150 lower-heat topics whose label/headline has a strong channel keyword
    # (so niche channels like chess still get picks). hot_now shows the top 40; channel_picks scans all of these.
    def any_strong(t):
        tx = " " + topic_text(t).lower() + " "
        return any(kw_hit(tx, k) for c in chans for k in c.get("strong", []))
    top = topics[:200] + [t for t in topics[200:] if any_strong(t)][:150]
    for t in top:
        w = [i for i in t["items"] if i["source"] == "wikipedia" and not i["extra"].get("geo")]
        t["wiki_title"] = max(w, key=lambda i: i["metric"])["title"] if w else None
    EN.type_topics(top)
    hot = []
    for t in top:
        txt = topic_text(t)
        core = " ".join([t["label"], t.get("wiki_title") or "", (t.get("entity") or {}).get("description") or ""]
                        + [i["extra"].get("description") or "" for i in t["items"] if i["source"] == "wikipedia"])
        etype, sports_hits = entity_type(t.get("entity"), txt)
        f = fit(txt, t["label"], chans, core=core, etype=etype)
        best = max(f.items(), key=lambda kv: kv[1]["score"])
        regions = sorted({i["extra"].get("geo") for i in t["items"] if i["extra"].get("geo")})
        ent = dict(t["entity"] or {}, type=etype) if (t.get("entity") or etype) else None
        if ent and sports_hits: ent["heuristic_hits"] = sports_hits
        hot.append({"rank": t["_rank"], "topic": t["label"], "heat": t["heat"], "status": t["status"], "velocity": t["velocity"],
                    **H.history_fields(t["keys"], today_et),
                    "why_hot": why(t), "sources": t["sources"], "regions": regions,
                    "broad_appeal": {"n_sources": t["n_sources"], "n_regions": len(regions)},
                    "entity": ent,
                    "paradox_signals": sorted({p.strip() for p in PARADOX if p in txt.lower()}),
                    "best_channel": best[0] if best[1]["score"] > 0 else None,
                    "channel_fit": f,
                    "links": [{"source": i["source"], "title": i["title"], "url": i["url"], "metric": i["metric_label"]}
                              for i in sorted(t["items"], key=lambda i: -i["_pct"])[:8]],
                    "keys": t["keys"]})
    # per-channel picks: top 5 by heat among the top-200 topics with fit > 0 (rank within a channel is still by heat)
    channel_picks = {c["id"]: [{"rank": h["rank"], "topic": h["topic"], "heat": h["heat"], "fit": h["channel_fit"][c["id"]]["score"],
                                "strong": h["channel_fit"][c["id"]]["strong"], "angle_hint": h["channel_fit"][c["id"]]["angle_hint"],
                                "url": h["links"][0]["url"] if h["links"] else None}
                               for h in hot if h["channel_fit"][c["id"]]["score"] > 0][:5] for c in chans}
    # related topics (informational): another topic's key appears in this topic's headlines
    for h in hot:
        tx = " " + " ".join(H.norm(l["title"]) for l in h["links"]) + " "
        h["related_topics"] = [o["topic"] for o in hot if o is not h and any(len(k) >= 4 and (" " + k + " ") in tx for k in o["keys"])][:5]
    # footage (informational) for top 15 hot
    with cf.ThreadPoolExecutor(5) as ex:
        for h, fo in zip(hot[:15], ex.map(lambda h: F.check(h["topic"]), hot[:15])): h["footage"] = fo
    upcoming, ustatus = C.build(today_et, 56)
    CAT_TAGS = {"film": ["entertainment", "film"], "launch": ["space", "science"], "astronomy": ["space", "science", "sky event"],
                "holiday": ["holiday", "culture"], "anniversary": ["history"], "awards": ["entertainment", "awards"],
                "sports": ["sports"], "shopping": ["shopping", "consumer"], "seasonal": ["seasonal", "weather"]}
    CAP = {"film": 4}  # per-category cap so film releases don't crowd out the list
    kept, cnt = [], {}
    for e in upcoming:
        cnt[e["category"]] = cnt.get(e["category"], 0) + 1
        if cnt[e["category"]] > CAP.get(e["category"], 99): continue
        e["category_tags"] = CAT_TAGS.get(e["category"], [e["category"]]) + (["chess"] if "chess" in e["name"].lower() else [])
        kept.append(e)
    upcoming = kept
    for e in upcoming:
        txt = e["name"] + " " + " ".join(e.get("tags", [])) + " " + " ".join(e.get("category_tags", []))
        e["channel_fit"] = fit(txt, e["name"], chans)
        b = max(e["channel_fit"].items(), key=lambda kv: kv[1]["score"])
        e["best_channel"] = b[0] if b[1]["score"] > 0 else None
    with cf.ThreadPoolExecutor(5) as ex:
        qs = [((e.get("hype_now") or {}).get("article") or e["name"]).replace("_", " ") for e in upcoming[:15]]
        for e, fo in zip(upcoming[:15], ex.map(F.check, qs)): e["footage"] = fo
    upcoming = upcoming[:40]
    def brief(i):
        return {"title": i["title"], "url": i["url"], "feed": i["extra"].get("feed"), "lang": i["extra"].get("lang"),
                "published": i["extra"].get("published"), "metric": i["metric_label"]}
    channel_feeds = {}
    for c in chans:
        its = sorted(chfeeds.get(c["id"], []), key=lambda i: -i.get("_pct", 0))
        seen, out_ = set(), []
        for i in its:
            k = H.norm(i["title"])[:60]
            if k in seen: continue
            seen.add(k); out_.append(brief(i))
        if out_: channel_feeds[c["id"]] = out_[:25]
    desks = {}
    for g in ("factcheck", "oddities"):
        its = sorted([i for i in fitems if i["source"] == g], key=lambda i: i["extra"].get("published") or "", reverse=True)
        desks[g] = [brief(i) for i in its[:25]]
    # round-robin across feeds (newest first within each) so one busy feed doesn't fill the list
    byf = {}
    for i in sorted(recent, key=lambda i: i["extra"].get("published") or "", reverse=True): byf.setdefault(i["extra"].get("feed"), []).append(i)
    rr = [x for tup in __import__("itertools").zip_longest(*byf.values()) for x in tup if x]
    seen, last7 = set(), []
    for i in rr:
        k = H.norm(i["title"])[:60]
        if k in seen: continue
        seen.add(k); last7.append(dict(brief(i), group=i["source"]))
    doc = {
        "schema": "trends-radar/v1.1",
        "generated_at": now.isoformat(timespec="seconds"),
        "generated_at_et": now.astimezone(ET).strftime("%Y-%m-%d %I:%M %p ET"),
        "urls": {"dashboard": PUBLIC_BASE + "/", "json": PUBLIC_BASE + "/trends.json", "markdown": PUBLIC_BASE + "/TRENDS.md",
                 "grok_md": PUBLIC_BASE + "/latest-grok.md"},
        "ranking_note": "Hot Now ranked purely by heat (cross-source mentions + per-source strength + velocity vs baseline). "
                        "Coming Up ranked by likely_heat (Wikipedia attention now / last year's peak, momentum, proximity). "
                        "channel_fit, paradox_signals and footage are informational and never change rank.",
        "sources": status, "coming_up_sources": ustatus,
        "channels": [{"id": c["id"], "name": c["name"], "format": c.get("format")} for c in chans],
        "top5_candidates": [{"rank": h["rank"], "topic": h["topic"], "heat": h["heat"], "best_channel": h["best_channel"],
                             "angle_hint": (h["channel_fit"].get(h["best_channel"]) or {}).get("angle_hint") if h["best_channel"] else None,
                             "footage_confidence": (h.get("footage") or {}).get("confidence")} for h in hot[:5]],
        "hot_now": hot[:40], "coming_up": upcoming,
        "channel_picks": channel_picks, "channel_feeds": channel_feeds, "desk_feeds": desks, "happened_last_7_days": last7[:50],
    }
    os.makedirs(OUT, exist_ok=True)
    json.dump(doc, open(os.path.join(OUT, "trends.json"), "w"), indent=1, ensure_ascii=False)
    open(os.path.join(OUT, "TRENDS.md"), "w").write(render_md(doc))
    open(os.path.join(OUT, "latest-grok.md"), "w").write(render_grok(doc, items))
    os.makedirs(os.path.join(ROOT, "history"), exist_ok=True)
    with open(os.path.join(ROOT, "history", f"{today_et}.jsonl"), "a") as fh:
        for h in hot[:80]:
            fh.write(json.dumps({"t": doc["generated_at"], "keys": h["keys"], "topic": h["topic"], "heat": h["heat"], "sources": h["sources"]}, ensure_ascii=False) + "\n")
    print(json.dumps({k: v["status"] + f" ({v['items']})" for k, v in {**status, **ustatus}.items()}, indent=0))
    return doc

CH = {"go-there-instead": "GTI", "intern-broke-it": "TIBI", "plan-not-panic": "PNP", "silver-paradox": "SP", "chess-blunder-club": "CBC"}
def fits_line(f):
    return ", ".join(f"{CH.get(k,k)} {v['score']}" for k, v in sorted(f.items(), key=lambda kv: -kv[1]["score"]) if v["score"] > 0) or "no channel fit"

def render_md(d):
    L = [f"# Trends Radar: {d['generated_at_et']}", "",
         f"Machine-readable: {d['urls']['json']} · Dashboard: {d['urls']['dashboard']}", "",
         "> " + d["ranking_note"], "", "## Sources", ""]
    for k, v in {**d["sources"], **d["coming_up_sources"]}.items():
        L.append(f"- **{k}**: {v['status']} ({v['items']} items){' - ' + v['note'] if v.get('note') else ''}")
    L += ["", "## Top 5 candidates (by heat)", ""]
    for c in d["top5_candidates"]:
        L.append(f"{c['rank']}. **{c['topic']}** (heat {c['heat']}) - best fit: {c['best_channel'] or 'none'}; footage: {c['footage_confidence']}"
                 + (f"\n   - angle hint: {c['angle_hint']}" if c["angle_hint"] else ""))
    L += ["", "## Channel picks (top 5 by heat with channel fit)", ""]
    for c in d["channels"]:
        ps = d.get("channel_picks", {}).get(c["id"], [])
        L.append(f"**{c['name']}** (`{c['id']}`): " + ("; ".join(f"#{p['rank']} [{p['topic']}]({p['url']}) (heat {p['heat']}, fit {p['fit']})" for p in ps) or "no fitting topic this run"))
    for k, v in d.get("channel_feeds", {}).items():
        L += ["", f"### Niche feed: {k}", ""] + [f"- [{x['title']}]({x['url']}) ({x['metric']})" for x in v[:10]]
    L += ["", "## Happened in the last 7 days (space, NASA, DoD, AARO)", ""] + [f"- {(x['published'] or '')[:10]} [{x['title']}]({x['url']}) ({x['feed']})" for x in d.get("happened_last_7_days", [])[:20]]
    for k, v in d.get("desk_feeds", {}).items():
        L += ["", f"## Desk: {k}", ""] + [f"- [{x['title']}]({x['url']}) ({x['feed']})" for x in v[:12]]
    L += ["", "## Hot now", ""]
    for h in d["hot_now"][:25]:
        L.append(f"### {h['rank']}. {h['topic']}  (heat {h['heat']}, {h['status']})")
        L.append(f"- Why: {h['why_hot']}")
        L.append(f"- Fit: {fits_line(h['channel_fit'])}")
        if h["best_channel"]: L.append(f"- Angle hint ({h['best_channel']}): {h['channel_fit'][h['best_channel']]['angle_hint']}")
        if h.get("footage"): L.append(f"- Footage (info only): {h['footage']['confidence']} - " + "; ".join(f"{c['source']}: {c.get('hits','err')}" for c in h["footage"]["checked"]))
        L.append("- Links: " + " · ".join(f"[{l['source']}]({l['url']})" for l in h["links"][:5]))
        L.append("")
    L += ["## Coming up (next 8 weeks)", ""]
    for e in d["coming_up"][:30]:
        hn = e.get("hype_now") or {}; ly = e.get("last_year") or {}
        L.append(f"- **{e['date']}** ({e['days_until']}d) **{e['name']}** - likely heat {e['likely_heat']}; {e['category']}; "
                 + (f"Wikipedia {hn.get('avg_daily_views_7d')}/day (x{hn.get('trend_ratio')}); " if hn else "")
                 + (f"last year peak {ly.get('peak_daily_views')}/day; " if ly else "")
                 + f"fit: {fits_line(e['channel_fit'])}; "
                 + (f"footage: {e['footage']['confidence']}; " if e.get("footage") else "")
                 + f"verified: {e['verified']}; [source]({e['source_url']})")
    return "\n".join(L) + "\n"

def render_grok(d, items):
    x = [i for i in items if i["source"] == "x"]
    L = [f"# X trends + cross-source radar: {d['generated_at_et']}", "",
         f"Source: Trends Radar ({d['urls']['dashboard']}). X status: {d['sources'].get('x', {}).get('status')} - {d['sources'].get('x', {}).get('note', '')}", ""]
    for geo in ["US", "Worldwide", "MX", "GB"]:
        ts = [i for i in x if i["extra"].get("kind") == "trend" and i["extra"].get("geo") == geo]
        if ts:
            L += [f"## X trends: {geo}", ""] + [f"{n+1}. [{i['title']}]({i['url']})" for n, i in enumerate(ts[:25])] + [""]
    news = [i for i in x if i["extra"].get("kind") == "news"]
    if news:
        L += ["## X news stories", ""] + [f"- [{i['title']}]({i['url']}): {i['extra'].get('summary','')[:240]}" for i in news[:20]] + [""]
    if not x: L += ["_No X snapshot available for this run (routine not run yet or snapshot older than 36h)._", ""]
    intl = [h for h in d["hot_now"] if len(h["regions"]) >= 2 or any(r in ("MX", "GB", "Worldwide") for r in h["regions"])]
    L += ["## Rising international", ""] + ([f"- **{h['topic']}** (heat {h['heat']}; regions: {', '.join(h['regions'])}) - {h['why_hot']}" for h in intl[:12]] or ["_none detected this run_"]) + [""]
    L += ["## Cross-source top 5 (by heat)", ""]
    for h in d["hot_now"][:5]:
        L.append(f"{h['rank']}. **{h['topic']}** (heat {h['heat']}, {h['n_sources'] if 'n_sources' in h else h['broad_appeal']['n_sources']} sources) - {h['why_hot']}")
        L.append("   - " + " · ".join(f"[{l['source']}]({l['url']})" for l in h["links"][:4]))
    return "\n".join(L) + "\n"

if __name__ == "__main__":
    main()
