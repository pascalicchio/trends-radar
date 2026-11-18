"""Entity typing via Wikidata (P31 instance-of, P106 occupation) for topics with a known Wikipedia article,
or via a Wikidata label search for the topic label when the match is exact. Used only to gate channel fit."""
import re
from concurrent.futures import ThreadPoolExecutor
from sources import S

OCC = {  # P106 occupation -> type
    "athlete": {"Q2066131", "Q3665646", "Q19204627", "Q937857", "Q10871364", "Q11338576", "Q10833314", "Q11774891", "Q12299841",
                "Q10843402", "Q13156709", "Q378622", "Q4009406", "Q11513337", "Q15117302", "Q14089670", "Q11607585", "Q13474373",
                "Q13141064", "Q10843263", "Q13382576", "Q2309784", "Q15306067", "Q18515558", "Q19595175"},
    "chess_player": {"Q10873124"},
    "actor": {"Q33999", "Q10800557", "Q10798782", "Q2405480", "Q2259451", "Q245068", "Q947873", "Q4610556", "Q3282637", "Q2526255"},
    "musician": {"Q639669", "Q177220", "Q753110", "Q488205", "Q36834", "Q855091", "Q130857", "Q2252262", "Q183945", "Q386854"},
    "politician": {"Q82955", "Q30461", "Q193391", "Q372436"},
}
INST = {  # P31 instance-of -> type
    "video_game": {"Q7889", "Q865493"},
    "film": {"Q11424", "Q24869", "Q506240", "Q202866"},
    "tv_series": {"Q5398426", "Q15416", "Q526877", "Q1259759", "Q21191270"},
    "sports_team": {"Q13393265", "Q17156793", "Q476028", "Q12973014", "Q847017", "Q1194951", "Q4498974", "Q13027888", "Q18558301", "Q15944511", "Q103229495"},
    "sports_event": {"Q27020041", "Q13406554", "Q18608583", "Q16510064", "Q1079023", "Q500834", "Q46190676", "Q114609228"},
    "music_work": {"Q482994", "Q134556", "Q7366", "Q105543609"},
    "company": {"Q4830453", "Q783794", "Q891723", "Q6881511"},
}
CELEB = {"athlete", "actor", "musician", "sports_team", "sports_event", "video_game", "film", "tv_series", "music_work", "chess_player"}

DIAG = {"calls": 0, "failed": 0, "last_error": None}

def wm_json(url, params, timeout=25):
    """Wikimedia API GET with retry/backoff (CI runners sometimes get 429 / HTML error pages)."""
    import time
    for attempt in range(3):
        DIAG["calls"] += 1
        try:
            r = S.get(url, params=params, timeout=timeout)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"): return r.json()
            DIAG["last_error"] = f"HTTP {r.status_code} {r.headers.get('content-type','')} {r.text[:120]!r}"
            if r.status_code == 429: time.sleep(float(r.headers.get("retry-after", 3) or 3))
        except Exception as e: DIAG["last_error"] = str(e)[:160]
        time.sleep(1.5 * (attempt + 1))
    DIAG["failed"] += 1
    return {}

def _type_of(entity):
    claims = entity.get("claims", {})
    ids = lambda p: {c["mainsnak"].get("datavalue", {}).get("value", {}).get("id") for c in claims.get(p, []) if c.get("mainsnak")}
    p31, p106 = ids("P31"), ids("P106")
    for t, qs in INST.items():
        if p31 & qs: return t
    if "Q5" in p31:
        for t in ("chess_player", "athlete", "actor", "musician", "politician"):
            if p106 & OCC[t]: return t
        return "person"
    return "other"

def type_topics(topics):
    """topics: list of dicts with 'wiki_title' (en, optional) and 'label'. Adds entity {qid,type,source}."""
    titles = sorted({t["wiki_title"] for t in topics if t.get("wiki_title")})
    title_q = {}
    for i in range(0, len(titles), 50):
        try:
            j = wm_json("https://en.wikipedia.org/w/api.php", dict(action="query", prop="pageprops", ppprop="wikibase_item", redirects=1,
                      titles="|".join(titles[i:i + 50]), format="json", formatversion=2))
            norm = {n["to"]: n["from"] for n in j["query"].get("normalized", [])}
            red = {r["to"]: r["from"] for r in j["query"].get("redirects", [])}
            for p in j["query"]["pages"]:
                q = (p.get("pageprops") or {}).get("wikibase_item")
                if not q: continue
                t = p["title"]; t0 = red.get(t, t); t0 = norm.get(t0, t0)
                title_q[t0] = q; title_q[t] = q
        except Exception: pass
    # label search for the rest (exact label/alias match only)
    def search(t):
        if t.get("wiki_title") and title_q.get(t["wiki_title"]): t["_q"] = (title_q[t["wiki_title"]], "wikipedia article"); return
        lab = t["label"].lstrip("#")
        if len(lab) < 4 or len(lab.split()) > 4: return
        try:
            j = wm_json("https://www.wikidata.org/w/api.php", dict(action="wbsearchentities", search=lab, language="en", limit=1, format="json"))
            hit = (j.get("search") or [None])[0]
            if hit and hit.get("match", {}).get("text", "").lower() == lab.lower():
                t["_q"] = (hit["id"], f"wikidata search '{lab}' -> {hit.get('label')}")
        except Exception: pass
    with ThreadPoolExecutor(3) as ex: list(ex.map(search, topics))
    qs = sorted({t["_q"][0] for t in topics if t.get("_q")})
    ents = {}
    for i in range(0, len(qs), 50):
        try:
            j = wm_json("https://www.wikidata.org/w/api.php", dict(action="wbgetentities", ids="|".join(qs[i:i + 50]), props="claims|labels|descriptions",
                      languages="en", format="json"), timeout=30)
            ents.update(j.get("entities", {}))
        except Exception: pass
    for t in topics:
        if t.get("_q") and t["_q"][0] in ents:
            e = ents[t["_q"][0]]
            t["entity"] = {"qid": t["_q"][0], "type": _type_of(e), "description": (e.get("descriptions", {}).get("en") or {}).get("value"),
                           "matched_via": t["_q"][1], "url": f"https://www.wikidata.org/wiki/{t['_q'][0]}"}
        else:
            t["entity"] = None
        t.pop("_q", None)
    return topics
