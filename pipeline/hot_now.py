"""Cluster items from all sources into topics and compute heat (cross-source + velocity vs baseline)."""
import re, math, json, os, glob, datetime as dt
from collections import defaultdict
from sources import ROOT

STOP = set("""a an the and or but of to in on at for with from by as is are was were be been being it its this that these those
he she they we you i his her their our your my me him them us not no yes do does did done has have had will would can could should
may might must than then there here what which who whom whose when where why how all any both each few more most other some such
only own same so too very just also into over under after before about against between through during up down out off again
further once new says said say live update updates watch video photos report reports news today tonight week year years day days
vs v first last next amid after over per via get gets got make makes made how why what top best""".split())
WEEKDAYS = set("monday tuesday wednesday thursday friday saturday sunday january february march april may june july august september october november december".split())
SOURCE_W = {"x": 1.0, "googletrends": 1.0, "reddit": 1.0, "wikipedia": 0.9, "googlenews": 0.9, "youtube": 0.8, "hackernews": 0.7,
            "factcheck": 0.8, "oddities": 0.7, "chess": 0.5, "travel": 0.5, "space": 0.5, "defense": 0.4}

ROMAN = {"ii": "2", "iii": "3", "iv": "4", "vi": "6", "vii": "7", "viii": "8", "ix": "9"}
import unicodedata
def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    w = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip().split()
    return " ".join(ROMAN.get(x, x) if i > 0 else x for i, x in enumerate(w))
def acronym(title):
    base = re.sub(r"\s*\(.*?\)", "", title); ws = base.split()
    if len(ws) < 3: return None
    tail = ws[-1] if re.fullmatch(r"[IVX]+|\d+", ws[-1]) else None
    caps = [w for w in (ws[:-1] if tail else ws) if w[0].isupper()]
    ac = "".join(w[0] for w in caps).lower()
    return norm(ac + (" " + tail if tail else "")) if len(ac) >= 3 else None
def tokens(s): return [w for w in norm(s).split() if len(w) > 2 and w not in STOP and w not in WEEKDAYS and not w.isdigit()]

GENERIC = {"united states", "new york", "white house", "supreme court", "world cup", "the new york times", "los angeles"}

def item_text(it):
    return " " + norm(it["title"] + " " + " ".join(n.get("title", "") for n in it["extra"].get("news", []))) + " "

def candidate_keys(items):
    """key(normalized) -> display label. Strong keys: Wikipedia titles, X trends, Google Trends queries,
    plus multi-word capitalized phrases seen in headlines."""
    keys = {}
    for it in items:
        t = it["title"]
        if it["source"] == "wikipedia":
            base = re.sub(r"\s*\(.*?\)", "", t); k = norm(base); keys.setdefault(k, (t, 3))
            ac = acronym(t)  # e.g. Grand Theft Auto VI -> "gta 6"
            if ac: keys.setdefault(ac, (t, 3))
        elif it["source"] == "x" and it["extra"].get("kind") == "trend":
            n = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t.lstrip("#")); keys.setdefault(norm(n), (t, 3))
        elif it["source"] == "googletrends":
            keys.setdefault(norm(t), (t, 3))
        for m in re.finditer(r"\b([A-Z][\w'’\.-]+(?:\s+(?:of|the|de|la|and|&)?\s*[A-Z][\w'’\.-]+){1,3})", t):
            k = norm(m.group(1)); w = k.split()
            if len(w) >= 2 and w[0] not in STOP and w[-1] not in STOP and w[0] not in WEEKDAYS and w[-1] not in WEEKDAYS:
                keys.setdefault(k, (m.group(1).strip("'’\"."), 1))
    return {k: v for k, v in keys.items() if len(k) >= 4 and k not in GENERIC and not all(x in STOP or x in WEEKDAYS or x.isdigit() for x in k.split())}

def cluster(items):
    """Seed-based assignment (no transitive chaining): each item joins the single best key it contains."""
    STRONG = lambda it: it["source"] in ("wikipedia", "googletrends") or (it["source"] == "x" and it["extra"].get("kind") == "trend")
    # strong items (a wiki title / a search query / an X trend) only join keys found in their own title
    texts = [(" " + norm(it["title"]) + " " + ((acronym(it["title"]) or "") + " " if it["source"] == "wikipedia" else "")) if STRONG(it) else item_text(it) for it in items]
    keys = candidate_keys(items)
    members = {}
    for k in keys:
        pat = " " + k + " "
        ids = [i for i, tx in enumerate(texts) if pat in tx]
        if ids: members[k] = ids
    def rank(k):
        ids = members[k]; srcs = {items[i]["source"] for i in ids}
        return (len(srcs), keys[k][1], len(k.split()), len(ids))
    order = sorted((k for k in members if len(members[k]) <= 25), key=rank, reverse=True)
    assigned, groups, labels = {}, [], []
    for k in order:
        free = [i for i in members[k] if i not in assigned]
        if not free: continue
        srcs = {items[i]["source"] for i in free}
        if len(free) == 1 and keys[k][1] < 3: continue  # weak single-item phrase: leave for its own singleton
        for i in free: assigned[i] = len(groups)
        groups.append([items[i] for i in free]); labels.append(keys[k][0])
    for i, it in enumerate(items):
        if i not in assigned: groups.append([it]); labels.append(None)
    for g, l in zip(groups, labels):
        for it in g: it["_label"] = l
    return merge_duplicates(groups), labels

