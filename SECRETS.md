# Secrets for Trends Radar (GitHub Actions, repo pascalicchio/trends-radar)

Each value is piped through stdin so it never appears in argv or in chat. Run on the box after the value is in env:

    printf %s "$YOUTUBE_API_KEY"      | gh secret set YOUTUBE_API_KEY      -R pascalicchio/trends-radar
    printf %s "$REDDIT_CLIENT_ID"     | gh secret set REDDIT_CLIENT_ID     -R pascalicchio/trends-radar
    printf %s "$REDDIT_CLIENT_SECRET" | gh secret set REDDIT_CLIENT_SECRET -R pascalicchio/trends-radar
    printf %s "$REDDIT_USERNAME"      | gh secret set REDDIT_USERNAME      -R pascalicchio/trends-radar

Then trigger a run with: gh workflow run refresh-trends -R pascalicchio/trends-radar
Check that the source status turns ok: curl -s https://trends-radar.pascalicchio.workers.dev/health

Until a secret is set, its source shows blocked/disabled and the rest of the pipeline keeps running.
