"""
skills/discord_notify.py — send messages to Discord via webhook.
"""
import requests
from config import DISCORD_WEBHOOK_URL
from utils import get_logger, sleep_human

log = get_logger("discord")


def notify(message: str, embed: dict = None) -> bool:
    """
    Send a message (and optional embed) to the configured Discord channel.
    Retries up to 3 times with 2-second backoff.
    Returns True on success.
    """
    url = DISCORD_WEBHOOK_URL
    if not url:
        log.warning("DISCORD_WEBHOOK_URL not set — skipping notification.")
        return False

    payload = {"content": message}
    if embed:
        payload["embeds"] = [embed]

    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if 200 <= r.status_code < 205:
                return True
            log.warning("Discord returned %s (attempt %d)", r.status_code, attempt + 1)
        except requests.RequestException as e:
            log.warning("Discord request error (attempt %d): %s", attempt + 1, e)
        sleep_human(2000, 2000)

    log.error("Discord notification failed after 3 attempts.")
    return False
