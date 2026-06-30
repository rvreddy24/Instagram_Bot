name: instagram-feed-engager
description: |
  Brain-driven feed engagement skill. Reads all engagement criteria from
  ig:brain:strategy.engagement (niche keywords, comment style, like threshold,
  story view probability, post age limits) set by the Gemini brain.
  Scrolls the home feed, skips ads/suggested content, scores organic posts,
  leaves Gemini-generated natural comments, likes posts, and optionally views
  story rings. All actions use human-like timing, UA/viewport rotation,
  cache-only cleaning, and exponential back-off on rate-limit detection.
categories: [social-media, automation, browser, stealth]
steps:
  1. **Initialize browser (same stealth launch as the post skill)**
     - Re‑use the same Chrome profile (`./chrome-profile`).
     - Pick a random UA from the list:
       ```
       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
       "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
       "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
       ```
     - Choose a random viewport size from `{1080x1920, 1280x720, 1366x768, 1440x900}`.
     - If a Chrome instance is not already running with these arguments, launch it via the Hermes browser tools with:
       ```
       --user-data-dir=./chrome-profile
       --disable-features=VizDisplayCompositor
       --disable-background-timer-throttling
       --disable-backgrounding-occluded-windows
       --disable-renderer-backgrounding
       --force-device-scale-factor=1
       --window-size=<chosen width>,<chosen height>
       --user-agent="<$UA>"
       ```
  2. **Warm‑up & clean‑state**
     - Wait a random **start‑up delay** 2 000‑6 000 ms.
     - Navigate to `https://www.instagram.com/` if not already there.
     - **Clear only non‑essential storage** (keeps login cookies):
       ```js
       // executed via browser_console
       await caches.keys().then(keys=>Promise.all(keys.map(k=>caches.delete(k))));
       await navigator.serviceWorker.getRegistrations().then(regs=>Promise.all(regs.map(r=>r.unregister())));
       if (Math.random()<0.2) { localStorage.clear(); }
       if (Math.random()<0.1) { indexedDB.databases().then(dbs=>dbs.forEach(db=>indexedDB.deleteDatabase(db.name))); }
       ```
  3. **Scrolling loop**
     - **Load brain strategy** for engagement:
           * Retrieve `ig:brain:strategy` from Hermes memory and parse JSON.
           * Extract `eng_cfg = strategy.engagement` (or use defaults if missing):
               - `niche_keywords`         → ["AI", "tech", "machine learning"]
               - `comment_style`          → "ask a follow-up question"
               - `like_threshold_score`   → 2
               - `story_view_probability` → 0.3
               - `min_post_age_minutes`   → 5
               - `max_post_age_hours`     → 6
           * Read configurable limits (memory keys override brain for manual tuning):
               - `MAX_SCROLLS`    = memory_get(key="ig:max_scrolls")    ?? 6
               - `ENGAGE_PER_RUN` = memory_get(key="ig:engage_per_run") ?? 3
     - Initialize counters: `comments_count = 0`, `likes_count = 0`, `story_views_count = 0`.
     - Initialize empty array `engaged = []`.
     - **Prune stale seen-posts** to cap memory growth:
           * Retrieve `ig:seen_index` (a JSON array of post IDs in insertion order; default `[]`).
           * If its length > 500, drop the oldest entries until it is 500 and call `memory remove` for each dropped `ig:seen:<id>` key.
           * Save the updated index back to `ig:seen_index`.
     - For `i` from 0 to `MAX_SCROLLS-1`:
        * Scroll down by a random offset between 200 and 800 pixels using `browser_scroll(direction="down")` with a custom distance (achieved by sending `window.scrollBy(0, <offset>)` via `browser_console` or by repeating small scrolls).
        * Wait a random delay `await `random(800,1500)` ms to let new content load.
        * Increment scroll counter.
        * Grab the accessibility snapshot via `browser_snapshot(full=false)`.
        * Parse the snapshot for elements with `role="article"` (these are feed posts).
        * For each post element:
          - Extract a stable identifier: the URL of the post link inside the article, or a combination of author name + timestamp.
          - Skip if the identifier is already in `engaged` or in the memory set `ig:seen:<id>`.
          - Skip if the article contains any element with `aria-label="Sponsored"` or known ad containers (e.g., role="presentation" with typical ad class names).
          - Extract timestamp (look for `<time>` element) and compute age in minutes.
          - Skip if age < `eng_cfg.min_post_age_minutes` OR age > `eng_cfg.max_post_age_hours * 60`.
          - Extract preview text (first few lines of caption) and author name.
          - Compute a relevance score:
            * Freshness: 2 pts if < 30 min, 1 pt if < 2 h, else 0.
            * Keyword match: +2 if any of `eng_cfg.niche_keywords` appear in preview (case-insensitive).
            * Author follow status: +2 if you already follow the author (inferred from a “Following” badge).
          - Skip if score < `eng_cfg.like_threshold_score`.
          - Keep the top N (e.g., 5) scored posts in a list `candidates`.
          - Save `candidates` list to `ig:last_candidates` in memory (used by follow-manager).
  4. **After the scroll loop**, sort `candidates` by score descending.
  5. **Engagement loop** – for each candidate up to `ENGAGE_PER_RUN`:
        a. Click the post link to open it in the modal view.
        b. Wait for the modal to appear (look for `role="dialog"`).
        c. Generate a short, natural comment using Gemini:
               - Build a Gemini API call (gemini-1.5-pro, same auth pattern as instagram-brain).
               - Prompt:
                 ```
                 Write a comment for this Instagram post.
                 Post preview: <preview_text>
                 Style instruction: <eng_cfg.comment_style>
                 Max 120 characters. No hashtags. Sound like a real person.
                 Return ONLY the comment text.
                 ```
               - Parse the response text as `comment`.
               - Fallback if Gemini fails: use a generic relevant comment from a small template set
                 (e.g., "This is fascinating! 🔥", "Really insightful, thanks for sharing!").
        d. Locate the comment input box (`role="textbox"` with `aria-label="Add a comment…"`).
        e. Type the comment using human‑like keystrokes:
               - Random delay 40‑100 ms per character.
               - Small random pause (200‑500 ms) after every 6‑8 characters.
               - With probability 0.1 insert a tiny typo (extra letter then backspace) to mimic human slip.
        f. Press Enter to submit. Increment `comments_count` by 1.
        g. Wait 1‑2 s, then locate the like button (usually a `<svg aria-label="Like">`) within the comment area or below the post and click it. Increment `likes_count` by 1.
        h. (Optional) View the author's story with probability `eng_cfg.story_view_probability`:
               - Roll `random(0.0, 1.0)` — only proceed if result < `eng_cfg.story_view_probability`.
               - Click the author's name/link in the header to go to their profile.
               - If a story ring is visible (circle with a plus or a colored border), click it, wait `random(3000,5000)` ms, then go back to the feed.
               - On success, increment `story_views_count` by 1.
        i. Store the interacted post ID in `engaged` and also in Hermes `memory` under `ig:seen:<postid>` to avoid future repeats.
           Also append the post ID to `ig:seen_index` and save it back to memory.
        j. Add a random delay between engagements (3‑8 s) to look natural.
  6. **Rate‑limit detection & back‑off**
        - After each major action (scroll, click, type, etc.) check the page for an error banner containing text like “Please wait a few minutes” or “Try again later”.
        - If detected:
            * Set `base_wait = 60` seconds.
            * Retrieve current retry count from Hermes memory key `ig:engage_retry` (default 0).
            * Compute `wait = base_wait * (2 ^ retry_count)` (max 5 retries).
            * Wait that amount, then refresh the page (`browser_press(key="F5")`) and retry from step 3 (or from the current scroll position if you prefer).
            * Increment retry count and store back to memory.
            * If max retries exceeded, return `{status:"error",message:"Engagement rate limit exceeded after retries"}`.
        - On successful completion of the engagement loop, reset any retry counter (`memory remove key=ig:engage_retry`).
  7. **Return results**
        - Return a JSON object with counts:
          {
            "status": "ok",
            "scrolled": <number of scrolls performed>,
            "candidates_considered": <N>,
            "comments": <comments_count>,
            "likes": <likes_count>,
            "story_views": <story_views_count>,
            "engaged": <comments_count + likes_count>,
            "last_timestamp": <epoch of last action>
          }
  8. **Failure handling**
        - On any uncaught exception or timeout before finishing:
            * Capture a screenshot (`./logs/<timestamp>_engage_error.png`).
            * Return `{status:"error",message:<short description>}`.