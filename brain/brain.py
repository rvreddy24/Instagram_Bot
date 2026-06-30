"""
brain/brain.py — Gemini-powered self-evaluating brain.

Modes
-----
pre         Generate a new Strategy JSON before the cycle starts.
            Also calls source_manager to score/prune/discover sources.
post        After a cycle: audit prediction accuracy, score the source
            used, update self-model, call Gemini for a retrospective insight.
deep-audit  Every DEEP_AUDIT_EVERY cycles: full accuracy analysis,
            strategy corrections, Discord weekly report.
status      Read-only snapshot of the current self-model and strategy.
"""
import json
import time
import re
from pathlib import Path
from typing import Literal

import google.generativeai as genai

import state
from config import (
    GEMINI_API_KEY, GEMINI_MODEL,
    MAX_PERF_ROWS, DEEP_AUDIT_EVERY,
    PERF_LOG, BRAIN_NOTES_LOG, AUDIT_LOG,
)
from utils import get_logger, now_epoch, ist_hour

log = get_logger("brain")

# ── Gemini setup ──────────────────────────────────────────────────────────────
genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel(GEMINI_MODEL)


def _gemini(prompt: str) -> str | None:
    """Call Gemini and return the response text. Returns None on failure."""
    if not GEMINI_API_KEY:
        log.error("GEMINI_API_KEY not set.")
        return None
    try:
        resp = _model.generate_content(prompt)
        return resp.text
    except Exception as e:
        log.error("Gemini call failed: %s", e)
        return None


def _parse_json_from_text(text: str) -> dict | None:
    """Extract the first JSON object from a Gemini response."""
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    log.error("Could not parse JSON from Gemini response.")
    return None


# ── Default structures ────────────────────────────────────────────────────────
DEFAULT_STRATEGY = {
    "version": 0,
    "updated_at": 0,
    "posting": {
        "best_hours_utc": [4, 9, 14],
        "frequency_hours": 8,
        "confidence": 0.1,
    },
    "content": {
        "topics": ["AI", "Machine Learning", "Productivity"],
        "style": "hook + 3 facts + CTA",
        "caption_tone": "informative but witty",
        "avoid_topics": [],
        "hashtags": ["#AI", "#Tech", "#MachineLearning", "#LearnOnInstagram"],
        "carousel_preferred": False,
    },
    "engagement": {
        "min_post_age_minutes": 5,
        "max_post_age_hours": 6,
        "niche_keywords": ["AI", "tech", "LLM"],
        "comment_style": "ask a thoughtful follow-up question",
        "like_threshold_score": 2,
        "story_view_probability": 0.3,
    },
    "follow": {
        "target_niches": ["AI researchers", "ML engineers", "tech founders"],
        "min_followers": 500,
        "max_following_ratio": 2.0,
        "unfollow_after_days": 14,
        "follows_per_run": 3,
    },
    "sources": {
        "rss": [
            {"url": "https://rss.arxiv.org/rss/cs.AI",
             "name": "arXiv AI", "score": 5.0, "uses": 0, "no_use_cycles": 0},
            {"url": "https://feeds.feedburner.com/venturebeat/SZYF",
             "name": "VentureBeat AI", "score": 5.0, "uses": 0, "no_use_cycles": 0},
            {"url": "https://www.technologyreview.com/feed/",
             "name": "MIT Tech Review", "score": 5.0, "uses": 0, "no_use_cycles": 0},
        ],
        "subreddits": [
            {"name": "MachineLearning", "score": 5.0, "uses": 0},
            {"name": "artificial",      "score": 5.0, "uses": 0},
            {"name": "LocalLLaMA",      "score": 5.0, "uses": 0},
        ],
        "youtube_channels": [
            {"id": "UCWX3yGbODI3HLd1VYSK8M0A",
             "name": "Two Minute Papers", "score": 5.0, "uses": 0},
            {"id": "UCbmNph6atAoGfqLoCL_duAg",
             "name": "Yannic Kilcher", "score": 5.0, "uses": 0},
        ],
        "prune_threshold": 2.5,
        "max_per_type": 10,
        "last_discovery_at": 0,
    },
    "brain_notes": "",
    "trigger_discovery": False,
}

