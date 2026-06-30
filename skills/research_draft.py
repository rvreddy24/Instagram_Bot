"""
skills/research_draft.py — pull fresh content from brain's source catalog,
score it, generate a Gemini caption, download or create media, write draft.
"""
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
import google.generativeai as genai

import state
from config import (
    GEMINI_API_KEY, GEMINI_MODEL, DRAFTS_DIR,
)
from utils import get_logger, now_epoch

log = get_logger("research_draft")
genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel(GEMINI_MODEL)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; InstagramBot/1.0)"}
_36H = timedelta(hours=36)


# ── Fetch helpers ─────────────────────────────────────────────────────────────
def _parse_rss(url: str, source_name: str) -> list[dict]:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)
        now   = datetime.now(timezone.utc)
        results = []
        for item in items:
            title = (item.findtext("title") or
                     item.findtext("atom:title", namespaces=ns) or "").strip()
            link  = (item.findtext("link") or
                     item.findtext("atom:link", namespaces=ns) or "").strip()
            desc  = (item.findtext("description") or
                     item.findtext("atom:summary", namespaces=ns) or "").strip()
            desc  = re.sub(r"<[^>]+>", "", desc)[:300]
            pub   = (item.findtext("pubDate") or
                     item.findtext("atom:updated", namespaces=ns) or "")
            age   = _36H  # default: include if can't parse
            try:
                from email.utils import parsedate_to_datetime
                dt  = parsedate_to_datetime(pub)
                age = now - dt.astimezone(timezone.utc)
            except Exception:
                pass
            if age <= _36H and title:
                results.append({
                    "source_url": link, "source_name": source_name,
                    "title": title, "summary": desc, "age_hours": age.seconds // 3600,
                })
        return results
    except Exception as e:
        log.debug("RSS parse error for %s: %s", url, e)
        return []


def _parse_reddit(name: str) -> list[dict]:
    url = f"https://www.reddit.com/r/{name}/hot.json?limit=15"
    try:
        r = requests.get(url, headers={**_HEADERS, "User-Agent": "InstagramBot/1.0"},
                         timeout=10)
        r.raise_for_status()
        now  = datetime.now(timezone.utc)
        data = r.json().get("data", {}).get("children", [])
        results = []
        for child in data:
            p   = child.get("data", {})
            age = timedelta(seconds=now.timestamp() - p.get("created_utc", 0))
            if age > _36H:
                continue
            title = p.get("title", "").strip()
            url_  = p.get("url", "")
            text  = p.get("selftext", "")[:200]
            if title:
                results.append({
                    "source_url": url_, "source_name": f"r/{name}",
                    "title": title, "summary": text,
                    "age_hours": int(age.seconds / 3600),
                    "score_hint": p.get("score", 0),
                })
        return results
    except Exception as e:
        log.debug("Reddit parse error for r/%s: %s", name, e)
        return []


def _parse_youtube(channel_id: str, channel_name: str) -> list[dict]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns   = {
            "atom":  "http://www.w3.org/2005/Atom",
            "media": "http://search.yahoo.com/mrss/",
        }
        now     = datetime.now(timezone.utc)
        entries = root.findall("atom:entry", ns)
        results = []
        for entry in entries[:5]:
            title   = entry.findtext("atom:title", namespaces=ns, default="").strip()
            link_el = entry.find("atom:link", ns)
            link    = link_el.get("href", "") if link_el is not None else ""
            pub     = entry.findtext("atom:published", namespaces=ns, default="")
            try:
                dt  = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                age = now - dt
            except Exception:
                age = timedelta(hours=10)
            if age <= _36H and title:
                results.append({
                    "source_url": link, "source_name": channel_name,
                    "title": title, "summary": "",
                    "age_hours": int(age.seconds / 3600),
                })
        return results
    except Exception as e:
        log.debug("YouTube parse error for %s: %s", channel_id, e)
        return []


# ── Scoring ───────────────────────────────────────────────────────────────────
def _score_item(item: dict, topics: list[str], avoid: list[str]) -> float:
    title   = (item.get("title", "") + " " + item.get("summary", "")).lower()
    # avoid filter
    if any(a.lower() in title for a in avoid):
        return -1.0
    score = 0.0
    # recency
    age = item.get("age_hours", 36)
    if age < 3:
        score += 2
    elif age < 12:
        score += 1
    # topic match
    for t in topics:
        if t.lower() in title:
            score += 2
        elif any(w in title for w in t.lower().split()):
            score += 1
    # engagement hint (Reddit)
    if item.get("score_hint", 0) > 1000:
        score += 1
    return score


