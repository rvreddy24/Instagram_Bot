name: instagram-research-draft
description: |
  Brain-driven research and draft generator. Reads content strategy from
  ig:brain:strategy (topics, style, caption_tone, hashtags, avoid_topics)
  set by the Gemini brain. Pulls recent items from RSS/Reddit/YouTube,
  scores them against brain-specified topics, generates an LLM caption
  using the brain's style and tone, and writes a draft markdown file.
  Falls back to sensible defaults when no brain strategy exists yet (first run).
categories: [social-media, automation]
steps:
  1. **Load brain strategy**
       - Retrieve `ig:brain:strategy` from Hermes memory. Parse the JSON.
       - Extract `content_cfg = strategy.content` (or use defaults if missing):
             * `topics`        → ["AI", "Machine Learning", "Productivity", "Tech"]
             * `style`         → "hook-question + 3 bullet facts + CTA + hashtags"
             * `caption_tone`  → "informative but witty"
             * `avoid_topics`  → []
             * `hashtags`      → ["#AI", "#Tech", "#LearnOnInstagram"]
             * `carousel_preferred` → false
       - Store `strategy_version` for inclusion in the draft front-matter.

  2. **Fetch recent content (last 36 h) — using brain's live source catalog**
       - Read `sources = strategy.sources` from the already-loaded brain strategy.
       - **RSS feeds** (`sources.rss`):
           * For each RSS entry in the list (sorted by `score` descending, cap at top 5):
               - Fetch the RSS feed URL via `execute_code` (`requests.get(url, timeout=10)`).
               - Parse items (using `feedparser` or simple XML regex).
               - Filter to items published within the last 36 h.
               - Add to unified results list with `source_url = item.link`, `source_name = entry.name`.
       - **Subreddits** (`sources.subreddits`):
           * For each subreddit (sorted by score desc, cap at top 3):
               - Fetch `https://www.reddit.com/r/<name>/hot.json?limit=10` via `execute_code`.
               - Parse posts from the last 36 h.
               - Add each as `{source_url: post.url, source_name: "r/<name>", title, summary: selftext[:200]}`.
       - **YouTube channels** (`sources.youtube_channels`):
           * For each channel (sorted by score desc, cap at top 2):
               - Fetch `https://www.youtube.com/feeds/videos.xml?channel_id=<id>` via `execute_code`.
               - Parse the last 5 entries; filter to within 36 h.
               - Add as `{source_url: video.link, source_name: entry.name, title, summary: ""}`.
       - Flatten all into a unified list: `[{source_url, source_name, title, summary, published_at, media_url|null}]`.

  3. **Deduplicate and filter**
       - Against stored recent post IDs in Hermes memory (`ig:recent:<id>`).
       - Filter OUT any item whose title or summary contains any word from
         `content_cfg.avoid_topics` (case-insensitive).

  4. **Score and select best item**
       Score each remaining item:
         * Recency: +2 if < 3 h old, +1 if < 12 h, 0 otherwise.
         * Topic match: +2 for each exact match with `content_cfg.topics`, +1 partial.
         * Engagement hint: +1 if upvote/view count > 1000 (where available).
       Select the highest-scoring item as `topic_item`.
       Store its ID: `memory action=add key="ig:recent:<id>" content="1"`.

  5. **Generate caption using Gemini**
       - Build a Gemini API call (same pattern as instagram-brain):
             endpoint: `gemini-1.5-pro`
             prompt:
               ```
               Write an Instagram caption for the following topic.

               Topic: <topic_item.title>
               Summary: <topic_item.summary>
               Style: <content_cfg.style>
               Tone: <content_cfg.caption_tone>
               Hashtags to include: <content_cfg.hashtags joined by space>
               Max length: 2200 characters.

               Return ONLY the caption text. No extra commentary.
               ```
             generationConfig: {temperature: 0.7, maxOutputTokens: 512}
       - Parse the response text as the `caption`.
       - Fallback: if Gemini call fails, generate a basic caption from `topic_item.title`
         + `content_cfg.hashtags` joined.

  6. **Download or generate media**
       - If `topic_item.media_url` is not null:
             Download to `./drafts/<timestamp>.<ext>` via `execute_code` (curl).
             Verify file size ≤ 30 MB; if larger, fall through to title-card.
       - Else (no media URL available):
             Generate a title-card image using ImageMagick:
             ```
             convert -size 1080x1080 xc:#0f0f1a \
               -fill '#7c3aed' -draw "rectangle 0,900 1080,1080" \
               -font DejaVu-Sans-Bold -pointsize 52 \
               -fill white -gravity North -annotate +0+120 "<topic_item.title>" \
               -font DejaVu-Sans -pointsize 28 \
               -fill '#a0a0c0' -gravity South -annotate +0+110 "<content_cfg.hashtags[0..2]>" \
               ./drafts/<timestamp>_card.png
             ```
             If ImageMagick is unavailable, return:
             `{error:"No media URL and ImageMagick not found – place an image in ./drafts/ manually"}` and stop.

  7. **Write draft markdown**
       Write `./drafts/<timestamp>.md` with the following front-matter:
       ```yaml
       ---
       media: ./drafts/<timestamp>.<ext>
       caption: "<caption>"
       topic: "<topic_item.title>"
       source_url: "<topic_item.source_url>"
       source_name: "<topic_item.source_name>"
       strategy_version: <strategy_version>
       style: "<content_cfg.style>"
       ---
       ```

  8. **Return**
       Return: `{"draft_path": "./drafts/<timestamp>.md", "topic": "<topic_item.title>", "strategy_version": <N>}`