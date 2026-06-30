"""
skills/log_performance.py — write per-cycle metrics to performance.jsonl
and update rolling aggregates in state.json.
"""
import json
import re
from pathlib import Path

import state
from config import PERF_LOG
from utils import get_logger, now_epoch, ist_hour, utc_hour, slugify

log = get_logger("log_performance")


def run(draft_path: str, post_result: dict, engage_result: dict,
        follow_result: dict = None, strategy_version: int = 0) -> dict:
    post_result   = post_result   or {}
    engage_result = engage_result or {}
    follow_result = follow_result or {"followed": 0, "unfollowed": 0}

    # ── Parse draft front-matter ──────────────────────────────────────────────
    fm: dict[str, str] = {}
    try:
        text = Path(draft_path).read_text(encoding="utf-8")
        m = re.search(r"^---\n(.*?)\n---", text, re.DOTALL | re.MULTILINE)
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip().strip('"')
    except Exception as e:
        log.warning("Could not parse draft front-matter: %s", e)

    topic       = fm.get("topic", "unknown")
    style       = fm.get("style", "")
    media       = fm.get("media", "")
    source_url  = fm.get("source_url", "")
    source_name = fm.get("source_name", "")

    # infographic_id = basename without extension
    infographic_id = Path(media).stem if media else "unknown"

    # ── Timestamps ────────────────────────────────────────────────────────────
    epoch    = now_epoch()
    ist_h    = ist_hour(epoch)
    utc_h    = utc_hour(epoch)

    # ── Engagement ────────────────────────────────────────────────────────────
    likes    = engage_result.get("likes", 0)
    comments = engage_result.get("comments", 0)
    engagement = likes + comments

    record = {
        "timestamp":       epoch,
        "infographic_id":  infographic_id,
        "topic":           topic,
        "caption_style":   style,
        "strategy_version": strategy_version,
        "source_url":      source_url,
        "source_name":     source_name,
        "views":           likes + comments * 2,  # proxy
        "likes":           likes,
        "comments":        comments,
        "story_views":     engage_result.get("story_views", 0),
        "engagement":      engagement,
        "followed":        follow_result.get("followed", 0),
        "unfollowed":      follow_result.get("unfollowed", 0),
        "hour_of_day_utc": utc_h,
        "hour_of_day_ist": ist_h,
        "post_id":         post_result.get("post_id"),
        "post_status":     post_result.get("status", "unknown"),
    }

    # ── Append to JSONL ───────────────────────────────────────────────────────
    with open(PERF_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ── Update rolling aggregates in state ────────────────────────────────────
    total_runs = state.get("ig_total_runs", 0) + 1
    state.set("ig_total_runs", total_runs)

    # hour bucket
    hour_counts = state.get("ig_hour_counts", {})
    hour_score  = state.get("ig_hour_score",  {})
    key = str(ist_h)
    hour_counts[key] = hour_counts.get(key, 0) + 1
    hour_score[key]  = hour_score.get(key,  0) + engagement
    state.update({"ig_hour_counts": hour_counts, "ig_hour_score": hour_score})

    # topic bucket
    slug = slugify(topic)
    topic_eng   = state.get("ig_topic_eng",   {})
    topic_count = state.get("ig_topic_count",  {})
    topic_eng[slug]   = topic_eng.get(slug,   0) + engagement
    topic_count[slug] = topic_count.get(slug, 0) + 1
    state.update({"ig_topic_eng": topic_eng, "ig_topic_count": topic_count})

    log.info("Logged performance: topic=%s engagement=%d ist_hour=%d", topic, engagement, ist_h)
    return {
        "status": "ok", "logged": True,
        "record_summary": {
            "topic": topic, "engagement": engagement,
            "hour_of_day_ist": ist_h, "strategy_version": strategy_version,
        },
    }
