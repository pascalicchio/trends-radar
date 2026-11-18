# Trends Radar: handoff for Claude Code

Trends Radar is a public, read-only feed of what's hot now and what's coming up in the next 8 weeks, scored against
the channels (Go There Instead, The Intern Broke It, Plan Not Panic, Silver Paradox, Chess Blunder Club / Clube do Vacilo). Use it to pick the next video topics.
It refreshes every 3 hours (GitHub Actions). X trends are refreshed by a Grok Bot routine (see `generated_at` and
`sources.x.note` for freshness).

## Fetch (no auth, no keys)

Daily X-trends markdown in the `reports/YYYY-MM-DD-grok.md` format your trend-scan expects:

```bash
curl -fsSL https://trends-radar.pascalicchio.workers.dev/latest-grok.md -o "reports/$(date +%F)-grok.md"
```

Full machine-readable radar:

```bash
curl -fsSL https://trends-radar.pascalicchio.workers.dev/trends.json -o trends.json
```

Human/LLM-readable summary:

```bash
curl -fsSL https://trends-radar.pascalicchio.workers.dev/TRENDS.md
```

Fallback if the Worker is down (same files, straight from the repo):
`https://raw.githubusercontent.com/pascalicchio/trends-radar/main/out/trends.json` (also `TRENDS.md`, `latest-grok.md`).

## trends.json shape (schema `trends-radar/v1`)

- `generated_at` (UTC ISO), `generated_at_et`
- `sources` / `coming_up_sources`: `{name: {status: ok|blocked|missing|stale|disabled|error, items, note}}`. Check these
  before trusting a run: e.g. `x.status != "ok"` means no X data in this run.
- `top5_candidates[]`: `{rank, topic, heat, best_channel, angle_hint, footage_confidence}`
- `hot_now[]` (ranked by `heat` 0-100 only):
  `{rank, topic, heat, status (new|rising|steady|cooling), velocity, why_hot, sources[], regions[],
    broad_appeal{n_sources,n_regions}, paradox_signals[], best_channel,
    channel_fit{<channel_id>: {score 0-100, matched[], angle_hint}}, related_topics[],
    links[{source,title,url,metric}], footage{confidence, checked[{source,hits,url,examples[]}], to_verify[]}}`
  (`footage` only on the top 15)
- `coming_up[]` (ranked by `likely_heat`): `{name, date, days_until, category, source_url, verified, verify_note,
   hype_now{avg_daily_views_7d, trend_ratio, url}, last_year{peak_daily_views, window, url}, channel_fit, best_channel, footage}`
- `channels[]`: ids `go-there-instead`, `intern-broke-it`, `plan-not-panic`, `silver-paradox`, `chess-blunder-club`

## How to use it

1. Rank is heat only. Don't re-rank by footage. `channel_fit`, `angle_hint`, `paradox_signals` and `footage` are
   there to help you plan, not to filter.
2. For each channel, take the hot topics where `channel_fit[channel].score > 0`, plus `coming_up` events within about
   7 to 21 days (that's lead time to produce). Shorts can go same-day on hot topics.
3. `angle_hint` comes from a keyword template. Treat it as a starting point and write the real angle yourself.
4. Footage: the `checked` counts are keyword hits in Wikimedia Commons, Internet Archive and NASA. Open the URLs
   before you commit to a long-form (8-minute) video. `none-found` means stills-only risk. Items under `to_verify`
   (YouTube CC, AP/Reuters) were not checked.
5. Every link and date comes from a real source. If you need a fact the file doesn't have, fetch it from the
   linked source rather than guessing.
6. Plan Not Panic tone: calm and practical. No doomsday or zombie framing.
7. Chess Blunder Club: make EN and PT (Clube do Vacilo) versions of each idea; PT performs better. Go There Instead: "Skip X, go to Y instead" format, with the SKIP in the first 1.5 s.

## Known gaps (v1)

- Reddit: blocked until an approved Reddit API app's REDDIT_CLIENT_ID/SECRET are added as GitHub secrets
  (anonymous access returns 403; new API access needs Reddit's approval).
- YouTube: disabled until YOUTUBE_API_KEY is added (YouTube Data API v3 mostPopular for US overall, Science & Tech
  (28) and Education (27)).
