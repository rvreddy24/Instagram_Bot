# Instagram Bot 🤖

An autonomous Instagram growth agent powered by the **Gemini AI brain**. It handles everything on its own — finding content, writing captions, posting at the right time, engaging with the community, managing its follow list, and continuously learning from its own results.

---

## What It Does

This bot runs on a fully automatic schedule and handles every part of your Instagram presence without you lifting a finger. It doesn't just execute fixed rules — it **thinks**, **learns**, and **improves** over time using Gemini AI.

Every single cycle, the bot:

- Decides **what to post** based on what's worked before
- Finds the best **content from the internet** (news, Reddit, YouTube)
- Writes a **Gemini-generated caption** in your preferred tone and style
- Posts at the **optimal time** for your audience
- Engages with the home feed by leaving **natural AI-written comments**
- Follows **niche-relevant accounts** and quietly unfollows those who don't follow back
- Logs every action and sends you a **Discord notification** with a full report

---

## The Brain

The heart of the bot is a self-evaluating Gemini AI brain that gets smarter after every single run.

**It manages its own content sources.** The brain maintains a live catalog of RSS feeds, subreddits, and YouTube channels. It scores each source based on how much real engagement the posts from that source actually received. Sources that consistently underperform get dropped automatically. When the pool shrinks, it goes and discovers new sources on its own using web searches.

**It audits its own predictions.** Before every cycle, the brain records what it predicts — which hour will get the best engagement, which topic will resonate. After the cycle ends, it checks whether it was right and updates its accuracy score accordingly.

**It maintains a self-model.** The brain tracks everything about itself — total cycles run, successful posts, engagement trends, follow-back rates, worst recent prediction, and an overall audit score. This self-awareness lets it course-correct without any human input.

**Every 7 cycles, it runs a deep audit.** It reviews the entire history of decisions it has made, identifies what it got wrong, rebalances the source portfolio, corrects the strategy, and sends you a weekly brain report on Discord.

---

## How It Grows

The bot starts conservatively with safe defaults and a neutral strategy. As it collects real data from your account, it evolves:

- **Early runs** — Learning mode. Posts cautiously, uses default sources, no strong opinions yet.
- **After ~10 runs** — Patterns emerge. Begins favouring certain hours, topics, and sources.
- **After ~20 runs** — High confidence. Strategy is tightly tuned to your audience's actual behaviour.
- **Ongoing** — Micro-adjustments every cycle. Compound improvement over time.

---

## Skills

The bot is made up of modular skills, each responsible for one part of the pipeline.

| Skill | What It Does |
|---|---|
| **Brain** | The central intelligence. Generates strategy, audits predictions, updates the self-model, runs weekly deep audits. |
| **Source Manager** | Scores, prunes, and discovers content sources (RSS, Reddit, YouTube) automatically. |
| **Research & Draft** | Pulls fresh content from the brain's live source catalog and generates a Gemini caption. |
| **Stealth Post** | Uploads the post to Instagram using a human-like browser session to avoid detection. |
| **Feed Engager** | Scrolls the home feed, scores posts using brain criteria, and leaves Gemini-written comments. |
| **Follow Manager** | Finds niche-qualified accounts to follow and quietly unfollows stale non-reciprocals. |
| **Log Performance** | Records every run's engagement data, source attribution, and strategy version to a log file. |
| **Discord Notify** | Sends real-time updates and the weekly brain report to your Discord channel. |
| **Auto Orchestrator** | Runs the full pipeline end-to-end, completely hands-off. |
| **Manual Orchestrator** | Same pipeline, but pauses and waits for your approval before posting. |

---

## What the Brain Controls

Every decision in the bot is made by Gemini AI — nothing is hardcoded.

- 📅 **When to post** — learned from your audience's actual active hours (in IST)
- 📝 **What to post** — topics ranked by historical engagement from your own account
- 🎨 **How to write** — caption style and tone refined based on what gets comments
- 🔍 **Where to find content** — live source catalog, auto-managed and self-improving
- 💬 **How to comment** — each comment is written fresh by Gemini based on the post
- 👥 **Who to follow** — niche-matched accounts that fit the brain's current targeting
- 🔁 **Who to unfollow** — stale non-reciprocals cleaned up automatically

---

## Discord Reports

You receive a message on Discord at every stage of each cycle, including:

- Brain strategy version and its latest insight
- Whether new content sources were discovered or underperformers were dropped
- Post confirmation with ID
- Engagement summary (comments, likes, story views)
- Follow/unfollow counts and follow-back rate
- Post-cycle brain insight with updated confidence and accuracy scores
- A full weekly brain report every 7 cycles

---

## Privacy & Safety

- Your Instagram login session is stored **locally only** in a persistent browser profile and is never uploaded anywhere.
- All logs and drafts stay on your machine and are excluded from version control.
- The bot uses randomised human-like timing, browser fingerprint rotation, and natural typing patterns to stay under Instagram's radar.
- All engagement actions have built-in rate-limit detection and automatic back-off.

---

## Built With

- [Gemini AI (gemini-1.5-pro)](https://deepmind.google/technologies/gemini/) — brain, caption generation, comment writing
- [Hermes by Nous Research](https://nousresearch.com/) — agent runtime, memory, skill orchestration
- Chrome (persistent profile) — stealthy browser automation
- Discord webhooks — real-time notifications

---

*This project is for educational and personal use. Use responsibly and in accordance with Instagram's Terms of Service.*