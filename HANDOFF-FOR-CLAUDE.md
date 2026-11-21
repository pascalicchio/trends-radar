# Trends Radar: handoff for Claude Code

Trends Radar is a public, read-only feed of what's hot now and what's coming up in the next 8 weeks, scored against
the channels (Go There Instead, The Intern Broke It, Plan Not Panic, Silver Paradox, Chess Blunder Club / Clube do Vacilo, Military Unclassified). Use it to pick the next video topics.
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

## trends.json shape (schema `trends-radar/v1.1`)

- `generated_at` (UTC ISO), `generated_at_et`
- `sources` / `coming_up_sources`: `{name: {status: ok|empty|blocked|missing|stale|disabled|error, items, note}}`. Check these
  before trusting a run: e.g. `x.status != "ok"` means no X data in this run. Niche/desk feeds appear as `feed:<id>`
  (e.g. `feed:snopes`, `feed:fide`, `feed:gnews_overtourism`); a failing one shows `error` with the reason in `note`.
- `top5_candidates[]`: `{rank, topic, heat, best_channel, angle_hint, footage_confidence}`
- `hot_now[]` (top 40, ranked by `heat` 0-100 only):
  `{rank, topic, heat, status (new|rising|steady|cooling), velocity,
    first_seen (UTC ISO of the first run in the last 7 days that had this topic, null if new),
    days_trending (distinct ET days in the last 7 with this topic), heat_yesterday (max heat yesterday ET, or null),
    why_hot, sources[], regions[], broad_appeal{n_sources,n_regions},
    entity{qid, type, description, matched_via, url} | null,
    paradox_signals[], best_channel,
    channel_fit{<channel_id>: {score 0-100, strong[], weak[], angle_hint, note?}}, related_topics[],
    links[{source,title,url,metric}],
    footage{confidence, checked[{source,hits,url,examples[],license_hint}], to_verify[]}}`
  (`footage` only on the top 15)
  - `entity.type` (from Wikidata P31/P106, or a sports-headline heuristic): athlete, sports_team, sports_event, actor,
    musician, music_work, video_game, film, tv_series, chess_player, politician, company, person, other, sports_heuristic.
  - Fit rules: needs a channel `strong` keyword in the topic itself (label / Wikipedia / Wikidata description), or two
    different strong keywords in its headlines. Sports, celebrity, video-game, film and TV entities get 0 unless the
    channel allows that type (chess allows chess players and chess events) and the topic itself has a strong keyword.
    If the topic itself matches one channel, other channels that only matched in headlines get 0. `note` says why a
    fit was zeroed.
- `channel_picks{<channel_id>: [{rank, topic, heat, fit, strong[], angle_hint, url}]}`: the top 5 by heat with
  fit > 0 for each channel. It scans the top 200 topics plus up to 150 lower-heat ones with a strong channel keyword,
  so `rank` can be above 40 (not in `hot_now`). Niche channels (chess) often only show up here.
- `channel_feeds{<channel_id>: [{title, url, feed, lang, published, metric}]}`: niche feeds per channel.
  `chess-blunder-club`: FIDE, Chess.com news, Lichess blog + top broadcasts, Wikipedia chess-page views (en/pt/es),
  Google News "chess"/"xadrez"/"ajedrez". `go-there-instead`: Google News overtourism/tourist tax/closures, airline
  routes/cancellations, visas/ETIAS, travel news, Christmas markets, Wikivoyage most-read, Wikipedia travel-page views.
  `military-unclassified`: DoD (war.gov) releases, AARO/UAP news, Google News UAP/declassified/weapons-tech/special-forces,
  Wikipedia military/UAP page views (B-21, F-35, SR-71, AARO, Area 51, Project Blue Book, etc.).
- `desk_feeds{factcheck[], oddities[]}`: fact-check (Snopes, AFP Fact Check, PolitiFact, Reuters Fact Check, AFP
  Factual ES) and oddities (Live Science, Smithsonian, Atlas Obscura, Coast to Coast AM). Newest first, last 7 days.
  These items also feed the hot-now clustering.
- `happened_last_7_days[]`: `{title, url, feed, group, published, ...}`: Spaceflight News API, NASA news releases,
  DoD (war.gov) releases, AARO/UAP news (via Google News). Newest first, round-robin across feeds.
- `coming_up[]` (ranked by `likely_heat`, max 4 films): `{name, date, days_until, category, category_tags[], source_url, verified,
   verify_note, hype_now{avg_daily_views_7d, trend_ratio, url}, last_year{peak_daily_views, window, url}, channel_fit,
   best_channel, footage}`
- `channels[]`: ids `go-there-instead`, `intern-broke-it`, `plan-not-panic`, `silver-paradox`, `chess-blunder-club`, `military-unclassified`
- Spanish/Portuguese: Google News MX (es) and BR (pt) top stories plus es/pt Wikipedia most-read are in the clustering;
  their regions show as `MX`, `BR`, `es-wiki`, `pt-wiki`.

## How to use it

1. Rank is heat only. Don't re-rank by footage. `channel_fit`, `angle_hint`, `paradox_signals` and `footage` are
   there to help you plan, not to filter.
2. For each channel, start from `channel_picks[channel]` (and `channel_feeds[channel]` for chess/travel/military), take the hot topics where `channel_fit[channel].score > 0`, plus `coming_up` events within about
   7 to 21 days (that's lead time to produce). Shorts can go same-day on hot topics.
3. `angle_hint` comes from a keyword template. Treat it as a starting point and write the real angle yourself.
4. Footage: the `checked` counts are keyword hits in public archives. Open the URLs
   before you commit to a long-form (8-minute) video. `none-found` means stills-only risk. Items under `to_verify`
   (YouTube CC, AP/Reuters) were not checked. Footage sources checked: Wikimedia Commons, Internet Archive, NASA, Library of Congress;
   each has a `license_hint`. DVIDS and the National Archives catalog need API keys, so they're only listed under
   `to_verify` with search links.
5. Every link and date comes from a real source. If you need a fact the file doesn't have, fetch it from the
   linked source rather than guessing.
6. Plan Not Panic tone: calm and practical. No doomsday or zombie framing.
7. Chess Blunder Club: make EN and PT (Clube do Vacilo) versions of each idea; PT performs better. Go There Instead: "Skip X, go to Y instead" format, with the SKIP in the first 1.5 s.

## Known gaps (v1.1)

- Reddit: blocked until Reddit approves the API app and REDDIT_CLIENT_ID/SECRET/USERNAME are added as GitHub secrets.
- X: only as fresh as the Grok Bot X routine (twice a day); X chess/travel/military news queries are part of that routine.
- Dedup merges topics that share a Wikipedia article, X trend name, or normalized title. Two different headline
  phrasings of the same story (e.g. "Nationwide Ground Stop" and "FAA Ground Stop") can still show as two topics.
- Entity typing covers topics with a Wikipedia article or an exact Wikidata label match; others fall back to the
  sports-headline heuristic.
