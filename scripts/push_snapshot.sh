#!/usr/bin/env bash
# Commit + push snapshots/x.json to GitHub; the push triggers the refresh-trends workflow.
set -euo pipefail
cd "$(dirname "$0")/.."
git pull -q --rebase origin main
git add snapshots/
if git diff --cached --quiet; then echo "no snapshot change"; exit 0; fi
git -c user.name="Fillipe Pascalicchio" -c user.email="pascalicchio@users.noreply.github.com" commit -qm "snapshot: X $(date -u +%Y-%m-%dT%H:%MZ)"
git push -q origin main && echo "pushed; workflow will rebuild in ~1 min"
