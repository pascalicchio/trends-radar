import json, os, sys
d = os.path.dirname(os.path.abspath(__file__))
html = open(os.path.join(d, "index.html")).read()
tok = os.environ.get("CF_BEACON_TOKEN", "").strip()
if tok:
    html = html.replace("<!--BEACON-->", "<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{\"token\":\"%s\"}'></script>" % tok)
js = open(os.path.join(d, "worker.template.js")).read().replace("__HTML__", json.dumps(html))
open(os.path.join(d, "worker.js"), "w").write(js)
print("worker.js", len(js), "beacon" if tok else "NO beacon")
