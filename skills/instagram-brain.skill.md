name: instagram-brain
description: |
  Fully autonomous, self-evaluating, self-auditing, self-aware Gemini brain.
  Uses gemini-1.5-pro to analyze performance, manage its own content sources
  (discovering, scoring, and pruning them automatically), audit the accuracy
  of its own past predictions, and maintain a living self-model that tracks
  every decision it makes and why.

  Modes:
    "pre"        – pre-cycle: score sources, generate Strategy JSON, update self-model
    "post"       – post-cycle: record outcome, score source used, update self-model
    "deep-audit" – weekly: full prediction accuracy audit, portfolio rebalance, Discord report
    "status"     – read-only: return current self-model and strategy summary

  The strategy JSON (ig:brain:strategy) is the single source of truth for every
  other skill's decisions: what to post, when, what topics, which sources to use,
  who to follow, and how to engage.
categories: [social-media, automation, ai, brain]

# ─── CONSTANTS ───────────────────────────────────────────────────────────────
# GEMINI_MODEL      : gemini-1.5-pro
# GEMINI_ENDPOINT   : https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent
# STRATEGY_KEY      : ig:brain:strategy
# NOTES_KEY         : ig:brain:notes
# PERF_FILE         : ./logs/performance.jsonl
# BRAIN_NOTES_FILE  : ./logs/brain_notes.jsonl
# AUDIT_LOG_FILE    : ./logs/audit_log.jsonl
# MAX_PERF_ROWS     : 30
# DEEP_AUDIT_EVERY  : 7  (cycles)
# ─────────────────────────────────────────────────────────────────────────────

