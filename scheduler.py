"""
scheduler.py — runs main.py on a repeating schedule based on the brain's
posting.frequency_hours value, which updates every cycle automatically.

Usage:
    python scheduler.py            # Runs immediately then on schedule
    python scheduler.py --dry-run  # Prints next run time without executing
"""
import sys
import time
import logging
import schedule

import state
from utils import get_logger

log = get_logger("scheduler")


def _get_interval_hours() -> int:
    strategy = state.get("brain_strategy") or {}
    hours    = strategy.get("posting", {}).get("frequency_hours", 8)
    return max(4, min(24, int(hours)))   # clamp 4–24 h


def _run_job():
    log.info("Scheduler firing — starting cycle.")
    try:
        from main import run_cycle
        result = run_cycle()
        log.info("Cycle result: %s", result.get("status"))
    except Exception as e:
        log.error("Cycle crashed: %s", e, exc_info=True)
        try:
            from skills.discord_notify import notify
            notify(f"🔴 Scheduler: cycle crashed — {e}")
        except Exception:
            pass

    # Re-schedule next run based on (potentially updated) strategy
    interval = _get_interval_hours()
    log.info("Next cycle in %d hours.", interval)
    schedule.clear("main_job")
    schedule.every(interval).hours.do(_run_job).tag("main_job")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        interval = _get_interval_hours()
        log.info("Dry-run mode. Would run every %d hours. Exiting.", interval)
        sys.exit(0)

    log.info("Instagram bot scheduler starting.")
    log.info("Running first cycle immediately...")
    _run_job()

    log.info("Scheduler loop running. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(30)
