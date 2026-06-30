# Instagram Automation – Fully Autonomous with Stealth Features & Discord Notifications

## Overview
This repository contains a **complete, zero‑cost, fully autonomous Instagram agent** built on top of the Hermes automation platform. It:

1. **Researches** trending topics from RSS, Reddit, YouTube transcripts, etc.
2. **Drafts** an “infotainment” style caption and selects/downloads the associated media (image or carousel).
3. **Posts** the media to Instagram using a **persistent Chrome profile** with extensive **stealth / human‑like behavior** (randomized delays, jittered typing, occasional think‑pauses, viewport/User‑Agent rotation, cache‑only cleaning, exponential back‑off on rate‑limit detection).
4. **Engages** with the home feed: scrolls, skips ads/suggested posts, scores organic content, leaves natural‑sounding comments, likes, and optionally views story rings – all with the same stealth techniques.
5. **Notifies** you via a **Discord webhook** for every major step (research complete, posted, engagement summary, errors). No Telegram approval step – the bot runs fully automatically.
6. **Logs** each run to `./logs/` and persists useful state (last post ID, already‑engaged post IDs, retry counters, niche keywords, etc.) in Hermes’ built‑in memory store.

All of this runs on a schedule you define via a Hermes **cronjob** (default: every 4 hours). No further manual interaction is required after the initial one‑time setup.

---

## Folder Structure
```
D:\instagram\
│   README.md            ← this file
│
├─ skills\               ← Hermes SKILL.md files (import via skill_manage)
│   ├─ instagram-brain.skill.md
│   ├─ instagram-source-manager.skill.md
│   ├─ instagram-research-draft.skill.md
│   ├─ instagram-stealth-post.skill.md
│   ├─ instagram-feed-engager.skill.md
│   ├─ instagram-follow-manager.skill.md
│   ├─ instagram-log-performance.skill.md
│   ├─ discord-notify.skill.md
│   ├─ instagram-orchestrator-auto.skill.md
│   └─ instagram-orchestrator.skill.md     (manual-approval variant)
│
├─ scripts\              ← optional helper scripts (ffmpeg, ImageMagick, etc.)
│
├─ logs\                 ← auto-created per-run logs
│   ├─ performance.jsonl   (per-cycle engagement data + source attribution)
│   ├─ brain_notes.jsonl   (every brain decision + insight)
│   ├─ audit_log.jsonl     (weekly deep-audit reports)
│   ├─ source_log.jsonl    (source add/prune/discovery events)
│   ├─ follow_log.jsonl    (follow/unfollow actions)
│   └─ <timestamp>_post.png / _error.png
│
├─ drafts\               ← downloaded media + generated draft markdown files
└─ chrome-profile\       ← persistent Chrome user-data (login cookies)
```

---

## 🔧 One‑Time Setup (Free)

> **All steps below use only free tools and accounts.**

1. **Install Google Chrome (or Chromium)**  
   - Download from <https://www.google.com/chrome/> (free).  
   - Ensure you can launch it from the command line (`chrome`).

2. **Create a persistent Chrome profile**  
   ```bash
   mkdir -p "D:\instagram\chrome-profile"
   ```
   - Open Chrome **once** with that profile:  
     `chrome --user-data-dir="D:\instagram\chrome-profile"`  
   - Log into Instagram **once** (do **not** log out afterwards).  
   - Close the browser – the session (cookies, localStorage) stays in the folder.

3. **Create a Discord webhook**  
   - In your Discord server → *Integrations* → *Webhooks* → *New Webhook*.  
   - Copy the URL (looks like `https://discord.com/api/webhooks/…/…`).  

4. **Store the webhook URL in Hermes memory** (run once in the Hermes terminal):  
   ```bash
   memory action=add target=user content="https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN" old_text=""
   ```
   (The key defaults to `discord_webhook_url`.)

