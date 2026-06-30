"""
skills/follow_manager.py — brain-driven follow/unfollow using Playwright.
Reads target_niches, min_followers, max_following_ratio from brain strategy.
Logs all actions to ./logs/follow_log.jsonl.

Uses Playwright's managed Chromium (no system Chrome required).
"""
from __future__ import annotations

import json
import random
import re
import time
from typing import Optional

from playwright.sync_api import sync_playwright

import state
from config import CHROME_PROFILE_DIR, FOLLOW_LOG, USER_AGENTS, VIEWPORTS, HEADLESS
from utils import get_logger, sleep_human, now_epoch

log = get_logger("follow_manager")
IG_URL = "https://www.instagram.com/"


def run() -> dict:
    strategy = state.get("brain_strategy") or {}
    follow   = strategy.get("follow", {})

    if not strategy:
        return {"status": "error", "message": "Brain strategy not found — run brain(pre) first"}

    target_niches      = [n.lower() for n in follow.get("target_niches", ["AI", "tech"])]
    min_followers      = follow.get("min_followers", 500)
    max_following_ratio= follow.get("max_following_ratio", 2.0)
    unfollow_days      = follow.get("unfollow_after_days", 14)
    follows_per_run    = follow.get("follows_per_run", 3)

    ua       = random.choice(USER_AGENTS)
    viewport = random.choice(VIEWPORTS)

    _STEALTH_ARGS = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-background-timer-throttling",
    ]

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_PROFILE_DIR),
            headless=HEADLESS,
            args=_STEALTH_ARGS,
            user_agent=ua,
            viewport=viewport,
            locale="en-US",
            timezone_id="Asia/Kolkata",
            device_scale_factor=2.0,
        )
        page = ctx.new_page()
        from utils import inject_stealth
        inject_stealth(page)
        try:
            result = _manage_follows(page, target_niches, min_followers,
                                     max_following_ratio, unfollow_days, follows_per_run)
        finally:
            ctx.close()
    return result


