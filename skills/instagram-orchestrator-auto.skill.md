name: instagram-orchestrator-auto
description: |
  Fully autonomous orchestrator driven by the self-evaluating Gemini brain.
  Pipeline: brain(pre) → source-manager (inside brain) → research+draft
            → post → engage → follow → log → brain(post) → [deep-audit if due] → notify.
  All skills are driven by ig:brain:strategy. The brain manages its own sources,
  audits its own predictions, and sends a weekly report automatically.
categories: [social-media, automation]
steps:
  1. **Brain — Pre-cycle evaluation**
        - Call skill `instagram-brain` with input `{mode:"pre"}`.
        - Handle response by status:
            * "error"    → notify Discord "🧠❌ Brain failed: <message>" and STOP.
            * "fallback" → notify Discord "🧠⚠️ Gemini call failed — using previous strategy. Continuing."
            * "ok"       → proceed.
        - Extract from result:
            * `strategy_version`
            * `brain_notes`
            * `source_discovery_triggered`
            * `source_summary` = `{pruned, discovered, total_sources, avg_source_score}`
            * `self_model_snapshot` = `{total_cycles, engagement_trend, audit_score}`
        - Build brain Discord notification:
              ```
              🧠 Brain v<strategy_version> ready.
              📊 Self-model: <total_cycles> cycles · trend <engagement_trend> · audit score <audit_score>
              💡 Insight: <brain_notes>
              ```
        - If `source_discovery_triggered`:
              append to message: `🔍 Source discovery ran: +<discovered> added, <pruned> pruned. <total_sources.rss> RSS · <total_sources.subreddits> subreddits · <total_sources.youtube_channels> YouTube`
        - Send combined message via `discord-notify`.

  2. **Research & Draft**
        - Call skill `instagram-research-draft`.
          (Reads brain's sources catalog and content strategy automatically.)
        - Extract `draft_path`, `topic`, `strategy_version`.
        - On error: notify Discord "🔎❌ Research failed: <message>" and STOP.
        - Notify Discord: "🔎 Research complete: \"<topic>\" → <draft_path>"

  3. **Post to Instagram**
        - Call skill `instagram-stealth-post` with input `draft_path`.
        - If status == "ok":
              * Extract `screenshot`, `post_id`.
              * Notify Discord: "✅ Posted (ID: <post_id>)"
          Else:
              * Notify Discord: "❌ Post failed: <error>"
              * STOP (return error JSON).

  4. **Engage with Feed**
        - Call skill `instagram-feed-engager`.
          (Reads engagement criteria from brain strategy automatically.)
        - Notify Discord:
              "📈 Engagement: <comments> comments · <likes> likes · <story_views> story views"

  5. **Follow / Unfollow**
        - Call skill `instagram-follow-manager`.
          (Reads follow criteria from brain strategy automatically.)
        - Notify Discord:
              "👥 Follows: +<followed> new · -<unfollowed> unfollowed · <follow_back_rate> follow-back rate"

  6. **Log Performance**
        - Call skill `instagram-log-performance` passing:
              `draft_path`, `post_result`, `engage_result`, `follow_result`, `strategy_version`.
        - (Saves source_url, source_name, engagement, IST hour to performance.jsonl.)

  7. **Brain — Post-cycle retrospective**
        - Call skill `instagram-brain` with input:
              `{mode:"post", post_result, engage_result, follow_result, draft_path, strategy_version}`
        - Extract `insight`, `new_confidence`, `deep_audit_triggered`, `self_model`.
        - Notify Discord:
              ```
              🧠 Post-cycle insight: <insight>
              📊 Confidence now: <new_confidence> · Hours accuracy: <hour_accuracy> · Topics accuracy: <topic_accuracy>
              ```
        - If `deep_audit_triggered`:
            * Call skill `instagram-brain` with `{mode:"deep-audit"}`.
            * (Brain will send the weekly report to Discord itself from within deep-audit mode.)

  8. **Final Notice**
        - Notify Discord:
              "🕒 Cycle <total_cycles> complete. Next run in <frequency_hours> h."

  9. **Return**
        - Return full summary JSON:
              `{status, strategy_version, brain_notes, post_id, engage_result, follow_result, insight, new_confidence, deep_audit_triggered}`