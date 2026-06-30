#!/bin/bash
# setup.sh — one-time Mac setup for the Instagram bot
# Usage: bash setup.sh
set -e

echo "🤖 Instagram Bot — Mac Setup"
echo "================================"

# ── Python check ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 not found."
  echo "   Install via: brew install python  OR  https://python.org"
  exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Python $PYTHON_VERSION found."

if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)"; then
  echo "✅ Python version OK (3.9+)"
else
  echo "❌ Python 3.9+ required. Install a newer version."
  exit 1
fi

# ── Virtual environment ───────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "📦 Creating virtual environment..."
  python3 -m venv .venv
fi
echo "✅ Virtual environment ready."

source .venv/bin/activate

# ── Python dependencies ───────────────────────────────────────────────────────
echo "📥 Installing Python packages..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ Packages installed."

# ── Playwright Chromium ───────────────────────────────────────────────────────
# We use Playwright's managed Chromium — no system Chrome install needed.
echo "🌐 Installing Playwright Chromium..."
playwright install chromium
playwright install-deps chromium 2>/dev/null || true  # Linux only, no-op on Mac
echo "✅ Playwright Chromium installed."

# ── Runtime directories ───────────────────────────────────────────────────────
mkdir -p logs drafts chrome-profile
echo "✅ Directories ready."

# ── .env file ─────────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "⚠️  Created .env — fill in your keys before starting the bot:"
  echo "    GEMINI_API_KEY=your_key_here"
  echo "    DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/..."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Setup complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next steps:"
echo ""
echo "  1. Fill in .env with your Gemini API key and Discord webhook."
echo ""
echo "  2. Log into Instagram ONCE manually (saves session to chrome-profile/):"
echo ""
echo "     source .venv/bin/activate"
echo "     python3 - <<'PYEOF'"
echo "     from playwright.sync_api import sync_playwright"
echo "     with sync_playwright() as p:"
echo "         ctx = p.chromium.launch_persistent_context("
echo "             './chrome-profile', headless=False,"
echo "             args=['--disable-blink-features=AutomationControlled'])"
echo "         input('Log into Instagram in the browser window, then press Enter here...')"
echo "         ctx.close()"
echo "     PYEOF"
echo ""
echo "  3. Run one cycle manually to test:"
echo "     python3 main.py"
echo ""
echo "  4. Start the scheduler (runs every N hours based on brain strategy):"
echo "     python3 scheduler.py"
echo ""
echo "  5. Run 24/7 in the background:"
echo "     nohup python3 scheduler.py > logs/scheduler.log 2>&1 &"
echo "     echo \$! > bot.pid"
echo "     # To stop: kill \$(cat bot.pid)"
echo ""
echo "  Optional — add as a macOS Launch Agent for auto-start on login:"
echo "     See README for the launchd plist example."
echo ""
