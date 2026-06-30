"""
utils.py — shared helpers: logging, human-like delays, typing simulation.
"""
import logging
import random
import time
from pathlib import Path
from config import LOGS_DIR

# ── Logger ────────────────────────────────────────────────────────────────────
def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")
        # Console
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)
        # File
        fh = logging.FileHandler(LOGS_DIR / "bot.log", encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


# ── Timing helpers ────────────────────────────────────────────────────────────
def sleep_human(min_ms: int = 500, max_ms: int = 2000) -> None:
    """Sleep for a random human-like duration."""
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def now_epoch() -> int:
    return int(time.time())


def ist_hour(epoch: int | None = None) -> int:
    """Return current hour in IST (UTC+5:30)."""
    ts = epoch or now_epoch()
    ist_epoch = ts + 5 * 3600 + 30 * 60
    return (ist_epoch // 3600) % 24


def utc_hour(epoch: int | None = None) -> int:
    ts = epoch or now_epoch()
    return (ts // 3600) % 24


# ── Browser helpers ───────────────────────────────────────────────────────────
def human_type(page, selector: str, text: str) -> None:
    """Type text into a Playwright element with random per-character delays."""
    page.click(selector)
    for char in text:
        page.keyboard.type(char, delay=random.uniform(40, 120))
        if random.random() < 0.08:
            # occasional short think-pause
            time.sleep(random.uniform(0.15, 0.45))
        if random.random() < 0.04:
            # tiny typo + backspace
            page.keyboard.type(random.choice("abcdefghijklmnopqrstuvwxyz"))
            time.sleep(0.08)
            page.keyboard.press("Backspace")


def scroll_page(page, pixels: int = None) -> None:
    """Scroll down by a random or specified pixel amount."""
    amount = pixels or random.randint(250, 750)
    page.evaluate(f"window.scrollBy(0, {amount})")
    sleep_human(800, 1500)


def clear_non_essential_storage(page) -> None:
    """Clear caches and optionally localStorage without touching login cookies."""
    page.evaluate("""async () => {
        const keys = await caches.keys();
        await Promise.all(keys.map(k => caches.delete(k)));
        const regs = await navigator.serviceWorker.getRegistrations();
        await Promise.all(regs.map(r => r.unregister()));
        if (Math.random() < 0.2) localStorage.clear();
    }""")


# ── Slug helper ───────────────────────────────────────────────────────────────
def slugify(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9_]", "", text.lower().replace(" ", "_"))