def _manage_follows(page, target_niches, min_followers,
                    max_following_ratio, unfollow_days, follows_per_run) -> dict:
    now = now_epoch()

    # ── Load state ────────────────────────────────────────────────────────────
    following_log: list[dict] = state.get("following_log") or []
    follow_declined: set[str] = set(state.get("ig_follow_declined") or [])
    already_following: set[str] = {e["account"] for e in following_log}

    # ── Unfollow stale ────────────────────────────────────────────────────────
    unfollowed = 0
    to_unfollow = [
        e for e in following_log
        if not e.get("followed_back", False)
        and (now - e.get("followed_at_epoch", now)) / 86400 >= unfollow_days
    ]

    sleep_human(2000, 5000)
    page.goto(IG_URL, wait_until="domcontentloaded", timeout=30000)

    for entry in to_unfollow:
        account = entry["account"]
        try:
            page.goto(f"https://www.instagram.com/{account}/", timeout=12000)
            sleep_human(1000, 2500)
            btn = page.query_selector("[aria-label*='Following'], button:has-text('Following')")
            if btn:
                btn.click()
                sleep_human(500, 1000)
                confirm = page.query_selector("button:has-text('Unfollow')")
                if confirm:
                    confirm.click()
                    sleep_human(2000, 4000)
                    following_log = [e for e in following_log if e["account"] != account]
                    already_following.discard(account)
                    _log_action("unfollow", account)
                    unfollowed += 1
        except Exception as e:
            log.warning("Unfollow %s failed: %s", account, e)

    # ── Check follow-backs ────────────────────────────────────────────────────
    check_list = [e for e in following_log
                  if not e.get("followed_back", False)
                  and (now - e.get("followed_at_epoch", now)) / 86400 < unfollow_days][:10]

    for entry in check_list:
        account = entry["account"]
        try:
            page.goto(f"https://www.instagram.com/{account}/", timeout=12000)
            sleep_human(800, 1800)
            content = page.content()
            if "Message" in content:     # mutual follow → "Message" button visible
                entry["followed_back"] = True
        except Exception:
            pass

    # ── Find candidates from feed ─────────────────────────────────────────────
    page.goto(IG_URL, timeout=15000)
    sleep_human(1000, 2000)

    feed_candidates: set[str] = set()
    articles = page.query_selector_all("article")
    for article in articles[:10]:
        link = article.query_selector("a[role='link']")
        if link:
            href = link.get_attribute("href") or ""
            name = href.strip("/").split("/")[0]
            if name and name not in already_following:
                feed_candidates.add(name)

    # Also from last candidates stored by feed_engager
    for cand in (state.get("ig_last_candidates") or []):
        author = cand.get("author", "")
        if author and author not in already_following:
            feed_candidates.add(author)

    candidates = [c for c in feed_candidates if c not in follow_declined]

    # ── Qualify and follow ────────────────────────────────────────────────────
    followed        = 0
    candidates_checked = 0

    for account in list(candidates)[:15]:
        if followed >= follows_per_run:
            break
        if account in already_following:
            continue
        candidates_checked += 1

        try:
            page.goto(f"https://www.instagram.com/{account}/", timeout=12000)
            sleep_human(800, 2000)

            fcount, fing = _scrape_stats(page)
            if fcount == 0:
                follow_declined.add(account)
                continue

            ratio = fing / max(fcount, 1)
            bio   = _get_bio(page).lower()

            qualifies = (
                fcount >= min_followers
                and ratio <= max_following_ratio
                and any(niche in bio for niche in target_niches)
            )

            if not qualifies:
                follow_declined.add(account)
                continue

            # Follow
            follow_btn = page.query_selector(
                "button:has-text('Follow'):not(:has-text('Following'))"
            )
            if follow_btn:
                sleep_human(500, 1500)
                follow_btn.click()
                sleep_human(3000, 7000)
                following_log.append({
                    "account": account,
                    "followed_at_epoch": now_epoch(),
                    "followed_back": False,
                    "followers": fcount,
                    "following_ratio": round(ratio, 2),
                })
                already_following.add(account)
                _log_action("follow", account, fcount, ratio)
                followed += 1
                log.info("Followed: @%s (%d followers)", account, fcount)
        except Exception as e:
            log.warning("Follow check for %s failed: %s", account, e)

    # ── Persist ───────────────────────────────────────────────────────────────
    state.update({
        "following_log":        following_log,
        "ig_follow_declined":   list(follow_declined)[-300:],
    })

    follow_back_rate = _calc_follow_back_rate(following_log)
    log.info("Follow manager done: +%d followed, -%d unfollowed, follow-back=%.1f%%",
             followed, unfollowed, follow_back_rate * 100)

    return {
        "status":            "ok",
        "followed":          followed,
        "unfollowed":        unfollowed,
        "candidates_checked": candidates_checked,
        "follow_back_rate":  follow_back_rate,
    }


def _scrape_stats(page) -> tuple[int, int]:
    followers = following = 0
    try:
        stats = page.query_selector_all("li span span")
        texts = [el.inner_text().replace(",", "").strip() for el in stats]
        nums  = []
        for t in texts:
            try:
                if "K" in t:
                    nums.append(int(float(t.replace("K", "")) * 1000))
                elif "M" in t:
                    nums.append(int(float(t.replace("M", "")) * 1_000_000))
                else:
                    nums.append(int(t))
            except Exception:
                pass
        if len(nums) >= 2:
            followers, following = nums[0], nums[1]
    except Exception:
        pass
    return followers, following


def _get_bio(page) -> str:
    try:
        el = page.query_selector("div.-vDIg, section div > span, div[class*='bio']")
        return el.inner_text() if el else ""
    except Exception:
        return ""


def _log_action(action: str, account: str, followers: int = 0, ratio: float = 0.0) -> None:
    record = {
        "timestamp": now_epoch(), "action": action, "account": account,
        "followers": followers, "following_ratio": round(ratio, 2),
    }
    with open(FOLLOW_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _calc_follow_back_rate(log_entries: list[dict]) -> float:
    checked = [e for e in log_entries if e.get("followed_back") is not None]
    if not checked:
        return 0.0
    return round(sum(1 for e in checked if e["followed_back"]) / len(checked), 3)
