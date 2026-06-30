"""
skills/source_manager.py — autonomous content source lifecycle.

Scores every RSS / subreddit / YouTube channel against real engagement data,
prunes underperformers, and discovers new sources when the pool is weak.
"""
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import requests

import state
from config import (
    SOURCE_LOG, PERF_LOG,
    MIN_USES_TO_SCORE, DISCOVERY_TRIGGER_THRESHOLD, MAX_SOURCES_PER_TYPE,
)
from utils import get_logger, now_epoch

log = get_logger("source_manager")
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; InstagramBot/1.0)"}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _append_source_log(record: dict) -> None:
    with open(SOURCE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _fetch(url: str, timeout: int = 10) -> requests.Response | None:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        log.debug("Fetch failed for %s: %s", url, e)
        return None


def _rss_is_valid(url: str, max_age_days: int = 7) -> bool:
    """Return True if the RSS feed has at least one item published within max_age_days."""
    r = _fetch(url)
    if not r:
        return False
    try:
        root = ET.fromstring(r.text)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}
        # RSS 2.0
        items = root.findall(".//item")
        # Atom
        if not items:
            items = root.findall(".//atom:entry", ns)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        for item in items[:5]:
            pub = (item.findtext("pubDate") or
                   item.findtext("atom:updated", namespaces=ns) or "")
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub)
                if dt > cutoff:
                    return True
            except Exception:
                return True  # can't parse date — assume it's fine
    except Exception:
        pass
    return False


def _youtube_rss_is_valid(channel_id: str) -> bool:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    return _rss_is_valid(url, max_age_days=30)


def _subreddit_subscribers(name: str) -> int:
    r = _fetch(f"https://www.reddit.com/r/{name}/about.json")
    if not r:
        return 0
    try:
        return r.json().get("data", {}).get("subscribers", 0)
    except Exception:
        return 0


