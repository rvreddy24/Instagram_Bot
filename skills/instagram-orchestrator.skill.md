name: instagram-orchestrator
description: |
  Orchestrates the full Instagram automation pipeline:
  1. Run the research-and-draft skill to generate a draft and send a Telegram preview.
  2. Wait for manual approval (via a temporary file signal) or auto‑approve after 15 minutes.
  3. If approved, run the stealth‑post skill to publish the content.
  4. Finally, run the feed‑engager skill to like/comment on the home feed.
  Returns a JSON summary of the outcome.
categories: [social-media, automation]
steps:
  1. Invoke the research‑and‑draft skill:
        draft_result = skill_invoke(name="instagram-research-draft")
     Expect the result to contain at least:
        - draft_path: path to the generated markdown draft
        - telegram_msg_id: optional ID of the Telegram preview message
     Store the draft_path in a variable for later steps.
  2. Set up an approval waiting mechanism:
        - Create a temporary file /tmp/ig_approved (or use Hermes memory key ig:approval_ready) that will be
          created when you approve the preview (e.g., via a Telegram bot button that writes this file).
        - Record the start time (epoch seconds).
        - Loop while elapsed < 900 seconds (15 min):
              if the approval file exists → break and set approved = true
              else sleep 5 seconds.
        - If the loop exits due to timeout → approved = false.
  3. If approved:
        a. Run the stealth‑post skill:
              post_result = skill_invoke(name="instagram-stealth-post", input=draft_path)
           Capture the output (status, screenshot, post_id).
        b. Run the feed‑engager skill:
              engage_result = skill_invoke(name="instagram-feed-engager")
        c. Build a final summary:
              {
                "stage": "completed",
                "draft_path": draft_path,
                "telegram_msg_id": telegram_msg_id,
                "post_result": post_result,
                "engage_result": engage_result,
                "timestamp": <epoch now>
              }
     Else (not approved):
        a. Return a summary indicating the draft was not approved:
              {
                "stage": "skipped_approval",
                "draft_path": draft_path,
                "telegram_msg_id": telegram_msg_id,
                "reason": "Approval timeout (15 min) or manual reject",
                "timestamp": <epoch now>
              }
  4. In either case, write the summary JSON to ./logs/orchestration_<timestamp>.json
     and return it as the skill result.