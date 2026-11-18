"""Informational only (never affects ranking): checks free/public video archives for footage on a topic."""
import re, requests
from sources import S

LICENSE = {
    "Wikimedia Commons (video)": "per-file license (mostly CC BY / CC BY-SA / public domain): check the file page and credit as required",
    "Internet Archive (movies)": "mixed: many public domain or CC, but uploads can be copyrighted; check each item's license/rights field",
    "NASA Image & Video Library (video)": "generally not copyrighted (US gov); no NASA endorsement implied; third-party content and logos excepted",
    "Library of Congress (film & video)": "varies: many items 'no known restrictions', others rights-restricted; check each item's Rights & Access",
}

def _q(label):
    q = re.sub(r"^(Film release|Rocket launch|\d+\w* anniversary):\s*", "", label)
    q = re.sub(r"[\(\)\[\]\"'|:#]", " ", q)
    return " ".join(q.split()[:6])

def check(label):
    q = _q(label); res = {"query": q, "checked": [], "to_verify": []}
    hits = 0; srcs = 0
    try:
        from entity import wm_json
        j = wm_json("https://commons.wikimedia.org/w/api.php", dict(action="query", list="search", srnamespace=6,
                  srsearch=f"{q} filetype:video", format="json", srlimit=3), timeout=20)
        n = j["query"]["searchinfo"]["totalhits"]; hits += min(n, 20); srcs += n > 0
        res["checked"].append({"source": "Wikimedia Commons (video)", "hits": n,
                               "url": "https://commons.wikimedia.org/w/index.php?search=" + requests.utils.quote(q + " filetype:video") + "&ns6=1",
                               "examples": ["https://commons.wikimedia.org/wiki/" + x["title"].replace(" ", "_") for x in j["query"]["search"][:2]]})
    except Exception as e: res["checked"].append({"source": "Wikimedia Commons (video)", "error": str(e)[:120]})
    try:
        j = S.get("https://archive.org/advancedsearch.php", params={"q": f"title:({q}) AND mediatype:movies", "fl[]": "identifier",
                  "rows": 2, "output": "json"}, timeout=20).json()
        n = j["response"]["numFound"]; hits += min(n, 20); srcs += n > 0
        res["checked"].append({"source": "Internet Archive (movies)", "hits": n,
                               "url": "https://archive.org/search?query=" + requests.utils.quote(f"title:({q})") + "&and[]=mediatype%3A%22movies%22",
                               "examples": ["https://archive.org/details/" + d["identifier"] for d in j["response"]["docs"]]})
    except Exception as e: res["checked"].append({"source": "Internet Archive (movies)", "error": str(e)[:120]})
    try:
        j = S.get("https://images-api.nasa.gov/search", params={"q": q, "media_type": "video"}, timeout=20).json()
        n = j["collection"]["metadata"]["total_hits"]; hits += min(n, 20); srcs += n > 0
        res["checked"].append({"source": "NASA Image & Video Library (video)", "hits": n,
                               "url": "https://images.nasa.gov/search?q=" + requests.utils.quote(q) + "&page=1&media=video",
                               "examples": ["https://images.nasa.gov/details/" + i["data"][0]["nasa_id"] for i in j["collection"]["items"][:2]]})
    except Exception as e: res["checked"].append({"source": "NASA Image & Video Library (video)", "error": str(e)[:120]})
    try:
        j = S.get("https://www.loc.gov/film-and-videos/", params={"q": q, "fo": "json", "c": 2}, timeout=30).json()
        n = j["pagination"]["of"]; hits += min(n, 20); srcs += n > 0
        res["checked"].append({"source": "Library of Congress (film & video)", "hits": n,
                               "url": "https://www.loc.gov/film-and-videos/?q=" + requests.utils.quote(q),
                               "examples": [r.get("id") for r in j.get("results", [])[:2] if r.get("id")]})
    except Exception as e: res["checked"].append({"source": "Library of Congress (film & video)", "error": str(e)[:120]})
    for c in res["checked"]: c["license_hint"] = LICENSE.get(c["source"])
    res["to_verify"] = [
        "DVIDS (US military public-domain video): https://www.dvidshub.net/search/?q=" + requests.utils.quote(q) + "&filter%5Btype%5D=video (API needs a key; not auto-checked)",
        "National Archives (NARA) catalog: https://catalog.archives.gov/search?q=" + requests.utils.quote(q) + "&typeOfMaterials=Moving%20Images (API needs a key; not auto-checked)","YouTube Creative Commons filter (search the topic, Filters > Creative Commons)",
                        "News-agency licensing (AP/Reuters/Storyful) or official channel/press-kit footage"]
    res["confidence"] = "high" if hits >= 10 and srcs >= 2 else "medium" if hits >= 3 else "low" if hits >= 1 else "none-found"
    res["note"] = ("Counts are keyword matches in public archives, not a relevance check; open the links before planning an episode. "
                   "'none-found' means stills-only risk for long-form.")
    return res