# ── Caption generation ────────────────────────────────────────────────────────
def _generate_caption(item: dict, cfg: dict) -> str:
    hashtags = " ".join(cfg.get("hashtags", ["#AI", "#Tech"]))
    prompt = f"""Write an Instagram caption for the following topic.

Topic: {item["title"]}
Summary: {item.get("summary", "")}
Style: {cfg.get("style", "hook + 3 facts + CTA")}
Tone: {cfg.get("caption_tone", "informative but witty")}
Hashtags to include: {hashtags}
Max length: 2200 characters.

Return ONLY the caption text. No extra commentary."""
    try:
        resp = _model.generate_content(prompt)
        return resp.text.strip()
    except Exception as e:
        log.warning("Gemini caption generation failed: %s", e)
        return f"{item['title']}\n\n{hashtags}"


# ── Media ─────────────────────────────────────────────────────────────────────
def _make_title_card(title: str, dest: Path) -> bool:
    """Use PIL to generate a simple title-card image."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img  = Image.new("RGB", (1080, 1080), color=(15, 15, 26))
        draw = ImageDraw.Draw(img)
        # Purple accent bar
        draw.rectangle([0, 900, 1080, 1080], fill=(124, 58, 237))
        # Title text — wrap manually
        words, lines, line = title.split(), [], ""
        for w in words:
            if len(line) + len(w) + 1 > 28:
                lines.append(line.strip())
                line = w + " "
            else:
                line += w + " "
        if line:
            lines.append(line.strip())
        y = 200
        for l in lines[:6]:
            draw.text((80, y), l, fill="white")
            y += 80
        img.save(dest)
        return True
    except Exception as e:
        log.error("PIL title card failed: %s", e)
        return False


def _download_media(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=20, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        if dest.stat().st_size > 30 * 1024 * 1024:
            dest.unlink()
            return False
        return True
    except Exception:
        return False


# ── Main ──────────────────────────────────────────────────────────────────────
def run() -> dict:
    strategy = state.get("brain_strategy") or {}
    cfg      = strategy.get("content", {})
    sources  = strategy.get("sources", {})
    topics   = cfg.get("topics", ["AI"])
    avoid    = cfg.get("avoid_topics", [])
    seen     = set(state.get("ig_seen_urls", []))

    # ── Fetch from all source types ───────────────────────────────────────────
    items: list[dict] = []

    rss_list = sorted(sources.get("rss", []), key=lambda x: x.get("score", 5), reverse=True)
    for src in rss_list[:5]:
        items.extend(_parse_rss(src["url"], src["name"]))

    sub_list = sorted(sources.get("subreddits", []), key=lambda x: x.get("score", 5), reverse=True)
    for src in sub_list[:3]:
        items.extend(_parse_reddit(src["name"]))

    yt_list  = sorted(sources.get("youtube_channels", []), key=lambda x: x.get("score", 5), reverse=True)
    for src in yt_list[:2]:
        items.extend(_parse_youtube(src["id"], src["name"]))

    log.info("Fetched %d items from sources.", len(items))

    # ── Deduplicate and score ─────────────────────────────────────────────────
    candidates = []
    for item in items:
        url = item.get("source_url", "")
        if url in seen:
            continue
        s = _score_item(item, topics, avoid)
        if s >= 0:
            item["_score"] = s
            candidates.append(item)

    if not candidates:
        log.error("No suitable content found after filtering.")
        return {"status": "error", "message": "No suitable content found"}

    candidates.sort(key=lambda x: x["_score"], reverse=True)
    best = candidates[0]
    log.info("Best item: %s (score=%.1f)", best["title"][:60], best["_score"])

    # Mark as seen
    seen.add(best.get("source_url", ""))
    seen_list = list(seen)[-500:]  # keep last 500
    state.set("ig_seen_urls", seen_list)

    # ── Caption ───────────────────────────────────────────────────────────────
    caption = _generate_caption(best, cfg)

    # ── Media ─────────────────────────────────────────────────────────────────
    ts   = now_epoch()
    ext  = "png"
    dest = DRAFTS_DIR / f"{ts}.{ext}"

    downloaded = False
    media_url  = best.get("media_url") or best.get("thumbnail_url")
    if media_url:
        downloaded = _download_media(media_url, dest)

    if not downloaded:
        ok = _make_title_card(best["title"], dest)
        if not ok:
            return {"status": "error",
                    "message": "No media available and PIL title card failed. "
                               "Install Pillow or place an image in ./drafts/ manually."}

    # ── Write draft ───────────────────────────────────────────────────────────
    draft_path = DRAFTS_DIR / f"{ts}.md"
    caption_escaped = caption.replace('"', '\\"')
    fm = f"""---
media: {dest}
caption: "{caption_escaped}"
topic: "{best['title'][:120]}"
source_url: "{best.get('source_url', '')}"
source_name: "{best.get('source_name', '')}"
strategy_version: {strategy.get('version', 0)}
style: "{cfg.get('style', '')}"
---
"""
    draft_path.write_text(fm, encoding="utf-8")

    log.info("Draft written to %s", draft_path)
    return {
        "status": "ok",
        "draft_path": str(draft_path),
        "topic": best["title"][:120],
        "strategy_version": strategy.get("version", 0),
    }