steps:
  # ═══════════════════════════════════════════════════════════════════════════
  # SHARED: Always run first regardless of mode
  # ═══════════════════════════════════════════════════════════════════════════

  0. **Authenticate & load state**
       - Determine `mode` from input. Default: `"pre"`.
       - Retrieve `gemini_api_key` from Hermes memory.
         If missing → return `{status:"error", message:"Set gemini_api_key in Hermes memory first"}`.
       - Load full strategy from `ig:brain:strategy`. Parse JSON.
         If missing → initialize a blank strategy (first-run defaults below).
       - Load `ig:brain:notes` (last insight string).
       - Load `ig:brain:self_model` (JSON object). Initialize if missing:
             ```json
             {
               "total_cycles": 0, "successful_posts": 0, "failed_posts": 0,
               "avg_engagement_last_10": 0, "engagement_trend": "unknown",
               "hour_prediction_accuracy": 0, "topic_prediction_accuracy": 0,
               "follow_back_rate": 0, "growth_follower_per_day": 0,
               "worst_recent_prediction": "", "audit_score": 0,
               "last_audit_at": 0, "last_prediction": {}
             }
             ```
       - Dispatch to the correct mode handler (steps 1–9).

  # ═══════════════════════════════════════════════════════════════════════════
  # MODE: "pre" — Pre-cycle strategy generation
  # ═══════════════════════════════════════════════════════════════════════════

  1. **[PRE] Manage sources**
       - Call skill `instagram-source-manager`.
       - If it returns `discovery_triggered: true`, note it for later Discord notification.
       - Log source summary: `{pruned, discovered, total_sources, avg_source_score}`.

  2. **[PRE] Load performance history**
       - Read last `MAX_PERF_ROWS` rows from `performance.jsonl` via `execute_code`.
       - Build:
           * Hour-of-day heatmap (IST): `[{hour, posts, avg_engagement}]` for hours 0–23.
           * Top 5 topics by avg engagement: `[{topic, avg_engagement, count}]`.
           * Bottom 5 topics by avg engagement.
           * Engagement trend: compare avg of last 5 runs vs avg of runs 6–10.
           * Follow-back rate: `followed_back / total_follows_tracked`.
       - Update self-model fields from computed data.

  3. **[PRE] Build and send Gemini pre-cycle prompt**
       Prompt sections:
       ```
       You are the strategic brain of an autonomous Instagram growth bot.
       Your job: analyze ALL data below and return an updated full Strategy JSON.
       Be specific, data-driven, and evolving — do not just repeat the last strategy.

       ## Self-Model (your own performance history)
       <self_model JSON>

       ## Performance history (last 30 runs)
       <rows JSON>

       ## Source catalog (current)
       <strategy.sources JSON including per-source scores>

       ## Hour-of-day engagement heatmap (IST, 0–23)
       <heatmap JSON>

       ## Top performing topics
       <top_topics JSON>

       ## Worst performing topics
       <bottom_topics JSON>

       ## Engagement trend
       <"up X%" or "down X%" or "stable">

       ## Current strategy (version N)
       <full strategy JSON>

       ## Last brain insight
       <ig:brain:notes>

       ## Instructions
       Return ONLY a valid JSON with this EXACT schema (no markdown):
       {
         "version": <current_version + 1>,
         "updated_at": <unix_epoch_now>,
         "posting": {
           "best_hours_utc": [<up to 3 hours>],
           "frequency_hours": <4-12>,
           "confidence": <0.0-1.0>
         },
         "content": {
           "topics": [<3-5 specific topic strings>],
           "style": "<caption structure>",
           "caption_tone": "<tone>",
           "avoid_topics": [<underperforming or risky>],
           "hashtags": [<8-12 hashtags>],
           "carousel_preferred": <true/false>
         },
         "engagement": {
           "min_post_age_minutes": <int>,
           "max_post_age_hours": <int>,
           "niche_keywords": [<keywords>],
           "comment_style": "<instruction>",
           "like_threshold_score": <int>,
           "story_view_probability": <0.0-1.0>
         },
         "follow": {
           "target_niches": [<niche descriptions>],
           "min_followers": <int>,
           "max_following_ratio": <float>,
           "unfollow_after_days": <int>,
           "follows_per_run": <2-10>
         },
         "sources": {
           "rss": <keep existing array with updated scores; do NOT remove — source-manager handles pruning>,
           "subreddits": <keep existing>,
           "youtube_channels": <keep existing>,
           "prune_threshold": <float, adjust based on overall quality>,
           "max_per_type": 10,
           "last_discovery_at": <keep existing>
         },
         "brain_notes": "<one sentence: most important insight from this analysis>",
         "trigger_discovery": <true if sources need refreshing, else false>
       }
       ```
       - Call Gemini API via `execute_code` (POST, 30s timeout, raise on error).
       - Parse JSON from response.
       - If Gemini fails: keep existing strategy, return `{status:"fallback"}`.

  4. **[PRE] Record prediction for later audit**
       - Store `ig:brain:last_prediction` in Hermes memory:
             ```json
             {
               "strategy_version": <new_version>,
               "predicted_best_hours": <strategy.posting.best_hours_utc>,
               "predicted_topics": <strategy.content.topics>,
               "predicted_at": <now_epoch>
             }
             ```
       - This is what the post-cycle and deep-audit modes compare against actual results.

  5. **[PRE] Persist new strategy and return**
       - Save full strategy to `ig:brain:strategy`.
       - Save `brain_notes` to `ig:brain:notes`.
       - Append to `brain_notes.jsonl`:
             `{timestamp, mode:"pre", version, brain_notes, source_summary, trigger_discovery}`
       - Return:
             ```json
             {
               "status": "ok",
               "mode": "pre",
               "strategy_version": <N>,
               "brain_notes": "<note>",
               "source_discovery_triggered": <bool>,
               "source_summary": {pruned, discovered, total_sources, avg_source_score},
               "self_model_snapshot": {total_cycles, engagement_trend, audit_score}
             }
             ```

  # ═══════════════════════════════════════════════════════════════════════════
  # MODE: "post" — Post-cycle retrospective
  # ═══════════════════════════════════════════════════════════════════════════

  6. **[POST] Receive cycle results**
       Inputs: `post_result`, `engage_result`, `follow_result`, `draft_path`, `strategy_version`.
       - Update self-model:
           * `total_cycles += 1`
           * If `post_result.status == "ok"`: `successful_posts += 1`; else: `failed_posts += 1`.
           * Update `avg_engagement_last_10` using last 10 rows of `performance.jsonl`.
           * Recompute `engagement_trend` (last 5 vs prev 5).
           * Update `follow_back_rate` from `ig:following_log`.

  7. **[POST] Audit this cycle's prediction**
       - Load `ig:brain:last_prediction`.
       - Was the post made at a predicted best hour? → `hour_correct = true/false`.
       - Was the post topic in the predicted topics list? → `topic_correct = true/false`.
       - Update running accuracy in self-model using an exponential moving average:
             `hour_prediction_accuracy = 0.9 * old + 0.1 * (1 if hour_correct else 0)`
             `topic_prediction_accuracy = 0.9 * old + 0.1 * (1 if topic_correct else 0)`

  8. **[POST] Score the source used this cycle**
       - Read `source_url` from the draft front-matter (parse with regex).
       - Find the matching source in `strategy.sources.rss / subreddits / youtube_channels`.
       - Update its `score` with the actual engagement this cycle:
             `new_score = (old_score * old_uses + engage_result.engagement) / (old_uses + 1)`
             `source.uses += 1`
             `source.last_used_at = now`
       - Persist updated `strategy.sources` to `ig:brain:strategy`.

  9. **[POST] Call Gemini for retrospective insight**
       Prompt:
       ```
       You are the strategic brain of an autonomous Instagram bot reflecting on a completed cycle.

       ## What I predicted (strategy version <N>)
       Best hours: <predicted_best_hours>
       Topics: <predicted_topics>

       ## What actually happened
       Post time hour (IST): <actual_hour>
       Topic used: <draft_topic>
       Engagement: <engage_result.comments> comments, <engage_result.likes> likes
       Post status: <post_result.status>
       Source used: <source_name> (score: <source_score>)
       Follow result: +<followed> follows, <follow_back_rate> follow-back rate

       ## My self-model
       <self_model JSON>

       Instructions:
       Return ONLY JSON:
       {
         "insight": "<one sentence, max 200 chars, specific and actionable>",
         "adjust_confidence": <-0.1 to +0.1>,
         "worst_prediction": "<what I got most wrong this cycle, or empty string>"
       }
       ```
       - Apply `adjust_confidence` to `strategy.posting.confidence` (clamp 0.0–1.0).
       - Update `self_model.worst_recent_prediction` if `worst_prediction` is non-empty.
       - Persist updated strategy and self-model.

  10. **[POST] Check if deep-audit should trigger**
        - If `self_model.total_cycles % DEEP_AUDIT_EVERY == 0` AND `total_cycles > 0`:
              * Self-invoke `instagram-brain` with `mode="deep-audit"` (or flag for orchestrator).
        - Append to `brain_notes.jsonl`:
              `{timestamp, mode:"post", version, insight, hour_correct, topic_correct, source_url, engagement}`
        - Persist self-model to `ig:brain:self_model`.
        - Return:
              ```json
              {
                "status": "ok",
                "mode": "post",
                "insight": "<insight>",
                "new_confidence": <float>,
                "self_model": {total_cycles, engagement_trend, hour_accuracy, topic_accuracy},
                "deep_audit_triggered": <bool>
              }
              ```

  # ═══════════════════════════════════════════════════════════════════════════
  # MODE: "deep-audit" — Weekly full analysis
  # ═══════════════════════════════════════════════════════════════════════════

  11. **[DEEP-AUDIT] Load full history**
        - Read ALL rows from `performance.jsonl`.
        - Read ALL entries from `brain_notes.jsonl`.
        - Read current `self_model`.
        - Compute comprehensive stats:
            * Overall hour accuracy: for each row, did the post hour match best_hours at that time?
            * Topic accuracy: which topics were predicted to do well but didn't, and vice versa?
            * Source accuracy: top 3 best sources vs bottom 3 sources by avg engagement.
            * Follow quality: overall `follow_back_rate` from `ig:following_log`.
            * Engagement growth: week-over-week avg engagement change.
            * Failed cycle pattern: what do failed posts have in common?

  12. **[DEEP-AUDIT] Call Gemini for full audit report**
        Prompt:
        ```
        You are the strategic brain conducting your weekly self-audit.
        Analyze ALL data below and produce a comprehensive audit report.

        ## Full performance history
        <all rows JSON>

        ## Brain decision log (last 7 cycles)
        <brain_notes.jsonl last 7 entries>

        ## Computed accuracy metrics
        Hour prediction accuracy: <float>
        Topic prediction accuracy: <float>
        Source performance: <top/bottom sources>
        Follow-back rate: <float>
        Engagement trend (7 days): <up/down X%>

        ## Current self-model
        <self_model JSON>

        ## Current strategy
        <strategy JSON>

        Instructions:
        Return ONLY JSON:
        {
          "audit_score": <0.0-1.0, overall self-assessment of brain quality>,
          "key_findings": [<up to 5 specific findings as strings>],
          "strategy_corrections": {
            <field_path>: <new_value>
            // e.g. "posting.best_hours_utc": [8, 13, 19]
            // Only include fields that should change based on evidence
          },
          "sources_to_drop": [<source URLs/names that evidence shows are underperforming>],
          "sources_to_find": [<topic strings to search for new sources>],
          "reset_confidence": <true if audit_score < 0.4>,
          "weekly_summary": "<3-4 sentences suitable for Discord. Mention biggest win, biggest miss, and plan for next week.>"
        }
        ```

  13. **[DEEP-AUDIT] Apply corrections and report**
        - Apply all `strategy_corrections` to the strategy JSON.
        - If `reset_confidence`: set `strategy.posting.confidence = 0.3`.
        - For each URL in `sources_to_drop`: remove from strategy sources + log to `source_log.jsonl`.
        - If `sources_to_find` is non-empty: call `instagram-source-manager` with `force_discovery: true`
          and the topic list from `sources_to_find`.
        - Update `self_model.audit_score = audit_score`.
        - Update `self_model.last_audit_at = now`.
        - Persist everything.
        - Append full audit record to `audit_log.jsonl`.
        - Notify Discord via `discord-notify`:
              ```
              🧠📊 Weekly Brain Report (cycle <total_cycles>)

              Audit score: <audit_score>/1.0
              <weekly_summary>

              Top finding: <key_findings[0]>
              ```
        - Return `{status:"ok", mode:"deep-audit", audit_score, key_findings, weekly_summary}`.

  # ═══════════════════════════════════════════════════════════════════════════
  # MODE: "status" — Read-only snapshot
  # ═══════════════════════════════════════════════════════════════════════════

  14. **[STATUS] Return current state**
        - Load and return:
              ```json
              {
                "status": "ok",
                "mode": "status",
                "strategy_version": <N>,
                "self_model": <self_model>,
                "source_summary": {
                  "rss_count": <N>, "rss_avg_score": <float>,
                  "subreddit_count": <N>, "subreddit_avg_score": <float>,
                  "youtube_count": <N>, "youtube_avg_score": <float>
                },
                "current_strategy_highlights": {
                  "best_hours_utc": <list>,
                  "top_topics": <list>,
                  "confidence": <float>
                }
              }
              ```

  # ═══════════════════════════════════════════════════════════════════════════
  # FIRST-RUN DEFAULTS (used when strategy is completely empty)
  # ═══════════════════════════════════════════════════════════════════════════

  15. **[FIRST-RUN] Seed initial strategy and sources**
        When `strategy == {}` (very first run ever):
        - Set strategy with safe defaults:
              posting: best_hours_utc=[4,9,14], frequency_hours=8, confidence=0.1
              content: topics=["AI", "Machine Learning", "Productivity"], style="hook + 3 facts + CTA"
              engagement: niche_keywords=["AI","tech","LLM"], like_threshold_score=2
              follow: min_followers=500, follows_per_run=3, unfollow_after_days=14
        - Seed initial sources:
              rss: [
                {url:"https://rss.arxiv.org/rss/cs.AI", name:"arXiv AI", score:5.0, uses:0},
                {url:"https://feeds.feedburner.com/venturebeat/SZYF", name:"VentureBeat AI", score:5.0, uses:0},
                {url:"https://www.technologyreview.com/feed/", name:"MIT Tech Review", score:5.0, uses:0}
              ]
              subreddits: [
                {name:"MachineLearning", score:5.0, uses:0},
                {name:"artificial", score:5.0, uses:0},
                {name:"LocalLLaMA", score:5.0, uses:0}
              ]
              youtube_channels: [
                {id:"UCWX3yGbODI3HLd1VYSK8M0A", name:"Two Minute Papers", score:5.0, uses:0},
                {id:"UCbmNph6atAoGfqLoCL_duAg", name:"Yannic Kilcher", score:5.0, uses:0}
              ]
        - Persist strategy and self-model.
        - Notify Discord: "🧠🌱 Brain initialized for first run. Using default strategy. It will learn from your results."
        - Proceed with normal `pre` mode from step 3.
