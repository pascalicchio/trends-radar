# Grok Bot routine: X snapshot for Trends Radar (needs to be created by the parent bot)

Why: X is only reachable through the `x` MCP connector, which a cron/GitHub Action can't call.
Schedule: daily at 6:30 AM ET and 6:30 PM ET (about 14 X reads/day of the 1000/day limit).

Steps (all on the box, nothing is posted anywhere):
1. `x.get_trends_by_woeid` with `trend.fields=[trend_name,tweet_count]`, `max_trends=50`, write_to_file=true, for
   woeid 23424977 (US), 1 (Worldwide), 23424900 (MX), 23424975 (GB).
2. `x.search_news` with `max_results=25`, `max_age_hours=24`,
   `news.fields=[name,hook,category,contexts,keywords,updated_at,id]`, write_to_file=true, for queries:
   "United States", "science space technology AI", "weather storm outage".
3. Run:
   python3 /workspace/trends-radar/scripts/make_snapshot.py x --trends US=<f1> --trends Worldwide=<f2> --trends MX=<f3> --trends GB=<f4> --news <f5> --news <f6> --news <f7>
4. Run: /workspace/trends-radar/scripts/push_snapshot.sh   (git push via the box's existing gh login; this
   triggers the GitHub Action, which rebuilds everything in about 1 minute)
5. Optional: `cd /workspace/trends-radar && git pull -q` ~3 minutes later to refresh /workspace/trends-radar/out/ on the box.
6. Stay silent on success. If a step fails twice, report it.
