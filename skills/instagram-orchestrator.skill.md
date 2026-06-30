name: instagram-orchestrator
description: |
  Manual-approval orchestrator. Runs the full pipeline — brain, research, post,
  engage, follow, log — but pauses after the draft is ready and waits up to
  15 minutes for the user to approve via Hermes memory key `ig:approval_ready`.
  If not approved in time, skips posting but still logs the draft.
  Use instagram-orchestrator-auto for fully autonomous (no-approval) runs.
categories: [social-media, automation]
steps:
  1. **Brain — Pre-cycle evaluation**
        - Call skill `instagram-brain` with `{mode:"pre"}`.
        - On error: notify Discord "🧠❌ Brain failed: <message>" and STOP.
        - Extract `strategy_version`, `brain_notes`, `source_discovery_triggered`.
        - Notify Discord: "🧠 Brain v<strategy_version> ready. 💡 <brain_notes>"

  2. **Research & Draft**
        - Call skill `instagram-research-draft`.
        - Extract `draft_path`, `topic`.
        - On error: notify Discord "🔎❌ Research failed: <message>" and STOP.
        - Notify Discord: "🔎 Draft ready: \"<topic>\" → <draft_path>. Waiting for approval (15 min)..."

  3. **Manual approval gate**
        - Delete any stale `ig:approval_ready` key from Hermes memory.
        - Record `start_epoch = now()`.
        - Poll every **5 s** (up to 900 s / 15 min):
              * `val = memory_get(key="ig:approval_ready")`
              * If val == "1" → `approved = true`, break.
        - If loop exits due to timeout → `approved = false`.
        - To approve from any terminal: `memory action=add target=user key="ig:approval_ready" content="1" old_text=""`.

  4. **If approved — Post, Engage, Follow, Log**
        a. Call skill `instagram-stealth-post` with `draft_path`.
           - If status == "ok": notify Discord "✅ Posted (ID: <post_id>)"
           - Else: notify Discord "❌ Post failed: <error>" and STOP.
        b. Call skill `instagram-feed-engager`.
           - Notify Discord: "📈 Engagement: <comments> comments · <likes> likes · <story_views> story views"
        c. Call skill `instagram-follow-manager`.
           - Notify Discord: "👥 Follows: +<followed> new · -<unfollowed> unfollowed"
        d. Call skill `instagram-log-performance` with `draft_path, post_result, engage_result, follow_result, strategy_version`.
        e. Call skill `instagram-brain` with `{mode:"post", post_result, engage_result, follow_result, draft_path, strategy_version}`.
           - Notify Discord: "🧠 Post-cycle insight: <insight>"
           - If `deep_audit_triggered`: call `instagram-brain` with `{mode:"deep-audit"}`.
        f. Remove `ig:approval_ready` from memory.
        g. Write summary JSON to `./logs/orchestration_<timestamp>.json` and return it.

  5. **If NOT approved — skip posting**
        - Notify Discord: "⛔ Draft not approved within 15 min – skipping post."
        - Remove `ig:approval_ready` from memory.
        - Return `{stage:"skipped_approval", draft_path, reason:"timeout", timestamp}`.