# ── Main ──────────────────────────────────────────────────────────────────────
def run(force_discovery: bool = False, force_topics: list[str] = None) -> dict:
    strategy = state.get("brain_strategy") or {}
    sources  = strategy.get("sources", {
        "rss": [], "subreddits": [], "youtube_channels": [],
        "prune_threshold": 2.5, "max_per_type": MAX_SOURCES_PER_TYPE,
        "last_discovery_at": 0,
    })
    topics = force_topics or strategy.get("content", {}).get("topics", ["AI"])
    prune_threshold = sources.get("prune_threshold", 2.5)
    max_per_type    = sources.get("max_per_type", MAX_SOURCES_PER_TYPE)

    # ── 1. Build score map from performance log ───────────────────────────────
    score_map: dict[str, dict] = {}
    if PERF_LOG.exists():
        with open(PERF_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    url = row.get("source_url", "")
                    if not url:
                        continue
                    if url not in score_map:
                        score_map[url] = {"total_engagement": 0, "uses": 0}
                    score_map[url]["total_engagement"] += row.get("engagement", 0)
                    score_map[url]["uses"] += 1
                except Exception:
                    pass

    # ── 2. Apply scores ───────────────────────────────────────────────────────
    for stype in ("rss", "subreddits", "youtube_channels"):
        for src in sources.get(stype, []):
            key = src.get("url") or src.get("name", "")
            if key in score_map:
                s = score_map[key]
                if s["uses"] >= MIN_USES_TO_SCORE:
                    src["score"] = round(s["total_engagement"] / s["uses"], 2)
                src["uses"] = s["uses"]
                src.pop("no_use_cycles", None)
            else:
                # Never used — count idle cycles
                nc = src.get("no_use_cycles", 0) + 1
                src["no_use_cycles"] = nc
                if nc >= 5:
                    src["score"] = 0.0

    # ── 3. Prune ──────────────────────────────────────────────────────────────
    pruned = 0
    for stype in ("rss", "subreddits", "youtube_channels"):
        kept = []
        for src in sources.get(stype, []):
            uses  = src.get("uses", 0)
            score = src.get("score", 5.0)
            if uses >= MIN_USES_TO_SCORE and score < prune_threshold:
                log.info("Pruning %s source: %s (score=%.2f)", stype, src.get("name", "?"), score)
                _append_source_log({
                    "timestamp": now_epoch(), "action": "prune",
                    "type": stype, "name": src.get("name", ""),
                    "url": src.get("url", src.get("name", "")),
                    "score": score, "uses": uses,
                    "reason": "score below prune_threshold",
                })
                pruned += 1
            else:
                kept.append(src)
        sources[stype] = kept

    # ── 4. Check discovery need ───────────────────────────────────────────────
    now        = now_epoch()
    total      = sum(len(sources.get(t, [])) for t in ("rss", "subreddits", "youtube_channels"))
    all_scored = [s for t in ("rss", "subreddits", "youtube_channels")
                  for s in sources.get(t, []) if s.get("uses", 0) >= MIN_USES_TO_SCORE]
    avg_score  = (sum(s.get("score", 5.0) for s in all_scored) / len(all_scored)
                  if all_scored else 5.0)

    needs_discovery = (
        force_discovery
        or any(len(sources.get(t, [])) < DISCOVERY_TRIGGER_THRESHOLD
               for t in ("rss", "subreddits", "youtube_channels"))
        or avg_score < prune_threshold * 1.5
        or pruned > max(1, total * 0.3)
        or (now - sources.get("last_discovery_at", 0) > 7 * 86400 and total < 15)
    )

    # ── 5. Discover ───────────────────────────────────────────────────────────
    discovered = 0
    if needs_discovery:
        log.info("Source discovery triggered. Topics: %s", topics)
        discovered += _discover_rss(sources, topics, max_per_type)
        discovered += _discover_subreddits(sources, topics, max_per_type)
        discovered += _discover_youtube(sources, topics, max_per_type)
        sources["last_discovery_at"] = now_epoch()

    # ── 6. Cap ────────────────────────────────────────────────────────────────
    for stype in ("rss", "subreddits", "youtube_channels"):
        lst = sources.get(stype, [])
        if len(lst) > max_per_type:
            lst.sort(key=lambda x: x.get("score", 5.0))
            excess = lst[:len(lst) - max_per_type]
            for src in excess:
                _append_source_log({
                    "timestamp": now_epoch(), "action": "cap-prune",
                    "type": stype, "name": src.get("name", ""),
                    "reason": "exceeded max_per_type",
                })
            sources[stype] = lst[len(lst) - max_per_type:]

    # ── 7. Persist ────────────────────────────────────────────────────────────
    strategy["sources"] = sources
    state.set("brain_strategy", strategy)

    total_now = {t: len(sources.get(t, [])) for t in ("rss", "subreddits", "youtube_channels")}
    log.info("Source manager done. Pruned=%d Discovered=%d Total=%s", pruned, discovered, total_now)
    return {
        "status": "ok",
        "pruned": pruned,
        "discovered": discovered,
        "total_sources": total_now,
        "discovery_triggered": needs_discovery,
        "avg_source_score": round(avg_score, 2),
    }


# ── Discovery helpers ─────────────────────────────────────────────────────────
def _existing_keys(sources: dict) -> set[str]:
    keys = set()
    for stype in ("rss", "subreddits", "youtube_channels"):
        for s in sources.get(stype, []):
            keys.add(s.get("url") or s.get("name") or s.get("id", ""))
    return keys


def _discover_rss(sources: dict, topics: list[str], max_per_type: int) -> int:
    existing  = _existing_keys(sources)
    current   = len(sources.get("rss", []))
    slots     = max_per_type - current
    added     = 0
    known_feeds = [
        ("arXiv CS.LG", "https://rss.arxiv.org/rss/cs.LG"),
        ("arXiv CS.CV", "https://rss.arxiv.org/rss/cs.CV"),
        ("The Gradient", "https://thegradient.pub/rss/"),
        ("Google AI Blog", "https://ai.googleblog.com/feeds/posts/default"),
        ("OpenAI Blog", "https://openai.com/blog/rss.xml"),
        ("Towards Data Science", "https://towardsdatascience.com/feed"),
        ("HuggingFace Blog", "https://huggingface.co/blog/feed.xml"),
        ("Machine Learning Mastery", "https://machinelearningmastery.com/feed/"),
        ("Analytics Vidhya", "https://www.analyticsvidhya.com/feed/"),
        ("KDnuggets", "https://www.kdnuggets.com/feed"),
    ]
    for name, url in known_feeds:
        if added >= slots:
            break
        if url in existing:
            continue
        if _rss_is_valid(url):
            sources.setdefault("rss", []).append({
                "url": url, "name": name, "score": 5.0,
                "uses": 0, "added_at": now_epoch(), "no_use_cycles": 0,
            })
            existing.add(url)
            _append_source_log({"timestamp": now_epoch(), "action": "discover",
                                 "type": "rss", "name": name, "url": url,
                                 "reason": "auto-discovered from known feed list"})
            log.info("Discovered RSS: %s", name)
            added += 1
    return added


def _discover_subreddits(sources: dict, topics: list[str], max_per_type: int) -> int:
    existing  = _existing_keys(sources)
    current   = len(sources.get("subreddits", []))
    slots     = max_per_type - current
    added     = 0
    candidates = [
        "MachineLearning", "artificial", "LocalLLaMA", "ChatGPT",
        "learnmachinelearning", "deeplearning", "datascience",
        "mlops", "reinforcementlearning", "computervision",
        "LanguageModels", "singularity", "AIPromptProgramming",
    ]
    for name in candidates:
        if added >= slots:
            break
        if name in existing:
            continue
        subs = _subreddit_subscribers(name)
        if subs >= 10_000:
            sources.setdefault("subreddits", []).append({
                "name": name, "score": 5.0, "uses": 0, "added_at": now_epoch(),
            })
            existing.add(name)
            _append_source_log({"timestamp": now_epoch(), "action": "discover",
                                 "type": "subreddit", "name": name,
                                 "reason": f"discovered, {subs} subscribers"})
            log.info("Discovered subreddit: r/%s (%d subs)", name, subs)
            added += 1
            time.sleep(1.5)   # be polite to Reddit
    return added


def _discover_youtube(sources: dict, topics: list[str], max_per_type: int) -> int:
    existing  = _existing_keys(sources)
    current   = len(sources.get("youtube_channels", []))
    slots     = max_per_type - current
    added     = 0
    candidates = [
        ("Lex Fridman",        "UCSHZKyawb77ixDdsGog4iWA"),
        ("Andrej Karpathy",    "UCbmNph6atAoGfqLoCL_duAg"),  # note: may be inactive
        ("3Blue1Brown",        "UCYO_jab_esuFRV4b17AJtAw"),
        ("Sentdex",            "UCfzlCWGWYyIQ0aLC5w48gBQ"),
        ("StatQuest",          "UCtYLUTtgS3k1Fg4y5tAhLbw"),
        ("The AI Epiphany",    "UCj8shE7aIn4Yawwbo2FceCQ"),
        ("Aleksa Gordic",      "UCv83Jcv_Rzo_GvJgJHkSJhQ"),
        ("AI Coffee Break",    "UCobqgqE4i5oyU7R1-9dq2wA"),
    ]
    for name, cid in candidates:
        if added >= slots:
            break
        if cid in existing:
            continue
        if _youtube_rss_is_valid(cid):
            sources.setdefault("youtube_channels", []).append({
                "id": cid, "name": name, "score": 5.0,
                "uses": 0, "added_at": now_epoch(),
            })
            existing.add(cid)
            _append_source_log({"timestamp": now_epoch(), "action": "discover",
                                 "type": "youtube", "name": name, "id": cid,
                                 "reason": "auto-discovered from known channel list"})
            log.info("Discovered YouTube: %s", name)
            added += 1
    return added
