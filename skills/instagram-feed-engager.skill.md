name: instagram-feed-engager
description: |
  Scrolls the Instagram home feed, skips ads/suggested content, scores organic posts,
  leaves natural‑sounding comments, likes them, and (optionally) views story rings.
  All actions are performed with human‑like timing, occasional micro‑movements,
  viewport/User‑Agent rotation, cache‑only cleaning, and exponential back‑off on
  rate‑limit detection.
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
     - Set `MAX_SCROLLS = 6` (adjustable) and `ENGAGE_PER_RUN = 3`.
     - Initialize empty array `engaged = []`.
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
          - Extract preview text (first few lines of caption) and author name.
          - Compute a relevance score:
            * Freshness: 2 pts if < 30 min, 1 pt if < 2 h, else 0.
            * Keyword match: +1 if any of your niche keywords appear in preview.
            * Author follow status: +2 if you already follow the author (can be inferred from a “Following” badge; otherwise 0).
          - Keep the top N (e.g., 5) scored posts in a list `candidates`.
  4. **After the scroll loop**, sort `candidates` by score descending.
  5. **Engagement loop** – for each candidate up to `ENGAGE_PER_RUN`:
        a. Click the post link to open it in the modal view.
        b. Wait for the modal to appear (look for `role="dialog"`).
        c. Generate a short, natural comment using an LLM prompt:
               "React to this Instagram post in one short, friendly sentence (under 120 characters). Keep it relevant to the visible content."
               Use the preview text and any visible hashtags as context.
        d. Locate the comment input box (`role="textbox"` with `aria-label="Add a comment…"`).
        e. Type the comment using human‑like keystrokes:
               - Random delay 40‑100 ms per character.
               - Small random pause (200‑500 ms) after every 6‑8 characters.
               - With probability 0.1 insert a tiny typo (extra letter then backspace) to mimic human slip.
        f. Press Enter to submit.
        g. Wait 1‑2 s, then locate the like button (usually a `<svg aria-label="Like">`) within the comment area or below the post and click it.
        h. (Optional) To view the author’s story:
               - Click the author’s name/link in the header to go to their profile.
               - If a story ring is visible (circle with a plus or a colored border), click it, wait `random(3000,5000)` ms, then go back to the feed.
        i. Store the interacted post ID in `engaged` and also in Hermes `memory` under `ig:seen:<postid>` to avoid future repeats.
        j. Add a random delay between engagements (3‑8 s) to look natural.
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
            "engaged": <number of posts commented/liked>,
            "last_timestamp": <epoch of last action>
          }
  8. **Failure handling**
        - On any uncaught exception or timeout before finishing:
            * Capture a screenshot (`./logs/<timestamp>_engage_error.png`).
            * Return `{status:"error",message:<short description>}`.