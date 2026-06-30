"""
skills/feed_engager.py — scroll the Instagram home feed, score posts using
brain's engagement criteria, and leave Gemini-written comments.
"""
import random
import re
import time

import google.generativeai as genai
from playwright.sync_api import sync_playwright

import state
from config import (
    CHROME_PROFILE_DIR, LOGS_DIR, USER_AGENTS, VIEWPORTS, HEADLESS,
    GEMINI_API_KEY, GEMINI_MODEL,
    DEFAULT_MAX_SCROLLS, DEFAULT_ENGAGE_PER_RUN,
)
from utils import get_logger, sleep_human, clear_non_essential_storage, scroll_page, now_epoch

log = get_logger("feed_engager")
genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel(GEMINI_MODEL)
IG_URL = "https://www.instagram.com/"

FALLBACK_COMMENTS = [
    "This is genuinely fascinating! 🔥",
    "Really insightful, thanks for sharing!",
    "Love seeing this kind of content 🙌",
    "Great perspective — definitely makes you think.",
    "This is exactly what I needed to see today!",
]


def run() -> dict:
    strategy = state.get("brain_strategy") or {}
    eng      = strategy.get("engagement", {})

    niche_kw    = [k.lower() for k in eng.get("niche_keywords", ["AI", "tech"])]
    comment_style = eng.get("comment_style", "ask a thoughtful follow-up question")
    like_thresh = eng.get("like_threshold_score", 2)
    story_prob  = eng.get("story_view_probability", 0.3)
    min_age_min = eng.get("min_post_age_minutes", 5)
    max_age_hrs = eng.get("max_post_age_hours", 6)

    max_scrolls     = int(state.get("ig_max_scrolls",    DEFAULT_MAX_SCROLLS))
    engage_per_run  = int(state.get("ig_engage_per_run", DEFAULT_ENGAGE_PER_RUN))

    ua       = random.choice(USER_AGENTS)
    viewport = random.choice(VIEWPORTS)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_PROFILE_DIR),
            channel="chrome",
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            user_agent=ua,
            viewport=viewport,
        )
        page = ctx.new_page()
        try:
            result = _engage(page, niche_kw, comment_style, like_thresh,
                             story_prob, min_age_min, max_age_hrs,
                             max_scrolls, engage_per_run)
        finally:
            ctx.close()
    return result


def _engage(page, niche_kw, comment_style, like_thresh,
            story_prob, min_age_min, max_age_hrs,
            max_scrolls, engage_per_run) -> dict:

    sleep_human(2000, 5000)
    page.goto(IG_URL, wait_until="domcontentloaded", timeout=30000)
    sleep_human(1000, 2000)
    clear_non_essential_storage(page)

    # Load seen posts from state
    seen_index: list[str] = state.get("ig_seen_index", [])
    if len(seen_index) > 500:
        seen_index = seen_index[-500:]
    seen_set = set(seen_index)

    candidates: list[dict] = []
    engaged_ids: set[str]  = set()
    comments_count = likes_count = story_views_count = 0
    retry_count    = 0

    for scroll_i in range(max_scrolls):
        scroll_page(page)

        # Parse articles
        articles = page.query_selector_all("article")
        for article in articles:
            try:
                post_id = _extract_id(article)
                if not post_id or post_id in seen_set or post_id in engaged_ids:
                    continue

                # Skip ads
                if article.query_selector("[aria-label='Sponsored']"):
                    continue

                age_min = _extract_age_minutes(article)
                if age_min is None:
                    continue
                if age_min < min_age_min or age_min > max_age_hrs * 60:
                    continue

                preview  = _extract_preview(article)
                is_following = _is_following(article)
                score    = _score_post(preview, age_min, niche_kw, is_following)

                if score >= like_thresh:
                    candidates.append({
                        "id": post_id, "score": score,
                        "preview": preview, "article": article,
                        "author": _extract_author(article),
                    })
            except Exception:
                pass

    # Sort by score and engage top N
    candidates.sort(key=lambda x: x["score"], reverse=True)
    state.set("ig_last_candidates", [
        {"id": c["id"], "author": c["author"], "score": c["score"]}
        for c in candidates[:10]
    ])

    for cand in candidates[:engage_per_run]:
        if _check_rate_limit(page):
            wait = 60 * (2 ** retry_count)
            log.warning("Rate limit — waiting %d s", wait)
            time.sleep(wait)
            page.reload()
            sleep_human(2000, 3000)
            retry_count += 1
            if retry_count >= 5:
                break
            continue

        try:
            post_link = cand["article"].query_selector("a[href*='/p/']")
            if not post_link:
                continue
            post_link.click()
            sleep_human(1500, 3000)

            # Gemini comment
            comment = _generate_comment(cand["preview"], comment_style)

            # Type comment
            comment_box = page.wait_for_selector(
                "[aria-label='Add a comment…'], [placeholder='Add a comment…']",
                timeout=6000,
            )
            comment_box.click()
            sleep_human(300, 700)
            for ch in comment:
                page.keyboard.type(ch, delay=random.uniform(40, 110))
                if random.random() < 0.08:
                    sleep_human(150, 400)
                if random.random() < 0.04:
                    page.keyboard.type(random.choice("abcde"))
                    sleep_human(60, 100)
                    page.keyboard.press("Backspace")
            page.keyboard.press("Enter")
            comments_count += 1
            sleep_human(1000, 2000)

            # Like
            like_btn = page.query_selector("[aria-label='Like'], [aria-label^='Like']")
            if like_btn:
                like_btn.click()
                likes_count += 1
            sleep_human(500, 1200)

            # Story (probabilistic)
            if random.random() < story_prob:
                story_views_count += _view_story(page, cand["author"])

            # Mark seen
            engaged_ids.add(cand["id"])
            seen_index.append(cand["id"])
            seen_set.add(cand["id"])

            # Close modal and continue
            page.keyboard.press("Escape")
            sleep_human(3000, 7000)

        except Exception as e:
            log.warning("Engagement error for post %s: %s", cand["id"], e)
            page.keyboard.press("Escape")
            sleep_human(1000, 2000)

    # Persist seen index (cap at 500)
    state.set("ig_seen_index", seen_index[-500:])
    state.set("ig_engage_retry", 0)

    engagement = likes_count + comments_count
    log.info("Engagement done: %d comments, %d likes, %d story views",
             comments_count, likes_count, story_views_count)
    return {
        "status": "ok",
        "comments": comments_count, "likes": likes_count,
        "story_views": story_views_count,
        "engagement": engagement,
        "candidates_considered": len(candidates),
    }