class UF:
    def __init__(s, n): s.p = list(range(n))
    def f(s, x):
        while s.p[x] != x: s.p[x] = s.p[s.p[x]]; x = s.p[x]
        return x
    def u(s, a, b): s.p[s.f(a)] = s.f(b)

def canon_keys(group):
    """Keys that identify the same subject: Wikipedia article titles (+ acronym), X trend names, the label."""
    ks = set()
    for it in group:
        if it["source"] == "wikipedia" and it["extra"].get("geo") in (None, "en"):
            base = re.sub(r"\s*\(.*?\)", "", it["title"]); ks.add(norm(base))
            a = acronym(it["title"]); a and ks.add(a)
        if it["source"] == "x" and it["extra"].get("kind") == "trend":
            ks.add(norm(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", it["title"].lstrip("#"))))
    if group and group[0].get("_label"): ks.add(norm(group[0]["_label"]))
    return {k for k in ks if len(k) >= 4}

def merge_duplicates(groups):
    keys = [canon_keys(g) for g in groups]
    uf = UF(len(groups)); seen = {}
    for i, ks in enumerate(keys):
        for k in ks:
            if k in seen: uf.u(i, seen[k])
            else: seen[k] = i
    merged = defaultdict(list)
    for i, g in enumerate(groups): merged[uf.f(i)].extend(g)
    out = []
    for root, g in merged.items():
        lab = groups[root][0].get("_label") if groups[root] else None
        for it in g: it["_label"] = lab or it.get("_label")
        out.append(g)
    return out

def label_for(group):
    w = [it for it in group if it["source"] == "wikipedia" and not it["extra"].get("geo")] or [it for it in group if it["source"] == "wikipedia"]
    if w and len(group) > 1: return max(w, key=lambda it: (not it["title"].startswith("List of"), it["metric"]))["title"]
    if group and group[0].get("_label"):
        l = group[0]["_label"]
        return l.title() if l.islower() else l
    pref = {"wikipedia": 0, "googletrends": 1, "x": 2, "googlenews": 3, "reddit": 4, "hackernews": 5, "youtube": 6}
    best = sorted(group, key=lambda it: (pref.get(it["source"], 9), -it["metric"]))[0]
    return best["title"]

HIST_FULL = defaultdict(list)  # key -> [(iso_t, date, heat)]
def load_history(days=7):
    hist = defaultdict(list)
    files = sorted(glob.glob(os.path.join(ROOT, "history", "*.jsonl")))
    for n, f in enumerate(files):
        day = os.path.basename(f)[:10]
        for line in open(f):
            try: r = json.loads(line)
            except Exception: continue
            for k in r.get("keys", []):
                HIST_FULL[k].append((r["t"], day, r["heat"]))
                if n >= len(files) - days: hist[k].append(r["heat"])
    return hist

def history_fields(keys, today):
    rows = [r for k in keys for r in HIST_FULL.get(k, [])]
    if not rows: return {"first_seen": None, "days_trending": 0, "heat_yesterday": None}
    y = str(today - __import__("datetime").timedelta(days=1))
    hy = [h for t, d, h in rows if d == y]
    return {"first_seen": min(t for t, d, h in rows), "days_trending": len({d for t, d, h in rows}),
            "heat_yesterday": max(hy) if hy else None}

def score(groups, n_by_source):
    hist = load_history()
    topics = []
    for g in groups:
        srcs = defaultdict(list)
        for it in g: srcs[it["source"]].append(it)
        # per-source strength: item's rank-percentile within its source (robust to different metric scales)
        strength = 0.0
        for s, its in srcs.items():
            best = max(its, key=lambda x: x["metric"])
            strength += SOURCE_W.get(s, 0.7) * best["_pct"]
        n_src = len(srcs)
        cross = min(1.0, (n_src - 1) / 3)
        # velocity: wikipedia view ratio, google trends presence in multiple geos, history baseline
        vel = 0.0; why_vel = []
        for it in srcs.get("wikipedia", []):
            v = it["extra"].get("velocity")
            if v: vel = max(vel, min(1.0, (v - 1) / 4)); why_vel.append(f"Wikipedia views {v:.1f}x vs prior 4-day avg")
        geos = {it["extra"].get("geo") for it in g}
        geos.discard(None)
        if len(geos) >= 2: vel = max(vel, 0.6); why_vel.append(f"trending in {len(geos)} regions ({', '.join(sorted(geos))})")
        keys = sorted({norm(label_for(g))} | canon_keys(g))
        prev = [h for k in keys for h in hist.get(k, [])]
        status = "new" if not prev else "steady"
        h0 = 100 * (0.40 * cross + 0.45 * min(1.0, strength / 2.0) + 0.15 * vel)
        if prev:
            base = sum(prev) / len(prev)
            if h0 > base * 1.25: status = "rising"; vel = max(vel, min(1.0, (h0 / max(base, 1) - 1)))
            elif h0 < base * 0.75: status = "cooling"
        heat = round(100 * (0.40 * cross + 0.45 * min(1.0, strength / 2.0) + 0.15 * vel), 1)
        topics.append({"label": label_for(g), "heat": heat, "status": status, "n_sources": n_src, "sources": sorted(srcs),
                       "velocity": round(vel, 2), "velocity_notes": why_vel, "baseline_runs": len(prev), "items": g, "keys": keys})
    topics.sort(key=lambda t: -t["heat"])
    return topics

def add_percentiles(items):
    by = defaultdict(list)
    for it in items: by[it["source"]].append(it)
    for s, its in by.items():
        its.sort(key=lambda x: x["metric"])
        n = len(its)
        for i, it in enumerate(its): it["_pct"] = (i + 1) / n
