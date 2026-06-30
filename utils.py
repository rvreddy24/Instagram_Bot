"""
utils.py — shared helpers: logging, human-like delays, typing simulation.
"""
from __future__ import annotations  # Python 3.9 compatible type hints

import logging
import random
import re
import time
from typing import Optional
from pathlib import Path
from config import LOGS_DIR

# ── Logger ────────────────────────────────────────────────────────────────────
def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)
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


def ist_hour(epoch: Optional[int] = None) -> int:
    """Return current hour in IST (UTC+5:30)."""
    ts = epoch or now_epoch()
    ist_epoch = ts + 5 * 3600 + 30 * 60
    return (ist_epoch // 3600) % 24


def utc_hour(epoch: Optional[int] = None) -> int:
    ts = epoch or now_epoch()
    return (ts // 3600) % 24


# ── Browser helpers ───────────────────────────────────────────────────────────
def human_type(page, selector: str, text: str) -> None:
    """Type text into a Playwright element with random per-character delays."""
    page.click(selector)
    for char in text:
        page.keyboard.type(char, delay=random.uniform(40, 120))
        if random.random() < 0.08:
            time.sleep(random.uniform(0.15, 0.45))
        if random.random() < 0.04:
            page.keyboard.type(random.choice("abcdefghijklmnopqrstuvwxyz"))
            time.sleep(0.08)
            page.keyboard.press("Backspace")


def scroll_page(page, pixels: Optional[int] = None) -> None:
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


def inject_stealth(page) -> None:
    """
    Patch common bot-detection fingerprints.
    Call once after opening a new page.
    """
    page.add_init_script("""
        // Remove webdriver flag
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

        // Fake realistic plugins list
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        // Fake language
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });

        // Fake Chrome runtime
        window.chrome = { runtime: {} };

        // Pass permissions query
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) =>
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters);
    """)


# ── Slug helper ───────────────────────────────────────────────────────────────
def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", text.lower().replace(" ", "_"))
