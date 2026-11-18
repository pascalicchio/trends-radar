// Trends Radar Worker: serves the dashboard and proxies the exports committed by GitHub Actions.
// No secrets: data comes from a public GitHub repo (raw.githubusercontent.com), cached at the edge for 5 minutes.
const RAW = "https://raw.githubusercontent.com/pascalicchio/trends-radar/main/out/";
const FILES = { "/trends.json": ["trends.json", "application/json; charset=utf-8"],
                "/TRENDS.md": ["TRENDS.md", "text/markdown; charset=utf-8"],
                "/latest-grok.md": ["latest-grok.md", "text/markdown; charset=utf-8"] };
const HTML = __HTML__;
export default {
  async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === "/" || url.pathname === "/index.html")
      return new Response(HTML, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=300" } });
    const f = FILES[url.pathname];
    if (f) {
      const r = await fetch(RAW + f[0], { cf: { cacheTtl: 300, cacheEverything: true } });
      if (!r.ok) return new Response("upstream " + r.status, { status: 502 });
      return new Response(r.body, { headers: { "content-type": f[1], "cache-control": "public, max-age=300", "access-control-allow-origin": "*" } });
    }
    if (url.pathname === "/health") {
      const r = await fetch(RAW + "trends.json", { cf: { cacheTtl: 300, cacheEverything: true } });
      const d = r.ok ? await r.json() : null;
      return Response.json({ ok: !!d, generated_at: d && d.generated_at, sources: d && d.sources });
    }
    return new Response("not found", { status: 404 });
  }
};
