#!/bin/bash
# setup.sh — one-time Mac setup for the Instagram bot
# Run once from the project directory: bash setup.sh

set -e
echo "🤖 Instagram Bot — Mac Setup"
echo "=============================="

# Python version check
python3 --version &>/dev/null || { echo "❌ Python 3 not found. Install via https://python.org"; exit 1; }

# Virtual environment
if [ ! -d ".venv" ]; then
  echo "📦 Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# Dependencies
echo "📥 Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# Playwright browsers
echo "🌐 Installing Playwright Chrome..."
playwright install chrome

# Directories
mkdir -p logs drafts chrome-profile

# .env file
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "⚠️  Created .env — please fill in your keys:"
  echo "    GEMINI_API_KEY=..."
  echo "    DISCORD_WEBHOOK_URL=..."
  echo ""
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Fill in .env with your Gemini API key and Discord webhook"
echo "  2. Log into Instagram once manually:"
echo "     source .venv/bin/activate"
echo "     python - <<'EOF'"
echo "     from playwright.sync_api import sync_playwright"
echo "     with sync_playwright() as p:"
echo "         ctx = p.chromium.launch_persistent_context('./chrome-profile', channel='chrome', headless=False)"
echo "         input('Log into Instagram, then press Enter here...')"
echo "         ctx.close()"
echo "     EOF"
echo ""
echo "  3. Start the bot:"
echo "     python scheduler.py"
echo ""
echo "  4. To keep it running 24/7 (background):"
echo "     nohup python scheduler.py > logs/scheduler.log 2>&1 &"
echo "     echo \$! > bot.pid   # saves the process ID"
echo ""
echo "  5. To stop it:"
echo "     kill \$(cat bot.pid)"
