"""Run all collectors, cluster/score, write out/trends.json, out/TRENDS.md, out/latest-grok.md, history/<date>.jsonl."""
import json, os, re, sys, datetime as dt, concurrent.futures as cf, yaml
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(__file__))
import sources as S, hot_now as H, coming_up as C, footage as F

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
    return re.search(r"(?<![a-z0-9])" + re.escape(kw.lower()) + (r"" if kw.endswith(("archaeolog", "discover")) else r"(?![a-z0-9])"), text) is not None

def fit(text, label, chans):
    t = " " + text.lower() + " "; res = {}
    for c in chans:
        sc, hits = 0, []
        for w, kws in c["keywords"].items():
            for k in kws:
                if kw_hit(t, k): sc += int(w); hits.append(k)
        if any(kw_hit(t, k) for k in c.get("exclude", [])): sc = 0; hits.append("(excluded keyword)")
        sc = min(100, sc)
        angle = None
        if sc > 0:
            for rule in c.get("angles", []):
                if not rule["match"] or any(kw_hit(t, k) for k in rule["match"]):
                    angle = rule["angle"].replace("{topic}", label); break
        res[c["id"]] = {"score": sc, "matched": hits[:8], "angle_hint": angle}
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
    with cf.ThreadPoolExecutor(7) as ex:
        futs = {k: ex.submit(f) for k, f in collectors.items()}
        for k, fu in futs.items():
            try: its, st = fu.result()
            except Exception as e: its, st = [], {"status": "error", "items": 0, "note": str(e)[:300]}
            items += its; status[k] = st
    H.add_percentiles(items)
    groups, _ = H.cluster(items)
    topics = H.score(groups, {})
    chans = channels()
    hot = []
    for t in topics[:60]:
        txt = topic_text(t)
        f = fit(txt, t["label"], chans)
        best = max(f.items(), key=lambda kv: kv[1]["score"])
        regions = sorted({i["extra"].get("geo") for i in t["items"] if i["extra"].get("geo")})
        hot.append({"rank": len(hot) + 1, "topic": t["label"], "heat": t["heat"], "status": t["status"], "velocity": t["velocity"],
                    "why_hot": why(t), "sources": t["sources"], "regions": regions,
                    "broad_appeal": {"n_sources": t["n_sources"], "n_regions": len(regions)},
                    "paradox_signals": sorted({p.strip() for p in PARADOX if p in txt.lower()}),
                    "best_channel": best[0] if best[1]["score"] > 0 else None,
                    "channel_fit": f,
                    "links": [{"source": i["source"], "title": i["title"], "url": i["url"], "metric": i["metric_label"]}
                              for i in sorted(t["items"], key=lambda i: -i["_pct"])[:8]],
                    "keys": t["keys"]})
    # related topics (informational): another topic's key appears in this topic's headlines
    for h in hot:
        tx = " " + " ".join(H.norm(l["title"]) for l in h["links"]) + " "
        h["related_topics"] = [o["topic"] for o in hot if o is not h and any(len(k) >= 4 and (" " + k + " ") in tx for k in o["keys"])][:5]
    # footage (informational) for top 15 hot
    with cf.ThreadPoolExecutor(5) as ex:
        for h, fo in zip(hot[:15], ex.map(lambda h: F.check(h["topic"]), hot[:15])): h["footage"] = fo
    upcoming, ustatus = C.build(today_et, 56)
    for e in upcoming:
        txt = e["name"] + " " + " ".join(e.get("tags", []))
        e["channel_fit"] = fit(txt, e["name"], chans)
        b = max(e["channel_fit"].items(), key=lambda kv: kv[1]["score"])
        e["best_channel"] = b[0] if b[1]["score"] > 0 else None
    with cf.ThreadPoolExecutor(5) as ex:
        qs = [((e.get("hype_now") or {}).get("article") or e["name"]).replace("_", " ") for e in upcoming[:15]]
        for e, fo in zip(upcoming[:15], ex.map(F.check, qs)): e["footage"] = fo
    upcoming = upcoming[:40]
    doc = {
        "schema": "trends-radar/v1",
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
    }
    os.makedirs(OUT, exist_ok=True)
    json.dump(doc, open(os.path.join(OUT, "trends.json"), "w"), indent=1, ensure_ascii=False)
    open(os.path.join(OUT, "TRENDS.md"), "w").write(render_md(doc))
    open(os.path.join(OUT, "latest-grok.md"), "w").write(render_grok(doc, items))
    os.makedirs(os.path.join(ROOT, "history"), exist_ok=True)
    with open(os.path.join(ROOT, "history", f"{today_et}.jsonl"), "a") as fh:
        for h in hot[:60]:
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