def _generate_comment(preview: str, style: str) -> str:
    try:
        prompt = (f"Write a comment for this Instagram post.\n"
                  f"Post preview: {preview[:300]}\n"
                  f"Style instruction: {style}\n"
                  f"Max 120 characters. No hashtags. Sound like a real person.\n"
                  f"Return ONLY the comment text.")
        resp = _model.generate_content(prompt)
        return resp.text.strip()[:120]
    except Exception:
        return random.choice(FALLBACK_COMMENTS)


def _score_post(preview: str, age_min: int, keywords: list[str], is_following: bool) -> int:
    score = 0
    if age_min < 30:
        score += 2
    elif age_min < 120:
        score += 1
    lower = preview.lower()
    if any(k in lower for k in keywords):
        score += 2
    if is_following:
        score += 2
    return score


def _view_story(page, author: str) -> int:
    try:
        page.goto(f"https://www.instagram.com/{author}/", timeout=10000)
        sleep_human(1000, 2000)
        ring = page.query_selector("canvas, [aria-label*='story'], [role='button'] > div > canvas")
        if ring:
            ring.click()
            sleep_human(3000, 5000)
            page.goto("https://www.instagram.com/", timeout=10000)
            return 1
    except Exception:
        pass
    return 0


def _extract_id(article) -> str | None:
    link = article.query_selector("a[href*='/p/']")
    if link:
        href = link.get_attribute("href") or ""
        m    = re.search(r"/p/([\w-]+)/", href)
        if m:
            return m.group(1)
    return None


def _extract_age_minutes(article) -> int | None:
    el = article.query_selector("time")
    if not el:
        return None
    dt_str = el.get_attribute("datetime") or ""
    try:
        from datetime import datetime, timezone
        dt  = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - dt
        return int(age.total_seconds() / 60)
    except Exception:
        return None


def _extract_preview(article) -> str:
    el = article.query_selector("span, div[class*='caption']")
    return (el.inner_text() or "")[:300] if el else ""


def _extract_author(article) -> str:
    link = article.query_selector("a[role='link']")
    if link:
        href = link.get_attribute("href") or ""
        return href.strip("/").split("/")[0]
    return ""


def _is_following(article) -> bool:
    for el in article.query_selector_all("button, span"):
        if "Following" in (el.inner_text() or ""):
            return True
    return False


def _check_rate_limit(page) -> bool:
    content = page.content() or ""
    return any(p in content for p in
               ["Please wait a few minutes", "Try again later", "Action Blocked"])
