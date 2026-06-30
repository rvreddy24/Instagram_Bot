name: instagram-log-performance
description: |
  Logs performance metrics for each run to a JSONL file and updates rolling aggregates in Hermes memory.
  Called at the end of the orchestrator after engagement.
categories: [social-media, automation]
steps:
  1. Gather data from the orchestrator context:
        - draft_path: from research-draft result (contains media file name)
        - post_result: from stealth-post (status, screenshot, post_id)
        - engage_result: from feed-engager (comments, likes, story_views)
        - timestamp: current epoch seconds
  2. Determine infographic_id: basename of the media file (without extension) from draft_path.
        If media is an array (carousel), use the first element.
  3. Estimate views:
        - Try to scrape the posted Instagram URL for og:description impressions via a quick
          execute_code call using the stored cookie session (same chrome-profile).
        - If scraping fails, use proxy: views = likes + comments * 2.
  4. Build record JSON:
        {
          "timestamp": <now>,
          "infographic_id": "<id>",
          "views": <estimated_views>,
          "engagement": <likes+comments+shares (shares approximated as 0)>,
          "hour_of_day": <hour from timestamp in UTC>,
          "post_id": "<post_id or null>"
        }
  5. Append record to ./logs/performance.jsonl (create if missing) using execute_code:
        with open('./logs/performance.jsonl','a',encoding='utf-8') as f:
            f.write(json.dumps(record)+'\n')
  6. Update rolling aggregates in Hermes memory (optional but speeds up weekly brain):
        - Increment counter: incr key=ig:total_runs by 1
        - For the specific infographic_id:
              incr key=ig:sum_views_<id> by views
              incr key=ig:sum_eng_<id> by engagement
        - For hour-of-day bucket:
              incr key=ig:hour_counts[<hour>] by 1
              incr key=ig:hour_score[<hour>] by engagement
  7. Return a brief summary for debugging: {status:"ok",logged:true}