name: instagram-stealth-post
description: |
  Uploads an image/video from a draft file to Instagram using a persistent Chrome profile,
  with extensive human‑like behaviour (random delays, jittered typing, occasional think‑pauses,
  viewport/User‑Agent rotation, cache‑only cleaning, and exponential back‑off on rate‑limit
  detection). Returns a JSON summary for the orchestrator.
categories: [social-media, automation, browser, stealth]
steps:
  1. **Prepare**
     - Read the draft markdown (front‑matter) → extract `media` (local file path) and `caption`.
     - Verify the file exists and is ≤ 30 MB; if not, return `{status:"error",message:"File invalid"}`.
  2. **Launch Chrome with a fresh but realistic fingerprint**
     - Choose a random UA from the list below (store in a temp variable `$UA`):
       ```
       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
       "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
       "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
       ```
     - Choose a random viewport size from `{1080x1920, 1280x720, 1366x768, 1440x900}`.
     - Start Chrome via the Hermes browser tools with the arguments:
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
     - (All other Chrome flags are left at defaults – they keep the fingerprint realistic.)
  3. **Warm‑up & clean‑state**
     - Wait a random **start‑up delay** 3 000‑10 000 ms.
     - Navigate to `https://www.instagram.com/` and wait for the feed to load (presence of `[role="feed"]`).
     - **Clear only non‑essential storage** (keeps login cookies):
       ```js
       // executed via browser_console
       await caches.keys().then(keys=>Promise.all(keys.map(k=>caches.delete(k))));
       await navigator.serviceWorker.getRegistrations().then(regs=>Promise.all(regs.map(r=>r.unregister())));
       // Keep localStorage & IndexedDB that hold the session; optionally clear a fraction:
       if (Math.random()<0.2) { localStorage.clear(); }
       if (Math.random()<0.1) { indexedDB.databases().then(dbs=>dbs.forEach(db=>indexedDB.deleteDatabase(db.name))); }
       ```
  4. **Navigate to the new‑post dialog**
     - Click the “Create” button (new‑post icon) → then “Post”.
     - Before each click, wait `random(200,800)` ms.
  5. **File upload**
     - When the file‑input appears, use `browser_type` to type the **absolute** path to the media file.
     - After typing, wait `random(500,1500)` ms, then press **Enter**.
  6. **Caption entry – human‑like typing**
     - Locate the `<textarea>` with `aria-label="Write a caption…"`.
     - Split the caption into words.
     - For each word:
        * Type the word with per‑character delay `random(40,120)` ms.
        * After the word, with probability 0.15 insert a **pause** of `random(200,600)` ms (simulating a think‑break).
        * After each word, with probability 0.05 add an **extra space** or **backspace‑space** to simulate a tiny typo that is immediately corrected.
     - After the final word, optionally (p=0.1) add a final **punctuation jitter** (e.g., an extra “!” then backspace).
  7. **Share button**
     - Locate the button with `aria-label="Share"`.
     - Before clicking, wait `random(300,900)` ms.
     - Click it.
  8. **Post‑success verification & back‑off handling**
     - Wait up to **20 s** for either:
        * the toast “Your post has been shared” **or**
        * the new post to appear in the profile grid (look for an `<a>` with `href` containing `/p/`).
     - If the wait expires, check for an error banner containing text like “Please wait a few minutes” or a modal with “Try again later”.
        * If found → treat as **rate‑limit**.
        * Implement exponential back‑off:
          * `base_wait = 60 s` (initial)
          * `wait = base_wait * (2 ^ retry_count)` (max 5 retries)
          * Wait that amount, then **refresh the page** (`browser_press(key="F5")`) and retry from step 4.
          * Increment `retry_count` and store it in Hermes memory under `ig:retry_count`.
          * If max retries exceeded → return `{status:"error",message:"Rate limit exceeded after retries"}`.
     - On success:
        * Extract the post URL from the address bar (`window.location.href`) or from a `<a>` element that contains `/p/`.
        * Take a screenshot via `browser_get_images()` or `browser_snapshot(full=true)` and save it to `./logs/<timestamp>_post.png`.
        * Reset any retry counter (`memory remove key=ig:retry_count`).
        * Return `{status:"ok",timestamp:<epoch>,screenshot:<path>,post_id:<extracted_id>}`.
  9. **Failure handling**
     - On any uncaught exception or timeout before step 8:
        * Capture a screenshot (`./logs/<timestamp>_error.png`).
        * Return `{status:"error",message:<short description>}`.