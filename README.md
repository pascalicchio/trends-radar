# Trends Radar

Hot-now + coming-up topic radar that feeds Claude Code a daily file for picking video topics
(Go There Instead, The Intern Broke It, Plan Not Panic, Silver Paradox, Chess Blunder Club / Clube do Vacilo).

- Dashboard: https://trends-radar.pascalicchio.workers.dev/
- Exports: `/trends.json`, `/TRENDS.md`, `/latest-grok.md` on the same host (also `out/` in this repo).
- Refresh: GitHub Actions every 3 hours (`.github/workflows/refresh.yml`) + whenever `snapshots/` changes.
- X data: `snapshots/x.json`, written by a Grok Bot routine (X is only reachable through its MCP connector) using
  `scripts/make_snapshot.py`, then pushed here; the next Actions run merges it. Ignored when older than 36h.
- Channels: `config/channels.yaml` (add a block to add a channel). Curated events: `config/events.yaml` (every event
  needs a source URL + a verify pattern that is re-checked on every run).
- History: `history/YYYY-MM-DD.jsonl` (topic heat per run; baseline for rising/cooling).

Ranking is heat only. Channel fit, angle hints, paradox signals and footage checks are informational.

Run locally: `pip install -r requirements.txt && python pipeline/build.py`
