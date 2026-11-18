#!/usr/bin/env python3
"""Assemble snapshots/x.json and snapshots/youtube.json from raw MCP result files.
Usage:
  make_snapshot.py x  --trends US=<file> --trends Worldwide=<file> [--trends MX=<file> --trends GB=<file>] --news <file> [--news <file> ...]
  make_snapshot.py youtube --feed trending=<file> --feed shorts=<file>
Each <file> is the text a CallDynamicTool(write_to_file=true) produced; the JSON body is extracted from it."""
import argparse, json, os, datetime as dt
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import re
def body(path):
    t = open(path, encoding="utf-8").read()
    m = re.search(r"Full text: (\S+?\.txt)", t)  # tool output was truncated; the full text lives in another file
    if m and os.path.exists(m.group(1)): t = open(m.group(1), encoding="utf-8").read()
    return json.JSONDecoder(strict=False).raw_decode(t[t.index("{"):])[0]
ap = argparse.ArgumentParser(); ap.add_argument("kind", choices=["x", "youtube"])
ap.add_argument("--trends", action="append", default=[]); ap.add_argument("--news", action="append", default=[])
ap.add_argument("--feed", action="append", default=[]); a = ap.parse_args()
snap = {"captured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
if a.kind == "x":
    snap["trends"] = {}
    for spec in a.trends:
        geo, f = spec.split("=", 1); snap["trends"][geo] = body(f).get("data", [])
    seen, news = set(), []
    for f in a.news:
        for n in body(f).get("data", []):
            if n.get("id") in seen: continue
            seen.add(n.get("id")); news.append(n)
    snap["news"] = news
    print("X trends:", {k: len(v) for k, v in snap["trends"].items()}, "news:", len(news))
else:
    snap["feeds"] = {}
    for spec in a.feed:
        name, f = spec.split("=", 1); b = body(f); d = b.get("data", b)
        snap["feeds"][name] = d.get("videos") or d.get("shorts") or d.get("items") or []
    print("YouTube feeds:", {k: len(v) for k, v in snap["feeds"].items()})
os.makedirs(os.path.join(ROOT, "snapshots"), exist_ok=True)
json.dump(snap, open(os.path.join(ROOT, "snapshots", f"{a.kind}.json"), "w"), ensure_ascii=False, indent=1)
