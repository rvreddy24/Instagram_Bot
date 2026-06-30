"""
skills/stealth_post.py — upload a post to Instagram using Playwright
with human-like timing, UA rotation, and exponential back-off.
"""
import random
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from config import CHROME_PROFILE_DIR, LOGS_DIR, USER_AGENTS, VIEWPORTS, HEADLESS
from utils import get_logger, sleep_human, human_type, clear_non_essential_storage, now_epoch
import state

log = get_logger("stealth_post")
IG_URL = "https://www.instagram.com/"


def run(draft_path: str) -> dict:
    # ── Read draft ────────────────────────────────────────────────────────────
    text = Path(draft_path).read_text(encoding="utf-8")
    fm   = _parse_fm(text)
    media_path = fm.get("media", "")
    caption    = fm.get("caption", "")

    if not media_path or not Path(media_path).exists():
        return {"status": "error", "message": f"Media file not found: {media_path}"}
    if Path(media_path).stat().st_size > 30 * 1024 * 1024:
        return {"status": "error", "message": "Media file exceeds 30 MB limit"}

    ua       = random.choice(USER_AGENTS)
    viewport = random.choice(VIEWPORTS)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_PROFILE_DIR),
            channel="chrome",
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-background-timer-throttling",
            ],
            user_agent=ua,
            viewport=viewport,
            locale="en-US",
        )
        page = ctx.new_page()

        try:
            result = _post(page, media_path, caption)
        finally:
            ctx.close()

    return result


def _post(page, media_path: str, caption: str) -> dict:
    retry_count = state.get("ig_post_retry", 0)
    max_retries = 5

    # Warm-up
    sleep_human(3000, 8000)
    page.goto(IG_URL, wait_until="domcontentloaded", timeout=30000)
    sleep_human(1500, 3000)
    clear_non_essential_storage(page)

    # Session check
    if _is_login_wall(page):
        return {"status": "error",
                "message": "Session expired — log into Instagram once with "
                           "./chrome-profile and restart."}

    for attempt in range(max_retries):
        try:
            # Navigate to upload dialog
            sleep_human(500, 1500)
            _click_create(page)

            # File upload
            sleep_human(500, 1200)
            with page.expect_file_chooser() as fc_info:
                page.click("[aria-label='Select from computer'], "
                           "button:has-text('Select from computer')")
            fc_info.value.set_files(media_path)
            sleep_human(2000, 4000)

            # Proceed through any crop/filter/trim screens
            for _ in range(4):
                next_btn = page.query_selector("button:has-text('Next')")
                if next_btn:
                    next_btn.click()
                    sleep_human(1000, 2500)

            # Caption
            cap_box = page.wait_for_selector(
                "[aria-label='Write a caption…'], "
                "[aria-label='Write a caption'], "
                "div[role='textbox']",
                timeout=10000,
            )
            cap_box.click()
            sleep_human(300, 700)
            _type_caption(page, caption)

            # Share
            sleep_human(300, 900)
            share_btn = page.wait_for_selector(
                "[aria-label='Share'], button:has-text('Share')", timeout=8000)
            share_btn.click()

            # Confirm
            post_id = _wait_for_success(page)
            ts      = now_epoch()
            shot    = str(LOGS_DIR / f"{ts}_post.png")
            page.screenshot(path=shot)
            state.set("ig_post_retry", 0)
            log.info("Posted successfully. post_id=%s", post_id)
            return {"status": "ok", "timestamp": ts,
                    "screenshot": shot, "post_id": post_id}

        except Exception as e:
            log.warning("Post attempt %d failed: %s", attempt + 1, e)
            if _check_rate_limit(page):
                wait = 60 * (2 ** retry_count)
                log.warning("Rate limit detected. Waiting %d s.", wait)
                state.set("ig_post_retry", retry_count + 1)
                time.sleep(wait)
                page.reload()
                retry_count += 1
            else:
                ts  = now_epoch()
                shot = str(LOGS_DIR / f"{ts}_post_error.png")
                page.screenshot(path=shot)
                return {"status": "error", "message": str(e), "screenshot": shot}

    state.set("ig_post_retry", 0)
    return {"status": "error", "message": "Max retries exceeded after rate limits"}


def _click_create(page) -> None:
    selectors = [
        "a[href='/create/style/']",
        "[aria-label='New post']",
        "svg[aria-label='New post']",
    ]
    for sel in selectors:
        el = page.query_selector(sel)
        if el:
            el.click()
            sleep_human(800, 1500)
            return
    # Fallback: find by text
    page.get_by_text("Create").first.click()
    sleep_human(800, 1500)


def _type_caption(page, caption: str) -> None:
    words = caption.split(" ")
    for i, word in enumerate(words):
        page.keyboard.type(word, delay=random.uniform(40, 110))
        if i < len(words) - 1:
            page.keyboard.type(" ", delay=random.uniform(30, 80))
        if random.random() < 0.12:
            sleep_human(150, 450)
        if random.random() < 0.04:
            page.keyboard.type("x")
            sleep_human(80, 120)
            page.keyboard.press("Backspace")


def _wait_for_success(page) -> str:
    for _ in range(40):
        if "Your post has been shared" in (page.content() or ""):
            break
        hrefs = [a.get_attribute("href") or "" for a in page.query_selector_all("a")]
        for h in hrefs:
            m = re.search(r"/p/([\w-]+)/", h)
            if m:
                return m.group(1)
        sleep_human(500, 500)
    # Try URL
    url = page.url
    m   = re.search(r"/p/([\w-]+)/", url)
    return m.group(1) if m else "unknown"


def _check_rate_limit(page) -> bool:
    content = page.content() or ""
    return any(phrase in content for phrase in
               ["Please wait a few minutes", "Try again later", "Action Blocked"])


def _is_login_wall(page) -> bool:
    content = page.content() or ""
    return "Log in" in content and "username" in content.lower() and "password" in content.lower()


def _parse_fm(text: str) -> dict:
    fm: dict[str, str] = {}
    m = re.search(r"^---\n(.*?)\n---", text, re.DOTALL | re.MULTILINE)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip().strip('"')
    return fm
