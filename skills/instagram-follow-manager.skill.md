name: instagram-follow-manager
description: |
  Brain-driven follow/unfollow manager. Reads ig:brain:strategy.follow for all
  criteria, finds matching accounts from the current feed and comment sections,
  follows them with human-like stealth timing, and unfollows accounts that
  exceeded the unfollow_after_days window without following back.
  Logs all actions to ./logs/follow_log.jsonl.
categories: [social-media, automation, browser, stealth]

# Reads from ig:brain:strategy.follow:
#   target_niches      : list of niche description strings
#   min_followers      : int
#   max_following_ratio: float (following/followers)
#   unfollow_after_days: int
#   follows_per_run    : int (2–10)

steps:
  1. **Load strategy**
       - Retrieve `ig:brain:strategy` from Hermes memory and parse the JSON.
       - Extract `follow_cfg = strategy.follow`.
       - If strategy is missing, return `{status:"error", message:"Brain strategy not found – run instagram-brain first"}`.

  2. **Load following log**
       - Retrieve `ig:following_log` from Hermes memory (JSON array of
         `{account, followed_at_epoch, followed_back: bool}`). Default to `[]`.
       - Separate into:
           * `to_unfollow`: entries where `followed_back == false` AND
             `(now_epoch - followed_at_epoch) / 86400 >= follow_cfg.unfollow_after_days`.
           * `already_following`: set of account names for quick lookup.

  3. **Unfollow stale accounts**
       - For each account in `to_unfollow` (process all, no cap):
           a. Navigate to `https://www.instagram.com/<account>/`.
           b. Wait `random(1000, 2500)` ms.
           c. Locate the "Following" button (aria-label contains "Following") and click it.
           d. Confirm the unfollow dialog if it appears (click "Unfollow").
           e. Wait `random(2000, 5000)` ms.
           f. Remove the account from `ig:following_log`.
           g. Append to `./logs/follow_log.jsonl`:
                 `{timestamp, action:"unfollow", account}`.
       - After all unfollows, navigate back to `https://www.instagram.com/`.

  4. **Find follow candidates from feed + comments**
       - Navigate to `https://www.instagram.com/` and take a snapshot.
       - Collect up to 10 article authors visible in the feed (extract author name / profile link).
       - For the top 3 posts by score (from feed-engager's last candidate list if available in memory
         as `ig:last_candidates`, else just the first 3 articles), open the comments section and
         collect up to 5 commenter account names.
       - Deduplicate against `already_following` and against `ig:follow_declined` (accounts
         previously inspected and rejected – to avoid re-checking every run).
       - You now have a candidate set.

  5. **Qualify candidates**
       For each candidate account (check up to 15 to find `follows_per_run` qualifying ones):
           a. Navigate to `https://www.instagram.com/<account>/`.
           b. Wait `random(800, 2000)` ms.
           c. Scrape profile stats: extract follower count and following count from the page
              (look for elements containing "followers" and "following" text near the stats row).
           d. Compute `following_ratio = following_count / max(followers_count, 1)`.
           e. Check bio text for any of `follow_cfg.target_niches` keywords (case-insensitive).
           f. **Qualify if ALL of**:
                * `followers_count >= follow_cfg.min_followers`
                * `following_ratio <= follow_cfg.max_following_ratio`
                * at least one niche keyword appears in bio or recent post captions.
           g. If not qualified, add to `ig:follow_declined` (persist in memory) and skip.
           h. Stop once `follows_per_run` qualified accounts are found.

  6. **Follow qualified accounts**
       For each qualified account:
           a. Locate the "Follow" button (aria-label "Follow") on their profile page.
           b. Wait `random(500, 1500)` ms before clicking.
           c. Click the Follow button.
           d. Wait `random(3000, 8000)` ms (important: slow down between follows to avoid limits).
           e. Add to `ig:following_log`:
                 `{account, followed_at_epoch: now, followed_back: false}`.
           f. Persist `ig:following_log` back to memory.
           g. Append to `./logs/follow_log.jsonl`:
                 `{timestamp, action:"follow", account, followers: N, following_ratio: R}`.

  7. **Check if any existing follows followed back**
       - For the last 10 entries in `ig:following_log` where `followed_back == false`
         and age < `unfollow_after_days` days:
           a. Navigate to `https://www.instagram.com/<account>/`.
           b. Check if the "Follow" button shows "Following" (they follow us back means
              the mutual-follow indicator appears, or check our followers list).
              Simpler heuristic: if the button label is "Message" (both follow each other),
              set `followed_back = true`.
           c. Update `ig:following_log` accordingly.
       - Persist the updated log.

  8. **Return results**
       ```json
       {
         "status": "ok",
         "followed": <N>,
         "unfollowed": <M>,
         "candidates_checked": <K>,
         "follow_back_rate": "<X of last 10 followed back>"
       }
       ```

  9. **Failure handling**
       - On any uncaught exception:
           * Capture a screenshot to `./logs/<timestamp>_follow_error.png`.
           * Return `{status:"error", message:<description>}`.
