import json, os, sys
d = os.path.dirname(os.path.abspath(__file__))
html = open(os.path.join(d, "index.html")).read()
tok = os.environ.get("CF_BEACON_TOKEN", "").strip()
if tok:
    html = html.replace("<!--BEACON-->", "<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{\"token\":\"%s\"}'></script>" % tok)
js = open(os.path.join(d, "worker.template.js")).read().replace("__HTML__", json.dumps(html))
open(os.path.join(d, "worker.js"), "w").write(js)
print("worker.js", len(js), "beacon" if tok else "NO beacon")
# Also write the Cloudflare MCP `execute` deploy snippet (pass it as "$file:/workspace/trends-radar/worker/deploy_code.js").
code = ('async () => { const code = ' + json.dumps(js) + '; const metadata = { main_module: "worker.js", compatibility_date: "2026-11-01" };'
        ' const form = new FormData(); form.append("metadata", new Blob([JSON.stringify(metadata)], { type: "application/json" }));'
        ' form.append("worker.js", new Blob([code], { type: "application/javascript+module" }), "worker.js");'
        ' const r = await cloudflare.request({ method: "PUT", path: `/accounts/${accountId}/workers/scripts/trends-radar`, body: form });'
        ' return {ok: r.success}; }')
open(os.path.join(d, "deploy_code.js"), "w").write(code)
