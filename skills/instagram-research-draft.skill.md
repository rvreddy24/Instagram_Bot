name: instagram-research-draft
description: |
  Pulls recent items from RSS/Reddit/YouTube, deduplicates against the last N posts,
  and generates an “infotainment” style caption + suggested media URL.
  Writes the draft to a markdown file.
categories: [social-media, automation]
steps:
  1. Fetch recent items (last 36 h) from configured RSS feeds, Reddit subreddits, and YouTube transcripts using the `web` tool.
  2. Flatten results, deduplicate against stored recent post IDs (kept in Hermes `memory` under keys `ig:recent:<id>`).
  3. Score each item: recency boost, keyword match to your niche, and engagement hints (e.g., upvote count).
  4. Select the highest‑scoring item as the topic.
  5. Generate a caption using an LLM (via the built‑in chat or an external API) in an informational‑entertainment tone.
  6. If the source provides a media URL, download it to `./drafts/<timestamp>.(jpg|png|mp4)` using `execute_code` (e.g., curl/ffmpeg).
  7. Write a draft markdown file with front‑matter:
     ```
     ---
     media: ./drafts/20240629_123456.jpg
     caption: "Your generated caption here..."
     ---
     ```
  8. Return the path to the draft file as JSON: `{ "draft_path": "./drafts/20240629_123456.md" }`.