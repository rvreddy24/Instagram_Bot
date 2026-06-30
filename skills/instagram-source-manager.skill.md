name: instagram-source-manager
description: |
  Fully autonomous content source manager. Scores every source in the brain's
  strategy against real engagement data from performance.jsonl, prunes sources
  that consistently underperform, and discovers new RSS feeds, subreddits, and
  YouTube channels when the source pool is weak or shrinking.
  Called by the brain pre-cycle. Writes all actions to ./logs/source_log.jsonl.
categories: [social-media, automation, ai, brain]

# ─── CONSTANTS ──────────────────────────────────────────────────────────────
# SOURCE_LOG     : ./logs/source_log.jsonl
# PERF_FILE      : ./logs/performance.jsonl
# MIN_USES_TO_SCORE: 3   (ignore sources with < 3 uses when pruning)
# DISCOVERY_TRIGGER_THRESHOLD: 5  (discover if any type has < 5 sources)
# MAX_PER_TYPE   : 10
# ────────────────────────────────────────────────────────────────────────────

steps:
  1. **Load current source catalog**
       - Retrieve `ig:brain:strategy` from Hermes memory and parse JSON.
       - Extract `sources` object. If missing, initialize with empty lists and defaults:
             ```json
             {
               "rss": [],
               "subreddits": [],
               "youtube_channels": [],
               "prune_threshold": 2.5,
               "max_per_type": 10,
               "last_discovery_at": 0
             }
             ```
       - Extract `topics = strategy.content.topics` (used for discovery queries).

  2. **Score all sources against performance history**
       - Read ALL lines from `./logs/performance.jsonl` using `execute_code`:
             ```python
             import json, os
             rows = []
             if os.path.exists('./logs/performance.jsonl'):
                 with open('./logs/performance.jsonl', encoding='utf-8') as f:
                     rows = [json.loads(l) for l in f if l.strip()]
             # Group by source_url
             scores = {}
             for row in rows:
                 src = row.get('source_url', '')
                 if not src:
                     continue
                 if src not in scores:
                     scores[src] = {'total_engagement': 0, 'uses': 0}
                 scores[src]['total_engagement'] += row.get('engagement', 0)
                 scores[src]['uses'] += 1
             print(json.dumps(scores))
             ```
       - For each source in `sources.rss`, `sources.subreddits`, `sources.youtube_channels`:
           * Look up its URL/name in `scores`.
           * If found AND `uses >= MIN_USES_TO_SCORE`:
               - `source.score = total_engagement / uses`
           * If found AND `uses < MIN_USES_TO_SCORE`:
               - Keep score as-is (not enough data yet).
           * If not found at all in performance log (never used):
               - Increment a `no_use_cycles` counter on the source.
               - If `no_use_cycles >= 5`, treat score as 0 (source is ignored by research).
           * Update `source.uses = scores[url].uses` if found.

  3. **Prune underperforming sources**
       - For each source type (rss, subreddits, youtube_channels):
           * Collect sources where `uses >= MIN_USES_TO_SCORE` AND `score < prune_threshold`.
           * For each such source:
               - Remove it from the list.
               - Append to `./logs/source_log.jsonl`:
                     ```json
                     {"timestamp": <now>, "action": "prune", "type": "<rss|subreddit|youtube>",
                      "name": "<name>", "url": "<url>", "score": <score>, "uses": <uses>,
                      "reason": "score below prune_threshold"}
                     ```
       - Log total pruned count.

  4. **Check if discovery is needed**
       Discovery is triggered if ANY of the following:
       - Any source type has fewer than `DISCOVERY_TRIGGER_THRESHOLD` (5) sources remaining.
       - The average score across all scored sources is below `prune_threshold * 1.5`.
       - More than 30% of sources were just pruned.
       - Last discovery was more than 7 days ago AND total sources < 15.
       - Brain explicitly passed `force_discovery: true` in the input.
       
       Set `needs_discovery = true/false`.

  5. **Discover new sources (if needed)**
       For each source type where discovery is needed:

       **RSS Feeds:**
       - Use the `web` tool to search: `"<topic> RSS feed filetype:xml OR inurl:rss OR inurl:feed site:.com"`
         for each of the top 3 topics in `strategy.content.topics`.
       - Also try known feed aggregators: Feedly, NewsAPI, feedspot.com for the topic.
       - Collect candidate RSS URLs. For each candidate:
           * Fetch the RSS URL (via `execute_code` using `requests`) and verify it returns valid XML.
           * Parse the first 3 items — check they are recent (< 7 days) and contain relevant keywords.
           * If valid AND not already in the source list: add with `score: 5.0, uses: 0, added_at: <now>`.
           * Cap at `max_per_type - current_count` new additions.
       - Log each addition to `source_log.jsonl`:
             `{timestamp, action:"discover", type:"rss", name, url, reason:"auto-discovered via web search"}`

       **Subreddits:**
       - Use the `web` tool to search: `"site:reddit.com/r <topic> community"` for each topic.
       - Also query `https://www.reddit.com/subreddits/search.json?q=<topic>&limit=10` via `execute_code`.
       - For each candidate subreddit:
           * Fetch `https://www.reddit.com/r/<name>/about.json` — verify `subscribers > 10000`
             and `public_description` contains relevant keywords.
           * If valid AND not already in list: add with `score: 5.0, uses: 0, added_at: <now>`.
       - Log each addition.

       **YouTube Channels:**
       - Use the `web` tool to search: `"<topic> YouTube channel" site:youtube.com` for each topic.
       - For each candidate channel URL, extract the channel ID or handle.
       - Verify by fetching the channel's RSS feed:
             `https://www.youtube.com/feeds/videos.xml?channel_id=<id>`
         Check it returns items and recent uploads (< 30 days).
       - If valid AND not already in list: add with `score: 5.0, uses: 0, added_at: <now>`.
       - Log each addition.

  6. **Enforce max_per_type cap**
       - For each type, if `len(sources) > max_per_type`:
           * Sort by score ascending.
           * Remove the lowest-scored ones until at or below cap.
           * Log each removal as `{action:"cap-prune", reason:"exceeded max_per_type"}`.

  7. **Update strategy with new source catalog**
       - Serialize the updated `sources` object back into the strategy JSON.
       - Persist to `ig:brain:strategy` in Hermes memory.
       - Also update `sources.last_discovery_at` to `now` if discovery ran.

  8. **Return summary**
       ```json
       {
         "status": "ok",
         "pruned": <N>,
         "discovered": <M>,
         "total_sources": {"rss": <R>, "subreddits": <S>, "youtube_channels": <Y>},
         "discovery_triggered": <true/false>,
         "avg_source_score": <float>
       }
       ```

  9. **Failure handling**
       - On any error, log to `source_log.jsonl` and return `{status:"error", message:<desc>}`.
       - Do NOT crash the brain — source management failure is non-fatal; the orchestrator continues.
