# Finish Cloudflare Web Analytics (blocked on a Cloudflare permission)

Creating the Web Analytics site needs the Cloudflare MCP permission `account-settings.write`. Fillipe has to approve
the Cloudflare reconnect card first. After that:
1. Cloudflare `execute`: POST /accounts/{id}/rum/site_info {"host":"trends-radar.pascalicchio.workers.dev","auto_install":false}
   and read result.site_token (this is a public beacon token, fine to put in HTML).
2. `CF_BEACON_TOKEN=<site_token> python3 worker/build_worker.py`
3. Cloudflare `execute` with code "$file:/workspace/trends-radar/worker/deploy_code.js"
4. Check that `curl -s https://trends-radar.pascalicchio.workers.dev/ | grep cloudflareinsights` returns a match.