DEFAULT_SELF_MODEL = {
    "total_cycles": 0,
    "successful_posts": 0,
    "failed_posts": 0,
    "avg_engagement_last_10": 0,
    "engagement_trend": "unknown",
    "hour_prediction_accuracy": 0.0,
    "topic_prediction_accuracy": 0.0,
    "follow_back_rate": 0.0,
    "growth_follower_per_day": 0.0,
    "worst_recent_prediction": "",
    "audit_score": 0.0,
    "last_audit_at": 0,
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _load_perf_rows(limit: int = MAX_PERF_ROWS) -> list[dict]:
    if not PERF_LOG.exists():
        return []
    rows = []
    with open(PERF_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows[-limit:]


def _load_brain_notes(limit: int = 7) -> list[dict]:
    if not BRAIN_NOTES_LOG.exists():
        return []
    rows = []
    with open(BRAIN_NOTES_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows[-limit:]


def _append_log(path: Path, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _build_heatmap(rows: list[dict]) -> list[dict]:
    buckets: dict[int, list[int]] = {h: [] for h in range(24)}
    for row in rows:
        h = row.get("hour_of_day_ist")
        if h is not None:
            buckets[h].append(row.get("engagement", 0))
    return [
        {
            "hour": h,
            "posts": len(v),
            "avg_engagement": round(sum(v) / len(v), 1) if v else 0,
        }
        for h, v in buckets.items()
        if v
    ]


def _top_bottom_topics(rows: list[dict]) -> tuple[list, list]:
    from collections import defaultdict
    agg: dict[str, list] = defaultdict(list)
    for row in rows:
        t = row.get("topic", "")
        if t:
            agg[t].append(row.get("engagement", 0))
    scored = sorted(
        [{"topic": t, "avg_engagement": round(sum(v) / len(v), 1), "count": len(v)}
         for t, v in agg.items()],
        key=lambda x: x["avg_engagement"],
        reverse=True,
    )
    return scored[:5], scored[-5:]


def _engagement_trend(rows: list[dict]) -> str:
    if len(rows) < 6:
        return "not enough data"
    recent = [r.get("engagement", 0) for r in rows[-5:]]
    prev   = [r.get("engagement", 0) for r in rows[-10:-5]]
    if not prev:
        return "not enough data"
    avg_r, avg_p = sum(recent) / len(recent), sum(prev) / len(prev)
    if avg_p == 0:
        return "stable"
    pct = round((avg_r - avg_p) / avg_p * 100, 1)
    return f"up {pct}%" if pct >= 0 else f"down {abs(pct)}%"


def _ema(old: float, new_val: float, alpha: float = 0.1) -> float:
    return round(old * (1 - alpha) + new_val * alpha, 4)


# ── Public API ────────────────────────────────────────────────────────────────
def run(mode: Literal["pre", "post", "deep-audit", "status"] = "pre",
        **kwargs) -> dict:
    """Entry point. Dispatch to the correct mode handler."""
    if not GEMINI_API_KEY:
        return {"status": "error", "message": "GEMINI_API_KEY not set in .env"}

    # Load / initialise state
    strategy   = state.get("brain_strategy") or {}
    self_model = state.get("brain_self_model") or {}

    is_first_run = not strategy
    if is_first_run:
        log.info("First run detected — seeding default strategy.")
        strategy   = dict(DEFAULT_STRATEGY)
        self_model = dict(DEFAULT_SELF_MODEL)
        state.update({"brain_strategy": strategy,
                      "brain_self_model": self_model})
        from skills.discord_notify import notify
        notify("🧠🌱 Brain initialized for first run. Using default strategy. "
               "It will learn from your results.")

    if not self_model:
        self_model = dict(DEFAULT_SELF_MODEL)

    if mode == "pre":
        return _run_pre(strategy, self_model)
    elif mode == "post":
        return _run_post(strategy, self_model, **kwargs)
    elif mode == "deep-audit":
        return _run_deep_audit(strategy, self_model)
    elif mode == "status":
        return _run_status(strategy, self_model)
    else:
        return {"status": "error", "message": f"Unknown mode: {mode}"}


# ── PRE ───────────────────────────────────────────────────────────────────────
def _run_pre(strategy: dict, self_model: dict) -> dict:
    log.info("Brain PRE-cycle starting (strategy v%s).", strategy.get("version", 0))

    # 1. Source management
    from skills.source_manager import run as source_run
    src_result = source_run()
    log.info("Source manager: %s", src_result)

    # Reload strategy after source manager may have updated it
    strategy = state.get("brain_strategy") or strategy

    # 2. Performance data
    rows      = _load_perf_rows()
    heatmap   = _build_heatmap(rows)
    top, bot  = _top_bottom_topics(rows)
    trend     = _engagement_trend(rows)

    # Update self-model engagement trend
    self_model["engagement_trend"] = trend
    if rows:
        last10  = [r.get("engagement", 0) for r in rows[-10:]]
        self_model["avg_engagement_last_10"] = round(sum(last10) / len(last10), 1)

    # 3. Gemini prompt
    prompt = f"""You are the strategic brain of an autonomous Instagram growth bot.
Analyze ALL data below and return an updated full Strategy JSON.
Be specific, data-driven, and evolving — do not just repeat the last strategy.

## Self-Model
{json.dumps(self_model, indent=2)}

## Performance history (last {MAX_PERF_ROWS} runs)
{json.dumps(rows, indent=2)}

## Source catalog
{json.dumps(strategy.get("sources", {}), indent=2)}

## Hour-of-day engagement heatmap (IST)
{json.dumps(heatmap, indent=2)}

## Top performing topics
{json.dumps(top, indent=2)}

## Worst performing topics
{json.dumps(bot, indent=2)}

## Engagement trend
{trend}

## Current strategy (v{strategy.get("version", 0)})
{json.dumps(strategy, indent=2)}

## Last brain insight
{strategy.get("brain_notes", "")}

## Instructions
Return ONLY a valid JSON object with this EXACT schema (no markdown fences):
{{
  "version": {strategy.get("version", 0) + 1},
  "updated_at": {now_epoch()},
  "posting": {{
    "best_hours_utc": [<up to 3 ints>],
    "frequency_hours": <4-12>,
    "confidence": <0.0-1.0>
  }},
  "content": {{
    "topics": [<3-5 specific strings>],
    "style": "<caption structure>",
    "caption_tone": "<tone>",
    "avoid_topics": [<list>],
    "hashtags": [<8-12 hashtags>],
    "carousel_preferred": <true/false>
  }},
  "engagement": {{
    "min_post_age_minutes": <int>,
    "max_post_age_hours": <int>,
    "niche_keywords": [<list>],
    "comment_style": "<instruction>",
    "like_threshold_score": <int>,
    "story_view_probability": <0.0-1.0>
  }},
  "follow": {{
    "target_niches": [<list>],
    "min_followers": <int>,
    "max_following_ratio": <float>,
    "unfollow_after_days": <int>,
    "follows_per_run": <2-10>
  }},
  "sources": <keep existing structure unchanged — source_manager handles pruning>,
  "brain_notes": "<one actionable sentence, max 200 chars>",
  "trigger_discovery": <true/false>
}}"""

    raw = _gemini(prompt)
    new_strategy = _parse_json_from_text(raw) if raw else None

    if not new_strategy:
        log.warning("Gemini call failed — keeping existing strategy (fallback).")
        state.update({"brain_self_model": self_model})
        return {"status": "fallback", "mode": "pre",
                "strategy_version": strategy.get("version", 0),
                "brain_notes": strategy.get("brain_notes", ""),
                "source_summary": src_result,
                "self_model_snapshot": self_model}

    # Preserve sources from state (source_manager already updated them)
    new_strategy["sources"] = strategy.get("sources", new_strategy.get("sources", {}))

    # 4. Record prediction for post-cycle audit
    state.set("brain_last_prediction", {
        "strategy_version": new_strategy["version"],
        "predicted_best_hours": new_strategy["posting"]["best_hours_utc"],
        "predicted_topics": new_strategy["content"]["topics"],
        "predicted_at": now_epoch(),
    })

    # 5. Persist
    state.update({"brain_strategy": new_strategy,
                  "brain_self_model": self_model})

    _append_log(BRAIN_NOTES_LOG, {
        "timestamp": now_epoch(), "mode": "pre",
        "version": new_strategy["version"],
        "brain_notes": new_strategy.get("brain_notes", ""),
        "trigger_discovery": new_strategy.get("trigger_discovery", False),
        "source_summary": src_result,
    })

    log.info("Brain PRE done. Strategy v%s. Notes: %s",
             new_strategy["version"], new_strategy.get("brain_notes", ""))

    return {
        "status": "ok", "mode": "pre",
        "strategy_version": new_strategy["version"],
        "brain_notes": new_strategy.get("brain_notes", ""),
        "source_discovery_triggered": src_result.get("discovery_triggered", False),
        "source_summary": src_result,
        "self_model_snapshot": {
            "total_cycles":     self_model["total_cycles"],
            "engagement_trend": self_model["engagement_trend"],
            "audit_score":      self_model["audit_score"],
        },
    }


# ── POST ──────────────────────────────────────────────────────────────────────
def _run_post(strategy: dict, self_model: dict,
              post_result: dict = None, engage_result: dict = None,
              follow_result: dict = None, draft_path: str = None,
              strategy_version: int = None, **_) -> dict:
    log.info("Brain POST-cycle starting.")
    post_result    = post_result    or {}
    engage_result  = engage_result  or {}
    follow_result  = follow_result  or {}

    # 6. Update self-model counts
    self_model["total_cycles"] += 1
    if post_result.get("status") == "ok":
        self_model["successful_posts"] += 1
    else:
        self_model["failed_posts"] += 1

    rows = _load_perf_rows()
    if rows:
        last10 = [r.get("engagement", 0) for r in rows[-10:]]
        self_model["avg_engagement_last_10"] = round(sum(last10) / len(last10), 1)
    self_model["engagement_trend"] = _engagement_trend(rows)

    # Follow-back rate from following log
    following_log = state.get("following_log") or []
    checked = [e for e in following_log if e.get("followed_back") is not None]
    if checked:
        rate = sum(1 for e in checked if e["followed_back"]) / len(checked)
        self_model["follow_back_rate"] = round(rate, 3)

    # 7. Audit prediction
    prediction = state.get("brain_last_prediction") or {}
    hour_correct  = False
    topic_correct = False

    if draft_path:
        try:
            import re as _re
            text = Path(draft_path).read_text(encoding="utf-8")
            topic_match = _re.search(r'^topic:\s*"?(.+?)"?\s*$', text, _re.MULTILINE)
            draft_topic = topic_match.group(1).strip() if topic_match else ""
            actual_h    = ist_hour()
            pred_hours  = prediction.get("predicted_best_hours", [])
            pred_topics = prediction.get("predicted_topics", [])
            hour_correct  = actual_h in pred_hours
            topic_correct = any(t.lower() in draft_topic.lower()
                                for t in pred_topics)
        except Exception as e:
            log.warning("Prediction audit parse error: %s", e)

    self_model["hour_prediction_accuracy"]  = _ema(
        self_model["hour_prediction_accuracy"], 1 if hour_correct else 0)
    self_model["topic_prediction_accuracy"] = _ema(
        self_model["topic_prediction_accuracy"], 1 if topic_correct else 0)

    # 8. Score the source used this cycle
    if draft_path:
        try:
            import re as _re
            text = Path(draft_path).read_text(encoding="utf-8")
            src_match = _re.search(r'^source_url:\s*"?(.+?)"?\s*$', text, _re.MULTILINE)
            if src_match:
                used_url   = src_match.group(1).strip()
                engagement = engage_result.get("engagement", 0)
                sources    = strategy.get("sources", {})
                for stype in ("rss", "subreddits", "youtube_channels"):
                    for src in sources.get(stype, []):
                        key = src.get("url") or src.get("name", "")
                        if key == used_url:
                            old_score = src.get("score", 5.0)
                            old_uses  = src.get("uses", 0)
                            src["score"] = round(
                                (old_score * old_uses + engagement) / (old_uses + 1), 2)
                            src["uses"]        = old_uses + 1
                            src["last_used_at"] = now_epoch()
                strategy["sources"] = sources
                state.set("brain_strategy", strategy)
        except Exception as e:
            log.warning("Source scoring error: %s", e)

    # 9. Gemini retrospective
    prompt = f"""You are the strategic brain of an autonomous Instagram bot reflecting on a completed cycle.

## What I predicted (strategy v{prediction.get("strategy_version", "?")})
Best hours (UTC): {prediction.get("predicted_best_hours", [])}
Topics: {prediction.get("predicted_topics", [])}

## What actually happened
Post time hour (IST): {ist_hour()}
Post status: {post_result.get("status", "unknown")}
Engagement: {engage_result.get("comments", 0)} comments, {engage_result.get("likes", 0)} likes
Followed: {follow_result.get("followed", 0)}, follow-back rate: {self_model["follow_back_rate"]}

## My self-model
{json.dumps(self_model, indent=2)}

Return ONLY JSON (no markdown):
{{
  "insight": "<one sentence, max 200 chars, specific and actionable>",
  "adjust_confidence": <-0.1 to 0.1>,
  "worst_prediction": "<what I got most wrong, or empty string>"
}}"""

    raw     = _gemini(prompt)
    retro   = _parse_json_from_text(raw) if raw else None
    insight = ""

    if retro:
        insight = retro.get("insight", "")
        adj     = float(retro.get("adjust_confidence", 0))
        conf    = strategy.get("posting", {}).get("confidence", 0.5)
        strategy.setdefault("posting", {})["confidence"] = round(
            max(0.0, min(1.0, conf + adj)), 3)
        if retro.get("worst_prediction"):
            self_model["worst_recent_prediction"] = retro["worst_prediction"]

    # Persist
    state.update({"brain_self_model": self_model,
                  "brain_strategy":   strategy})

    # Check deep audit
    deep_audit_triggered = (
        self_model["total_cycles"] > 0 and
        self_model["total_cycles"] % DEEP_AUDIT_EVERY == 0
    )

    _append_log(BRAIN_NOTES_LOG, {
        "timestamp": now_epoch(), "mode": "post",
        "version": strategy.get("version", 0),
        "insight": insight,
        "hour_correct": hour_correct,
        "topic_correct": topic_correct,
        "engagement": engage_result.get("engagement", 0),
    })

    log.info("Brain POST done. Insight: %s", insight)
    return {
        "status": "ok", "mode": "post",
        "insight": insight,
        "new_confidence": strategy.get("posting", {}).get("confidence", 0),
        "self_model": {
            "total_cycles":            self_model["total_cycles"],
            "engagement_trend":        self_model["engagement_trend"],
            "hour_prediction_accuracy": self_model["hour_prediction_accuracy"],
            "topic_prediction_accuracy": self_model["topic_prediction_accuracy"],
        },
        "deep_audit_triggered": deep_audit_triggered,
    }


# ── DEEP AUDIT ────────────────────────────────────────────────────────────────
def _run_deep_audit(strategy: dict, self_model: dict) -> dict:
    log.info("Brain DEEP-AUDIT starting.")
    from skills.discord_notify import notify

    all_rows   = _load_perf_rows(limit=9999)
    brain_log  = _load_brain_notes()
    heatmap    = _build_heatmap(all_rows)
    top, bot   = _top_bottom_topics(all_rows)

    prompt = f"""You are the strategic brain conducting your weekly self-audit.
Analyze ALL data and produce a comprehensive audit report.

## Full performance history ({len(all_rows)} runs)
{json.dumps(all_rows, indent=2)}

## Brain decision log (last 7 cycles)
{json.dumps(brain_log, indent=2)}

## Hour-of-day heatmap (IST)
{json.dumps(heatmap, indent=2)}

## Top topics
{json.dumps(top, indent=2)}

## Worst topics
{json.dumps(bot, indent=2)}

## Self-model
{json.dumps(self_model, indent=2)}

## Current strategy
{json.dumps(strategy, indent=2)}

Return ONLY JSON (no markdown):
{{
  "audit_score": <0.0-1.0>,
  "key_findings": [<up to 5 strings>],
  "strategy_corrections": {{<field_path>: <new_value>}},
  "sources_to_drop": [<url or name strings>],
  "sources_to_find": [<topic strings>],
  "reset_confidence": <true/false>,
  "weekly_summary": "<3-4 sentences: biggest win, biggest miss, plan for next week>"
}}"""

    raw    = _gemini(prompt)
    report = _parse_json_from_text(raw) if raw else None

    if not report:
        log.error("Deep audit Gemini call failed.")
        notify("🧠📊 Weekly deep audit failed — Gemini call error. Will retry next cycle.")
        return {"status": "error", "mode": "deep-audit"}

    # Apply corrections
    corrections = report.get("strategy_corrections", {})
    for path, val in corrections.items():
        keys = path.split(".")
        obj  = strategy
        for k in keys[:-1]:
            obj = obj.setdefault(k, {})
        obj[keys[-1]] = val

    if report.get("reset_confidence"):
        strategy.setdefault("posting", {})["confidence"] = 0.3

    # Drop sources flagged by audit
    drop = set(report.get("sources_to_drop", []))
    for stype in ("rss", "subreddits", "youtube_channels"):
        strategy.setdefault("sources", {}).setdefault(stype, [])
        kept = []
        for src in strategy["sources"][stype]:
            key = src.get("url") or src.get("name", "")
            if key in drop:
                log.info("Deep audit dropping source: %s", key)
            else:
                kept.append(src)
        strategy["sources"][stype] = kept

    # Discover new sources if requested
    if report.get("sources_to_find"):
        from skills.source_manager import run as source_run
        source_run(force_discovery=True,
                   force_topics=report["sources_to_find"])

    self_model["audit_score"]    = report["audit_score"]
    self_model["last_audit_at"]  = now_epoch()

    state.update({"brain_strategy": strategy,
                  "brain_self_model": self_model})

    _append_log(AUDIT_LOG, {
        "timestamp": now_epoch(),
        "audit_score": report["audit_score"],
        "key_findings": report.get("key_findings", []),
        "weekly_summary": report.get("weekly_summary", ""),
        "total_cycles": self_model["total_cycles"],
    })

    summary = report.get("weekly_summary", "No summary generated.")
    notify(
        f"🧠📊 **Weekly Brain Report** (cycle {self_model['total_cycles']})\n\n"
        f"Audit score: **{report['audit_score']}/1.0**\n"
        f"{summary}\n\n"
        f"Top finding: {report.get('key_findings', ['—'])[0]}"
    )

    log.info("Deep audit done. Score: %s", report["audit_score"])
    return {
        "status": "ok", "mode": "deep-audit",
        "audit_score": report["audit_score"],
        "key_findings": report.get("key_findings", []),
        "weekly_summary": summary,
    }


# ── STATUS ────────────────────────────────────────────────────────────────────
def _run_status(strategy: dict, self_model: dict) -> dict:
    src = strategy.get("sources", {})

    def _avg(lst):
        scores = [s.get("score", 0) for s in lst if s.get("uses", 0) > 0]
        return round(sum(scores) / len(scores), 2) if scores else 0.0

    return {
        "status": "ok", "mode": "status",
        "strategy_version": strategy.get("version", 0),
        "self_model": self_model,
        "source_summary": {
            "rss_count":           len(src.get("rss", [])),
            "rss_avg_score":       _avg(src.get("rss", [])),
            "subreddit_count":     len(src.get("subreddits", [])),
            "subreddit_avg_score": _avg(src.get("subreddits", [])),
            "youtube_count":       len(src.get("youtube_channels", [])),
            "youtube_avg_score":   _avg(src.get("youtube_channels", [])),
        },
        "strategy_highlights": {
            "best_hours_utc": strategy.get("posting", {}).get("best_hours_utc", []),
            "top_topics":     strategy.get("content", {}).get("topics", []),
            "confidence":     strategy.get("posting", {}).get("confidence", 0),
        },
    }
