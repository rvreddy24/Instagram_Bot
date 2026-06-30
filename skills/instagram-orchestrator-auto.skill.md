name: instagram-orchestrator-auto
description: |
  Fully autonomous orchestrator: research → draft → post → engage,
  with Discord notifications at each major step and error handling.
  No manual approval step; relies on persistent Chrome profile.
categories: [social-media, automation]
steps:
  1. **Research & Draft**
        - Call skill `instagram-research-draft`.
        - Extract `draft_path` from the JSON result.
        - Notify Discord via `discord-notify`:
              "🔎 Research complete. Draft ready: <draft_path>"
  2. **Post to Instagram**
        - Call skill `instagram-stealth-post` with input `draft_path`.
        - Parse result JSON.
        - If status == "ok":
              * Extract `screenshot` and `post_id`.
              * Notify Discord:
                    "✅ Posted to Instagram (ID: <post_id>). Screenshot: <screenshot>"
          Else:
              * Extract error message.
              * Notify Discord:
                    "❌ Instagram post failed: <error>"
              * Stop further steps (return error).
  3. **Engage with Feed**
        - Call skill `instagram-feed-engager`.
        - Parse result JSON for `comments`, `likes`, `story_views`.
        - Notify Discord:
              "📈 Engagement: <comments> comments, <likes> likes, <story_views> story views."
  4. **Final Notice**
        - Notify Discord:
              "🕒 Cycle complete. Next run in 4 hours."
  5. **Return**
        - Return a JSON summarizing the outcome for the cron‑job log.