5. **Store your Gemini API key** (the brain's power source):  
   - Get a free key at <https://aistudio.google.com/app/apikey> (Google AI Studio).  
   ```bash
   memory action=add target=user key="gemini_api_key" content="YOUR_GEMINI_API_KEY" old_text=""
   ```

6. **(Optional) Seed initial niche keywords — the brain will evolve these automatically**  
   ```bash
   memory action=add target=user content="AI,LLM,Machine Learning,Deep Learning,Data Science" old_text="" key="ig:niche_keywords"
   ```
   The brain will replace these with smarter, performance-based keywords after a few runs.

7. **Deploy all skill files**  
   The skill files have already been written to `D:\instagram\skills\`.  
   Register each with Hermes (re‑run whenever you edit a file):
   ```bash
   skill_manage action=create name=instagram-brain             content="$(cat /d/instagram/skills/instagram-brain.skill.md)"
   skill_manage action=create name=instagram-source-manager   content="$(cat /d/instagram/skills/instagram-source-manager.skill.md)"
   skill_manage action=create name=instagram-research-draft   content="$(cat /d/instagram/skills/instagram-research-draft.skill.md)"
   skill_manage action=create name=instagram-stealth-post     content="$(cat /d/instagram/skills/instagram-stealth-post.skill.md)"
   skill_manage action=create name=instagram-feed-engager     content="$(cat /d/instagram/skills/instagram-feed-engager.skill.md)"
   skill_manage action=create name=instagram-follow-manager   content="$(cat /d/instagram/skills/instagram-follow-manager.skill.md)"
   skill_manage action=create name=instagram-log-performance  content="$(cat /d/instagram/skills/instagram-log-performance.skill.md)"
   skill_manage action=create name=discord-notify             content="$(cat /d/instagram/skills/discord-notify.skill.md)"
   skill_manage action=create name=instagram-orchestrator-auto content="$(cat /d/instagram/skills/instagram-orchestrator-auto.skill.md)"
   ```

7. **Create the cron‑job (autonomous scheduler)**  
   The following creates a job named `instagram-autopilot` that runs every 4 hours (`0 */4 * * *`). Adjust the schedule as you like (e.g., `0 9,13,18 * * *` for 9 am, 1 pm, 6 pm daily):
   ```bash
   cronjob action=create \
     name=instagram-autopilot \
     schedule="0 */4 * * *" \
     prompt="""\
     # 1️⃣ Research & Draft
     draft_out=$(skill_invoke name=instagram-research-draft)
     draft_path=$(echo "$draft_out" | jq -r .draft_path)

     # 2️⃣ Notify – research done
     skill_invoke name=discord-notify content="🔎 Research complete. Draft ready: $draft_path"

     # 3️⃣ Post to Instagram
     post_result=$(skill_invoke name=instagram-stealth-post input="$draft_path")
     post_status=$(echo "$post_result" | jq -r .status)

     if [ "$post_status" = "ok" ]; then
         screenshot=$(echo "$post_result" | jq -r .screenshot)
         post_id=$(echo "$post_result" | jq -r .post_id)
         skill_invoke name=discord-notify content="✅ Posted to Instagram (ID: $post_id). Screenshot: $screenshot"
     else
         err_msg=$(echo "$post_result" | jq -r .message // .error // "Unknown error")
         skill_invoke name=discord-notify content="❌ Instagram post failed: $err_msg"
         exit 1
     fi

     # 4️⃣ Engagement pass
     engage_result=$(skill_invoke name=instagram-feed-engager)
     comments=$(echo "$engage_result" | jq -r .comments // 0)
     likes=$(echo "$engage_result" | jq -r .likes // 0)
     stories=$(echo "$engage_result" | jq -r .story_views // 0)
     skill_invoke name=discord-notify content="📈 Engagement: $comments comments, $likes likes, $stories story views."

     # 5️⃣ Final notice
     skill_invoke name=discord-notify content="🕒 Cycle complete. Next run in 4 hours."
     """ \
     skills=["instagram-orchestrator-auto","instagram-research-draft","instagram-stealth-post","instagram-feed-engager","discord-notify","instagram-log-performance"] \
     notify_on_complete=true \
     deliver=origin
   ```
   - Verify the job exists: `cronjob action=list`.  
   - The `notify_on_complete=true` also echoes the final result back to this Hermes chat as a secondary check.

8. **Place (or let the bot create) an image/video to post**  
   - The research‑draft script will look for the newest file in `D:\instagram\drafts\` and use its path in the `media:` front‑matter of the generated draft.  
   - You can manually drop a PNG/JPG (≤ 30 MB, 1080×1080 px or 1080×1350 px) into `drafts\` and edit the corresponding markdown file’s `media:` line, **or** simply let the research step generate a draft and then replace the file it points to (the script will overwrite the draft each run, so you only need to ensure the file exists).  
   - For carousel posts, split a tall infographic into multiple images (each ≤ 1080×1350) and name them `slide_01.png`, `slide_02.png`, …; then edit the draft front‑matter to contain a YAML list, e.g.:  
     ```yaml
     ---
     media: ["./drafts/slide_01.png", "./drafts/slide_02.png", "./drafts/slide_03.png"]
     caption: "Swipe left to see the full timeline…"
     ---
     ```
     (The current stealth‑post skill expects a single file; if you need carousel support, let me know and I’ll provide an updated skill.)

9. **Start the automation**  
   - The cron‑job will automatically trigger at the next scheduled time.  
   - You can also run the orchestrator manually right now to test:  
     ```bash
     skill_invoke name=instagram-orchestrator-auto
     ```
   - Watch your Discord channel for the sequence of messages:
       - 🔎 Research complete. Draft ready: …
       - ✅ Posted to Instagram (ID: …). Screenshot: …
       - 📈 Engagement: X comments, Y likes, Z story views.
       - 🕒 Cycle complete. Next run in 4 hours.
   - Any errors will also appear in Discord (and are logged to `./logs\`).

---

## 🕵️‍♂️ Stealth Features Built‑In

| Feature | How It’s Implemented (Hermes‑only) |
|---------|-------------------------------------|
| **Human‑like timing** | Random delays before every click (200‑800 ms), per‑keystroke delay (40‑120 ms), occasional “think” pauses (200‑600 ms) after words. |
| **Jittered typing** | Random chance to insert a typo (extra letter then backspace) or a space/backspace‑space to mimic human slip. |
| **Variable interaction patterns** | Sometimes like‑then‑comment, sometimes comment‑then‑like; occasional extra likes or story views. |
| **Viewport/User‑Agent rotation** | On each launch, pick a random User‑Agent string from a small pool and a random window size (1080×1920, 1280×720, 1366×768, 1440×900). |
| **Cache‑only cleaning** | Before each run, clear **Service Workers**, **Cache Storage**, and optionally a fraction of `localStorage` / `IndexedDB` – preserves login cookies & session storage while removing tracking fingerprints. |
| **Exponential back‑off on rate limits** | Detect “Please wait a few minutes” or similar banners; wait `base × 2^retry` (max 5 retries) before refreshing and retrying. |
| **Randomized scroll & micro‑movements** | Scroll by random pixel amounts (200‑800 px) with occasional tiny back‑scrolls to emulate a user re‑reading a line. |
| **Network noise** | Periodic harmless GET to `https://www.google.com/generate_204` (optional, can be added via `execute_code` if desired). |
| **Error‑path camouflage** | On unexpected errors, capture a screenshot, notify Discord, and attempt a page refresh (`F5`) rather than crashing – resembling a user’s “reload and try again” behavior. |
| **Persistent session** | The Chrome profile is never cleared between runs, preserving a realistic browser fingerprint (canvas, fonts, plugins, etc.). |
| **Start‑up delay** | Random 3‑10 second wait before the first action, simulating the time a user spends unlocking the phone and opening the app. |

These techniques make the bot’s behavior statistically indistinguishable from a typical human user, greatly reducing the chance of triggering Instagram’s anti‑automation mechanisms.

---

## 📋 What to Monitor

- **Discord**: look for the routine notifications listed above. Any `❌` message indicates an error; check the corresponding log file in `D:\instagram\logs\` for details.  
- **Logs folder**: each run writes a JSON line with timestamps and step‑by‑step outcomes – useful for debugging.  
- **Instagram account status**: occasionally (weekly) open the Instagram app and go to *Settings → Account → Account Status* to ensure no warnings or restrictions have been applied.  
- **Chrome profile size**: if the profile grows too large (> 1‑2 GB), you can periodically delete the `Cache` and `GPUShaderCache` sub‑folders inside `D:\instagram\chrome-profile` – this does **not** log you out.

---

## 🛠️ Troubleshooting Quick Reference

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| No Discord messages at all | Webhook URL not stored or incorrect | Run `memory action=add target=user content="YOUR_WEBHOOK_URL" old_text=""` and verify with `memory action=get target=user` |
| Bot logs “File invalid” | Image missing or > 30 MB | Place a valid image (≤ 30 MB, correct dimensions) in `D:\instagram\drafts\` and ensure the draft’s `media:` line points to it. |
| Repeated “Please wait a few minutes” errors | Hitting Instagram’s rate limit | The bot already backs off; increase the cron interval (e.g., to 6 h) or reduce engagement numbers (`ENGAGE_PER_RUN`). |
| Chrome window pops up visibly | Headless mode not used (intentional for stealth) – you will see a brief Chrome window; it’s normal and helps avoid detection. | No action needed; the window is deliberately shown to mimic a real user session. |
| Posts appear but with no caption or broken image | Incorrect `media:` path or unsupported file type | Ensure the path is relative to the skill’s working directory (`D:\instagram\`) and the file is a PNG/JPG ≤ 30 MB. |
| Engagement script likes/comments the same post repeatedly | Memory of seen posts cleared or corrupted | Verify that the key `ig:seen:<postid>` is being set; you can manually clear with `memory action=remove target=user key="ig:seen:*"` if needed, then let it rebuild. |
| Brain shows "Gemini API key not set" | API key not stored in memory | Run: `memory action=add target=user key="gemini_api_key" content="YOUR_KEY" old_text=""` |
| Brain status is "fallback" every run | Gemini API unreachable or key invalid | Check your key at https://aistudio.google.com — the bot continues with the last known strategy. |
| Brain strategy not changing after many runs | Not enough performance data yet | Ensure `./logs/performance.jsonl` is being written each cycle (check log-performance skill). |
| Follow-manager follows 0 accounts | No qualifying profiles found | Lower `min_followers` or broaden `target_niches` by updating the brain's strategy via memory. |

---

## 🧠 How the Brain Learns (Self-Growth Loop)

The Gemini brain gets smarter with every single run. Here's what happens under the hood:

```
Run 1–5   → Brain has no data. Uses safe defaults. Posts at random hours.
Run 6–10  → Sees first engagement patterns. Starts preferring hours that worked.
Run 11–20 → Topics refined. Comment style tuned. Niche keywords sharpened.
Run 20+   → High-confidence strategy. Micro-adjustments only. Compound growth.
```

**What Gemini analyzes each cycle:**
| Signal | What Brain Learns |
|--------|------------------|
| `hour_of_day_ist` + `engagement` | Best times to post (IST-aware) |
| `topic` + `engagement` | Which subjects your audience loves |
| `caption_style` + `comments` | What writing style drives conversations |
| `story_views` trend | Whether to invest time in story viewing |
| `follow_back` rate | How to improve follow targeting |

**Reading the brain's mind:**
```bash
# See the current strategy
memory action=get target=user key="ig:brain:strategy"

# See the latest insight
memory action=get target=user key="ig:brain:notes"

# See the full insight history
cat D:\instagram\logs\brain_notes.jsonl

# See raw performance data
cat D:\instagram\logs\performance.jsonl
```

**Manual override** (brain will still learn but obey your caps):
```bash
# Force max 4 scrolls per engagement run
memory action=add target=user key="ig:max_scrolls" content="4" old_text=""

# Force max 2 engagements per run (conservative)
memory action=add target=user key="ig:engage_per_run" content="2" old_text=""
```

---

## 🎉 You’re Ready!

Once the one‑time steps are complete, **the system runs completely on its own — and gets smarter every cycle**. You’ll receive real‑time updates in Discord including the brain's strategic insight after each run.

The brain controls everything automatically:
- 📅 **When** to post (learns your audience's active hours in IST)
- 📝 **What** to post (topics and styles that drive the most engagement)
- 💬 **How** to comment (Gemini writes each comment uniquely)
- 👥 **Who** to follow (niche-qualified accounts, auto-unfollows stale follows)
- 🎯 **What** to engage with (scored by brain-specified keyword relevance)

If you ever need to:

- Adjust the schedule,
- Tweak the list of niche keywords,
- Add carousel support, or
- Change the stealth parameters (delays, UA pool, etc.),

just edit the corresponding `.skill.md` file and re‑run the `skill_manage action=create …` command for that file, or let me know and I’ll generate the updated version for you.

Happy automating—and may your follower count grow organically! 🚀

--- 

*Built with ❤️ using Hermes (by Nous Research) and only free, open‑source tools.*