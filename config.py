import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# ── Paths ────────────────────────────────────────────────────────────────────
STATE_FILE          = BASE_DIR / "state.json"
LOGS_DIR            = BASE_DIR / "logs"
DRAFTS_DIR          = BASE_DIR / "drafts"
CHROME_PROFILE_DIR  = BASE_DIR / "chrome-profile"
PERF_LOG            = LOGS_DIR / "performance.jsonl"
BRAIN_NOTES_LOG     = LOGS_DIR / "brain_notes.jsonl"
AUDIT_LOG           = LOGS_DIR / "audit_log.jsonl"
SOURCE_LOG          = LOGS_DIR / "source_log.jsonl"
FOLLOW_LOG          = LOGS_DIR / "follow_log.jsonl"

# Create required directories on import
for d in [LOGS_DIR, DRAFTS_DIR, CHROME_PROFILE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Secrets ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL        = "gemini-1.5-pro"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# ── Brain settings ───────────────────────────────────────────────────────────
MAX_PERF_ROWS       = 30   # how many recent rows fed to Gemini
DEEP_AUDIT_EVERY    = 7    # cycles between deep audits

# ── Source management ────────────────────────────────────────────────────────
MIN_USES_TO_SCORE            = 3
DISCOVERY_TRIGGER_THRESHOLD  = 5
MAX_SOURCES_PER_TYPE         = 10

# ── Engagement defaults (overridden by brain strategy) ───────────────────────
DEFAULT_MAX_SCROLLS     = 6
DEFAULT_ENGAGE_PER_RUN  = 3

# ── Browser ──────────────────────────────────────────────────────────────────
# Set HEADLESS=true in .env to run without a visible window.
# Instagram detection is lower with headless=False, but headless=True
# works fine on a headless server if you also set --disable-blink-features.
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

VIEWPORTS = [
    {"width": 1280, "height": 800},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1920, "height": 1080},
]
