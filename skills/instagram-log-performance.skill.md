name: instagram-log-performance
description: |
  Logs richer performance metrics for each run to a JSONL file and updates
  rolling aggregates in Hermes memory. The additional fields (topic,
  caption_style, strategy_version, hour_of_day_ist) are essential for the
  Gemini brain to accurately analyze what kinds of content, styles, and
  posting times drive the best engagement.
  Called at step 6 of the auto-orchestrator after engagement and follow.
categories: [social-media, automation]
steps:
  1. **Gather data from orchestrator context**
       - `draft_path`        : path to the draft markdown (contains front-matter)
       - `post_result`       : from stealth-post (status, screenshot, post_id)
       - `engage_result`     : from feed-engager (comments, likes, story_views)
       - `follow_result`     : from follow-manager (followed, unfollowed) — default `{followed:0,unfollowed:0}` if not passed
       - `strategy_version`  : from brain pre-cycle result
       - `timestamp`         : current epoch seconds

  2. **Parse draft front-matter**
       Use `execute_code` to read the draft markdown and extract:
       ```python
       import re, json
       with open(draft_path, encoding='utf-8') as f:
           content = f.read()
       fm = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
       data = {}
       if fm:
           for line in fm.group(1).splitlines():
               if ':' in line:
                   k, v = line.split(':', 1)
                   data[k.strip()] = v.strip().strip('"')
       print(json.dumps(data))
       ```
       Extract: `topic`, `style`, `media` (for infographic_id), `source_url`, `source_name`.

  3. **Determine infographic_id**
       - Basename of the media file (without extension) from `data['media']`.
       - If media is a YAML list (carousel), use the basename of the first element.

  4. **Compute hour_of_day (IST = UTC+5:30)**
       ```python
       import time
       utc_epoch = timestamp
       ist_epoch = utc_epoch + (5 * 3600) + (30 * 60)  # +5h 30m
       ist_hour = (ist_epoch // 3600) % 24
       utc_hour = (utc_epoch // 3600) % 24
       ```

  5. **Estimate views**
       - Try to scrape the posted Instagram URL (`https://www.instagram.com/p/<post_id>/`)
         for `og:description` impressions via a quick `execute_code` HTTP GET using the
         stored cookie session (same chrome-profile). Parse view count from description text.
       - If scraping fails or returns 0, use proxy: `views = likes + comments * 2`.

  6. **Build record JSON**
       ```json
       {
         "timestamp": <now>,
         "infographic_id": "<id>",
         "topic": "<topic>",
         "caption_style": "<style>",
         "strategy_version": <N>,
         "source_url": "<source_url>",
         "source_name": "<source_name>",
         "views": <estimated_views>,
         "likes": <engage_result.likes>,
         "comments": <engage_result.comments>,
         "story_views": <engage_result.story_views>,
         "engagement": <likes + comments>,
         "followed": <follow_result.followed>,
         "unfollowed": <follow_result.unfollowed>,
         "hour_of_day_utc": <utc_hour>,
         "hour_of_day_ist": <ist_hour>,
         "post_id": "<post_id or null>",
         "post_status": "<ok or error>"
       }
       ```

  7. **Append to performance log**
       ```python
       import json
       with open('./logs/performance.jsonl', 'a', encoding='utf-8') as f:
           f.write(json.dumps(record) + '\n')
       ```

  8. **Update rolling aggregates in Hermes memory**
       - `incr key=ig:total_runs by 1`
       - For the infographic_id:
             `incr key=ig:sum_views_<id> by views`
             `incr key=ig:sum_eng_<id> by engagement`
       - For IST hour-of-day bucket:
             `incr key=ig:hour_counts[<ist_hour>] by 1`
             `incr key=ig:hour_score[<ist_hour>] by engagement`
       - For topic:
             `incr key=ig:topic_eng_<slug(topic)> by engagement`
             `incr key=ig:topic_count_<slug(topic)> by 1`
         (slug = lowercase, spaces replaced with underscores, non-alphanum removed)

  9. **Return**
       `{status:"ok", logged:true, record_summary:{topic, engagement, hour_of_day_ist, strategy_version}}`