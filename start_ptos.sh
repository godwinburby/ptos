#!/bin/bash
# PTOS Web Server Start Script
# Works with Termux Widget - one-tap start
#
# This script:
# - Checks for updates (git pull) on every run
# - Kills any existing server on port 5000
# - Starts fresh server + opens browser

set -e

PTOS_DIR="$HOME/storage/shared/ptos"
cd "$PTOS_DIR"

echo "=========================================="
echo "  PTOS Web"
echo "=========================================="
echo ""

# Check if PTOS is installed
if [ ! -d "$PTOS_DIR" ]; then
    echo "❌ PTOS is not installed."
    echo ""
    echo "Run setup_ptos.sh first to install PTOS."
    exit 1
fi

# Always check for updates
echo "📥 Checking for updates..."
cd "$PTOS_DIR"
git pull

echo ""
echo "✅ PTOS is up to date!"
echo ""

# Kill any existing server on port 5000
echo "🔄 Stopping any existing server..."
pkill -f "python.*ptos_web.py" 2>/dev/null || true
sleep 1

echo "🚀 Starting PTOS Web Server..."
echo ""
echo "Open in browser: http://localhost:5000"
echo ""

# Open browser (non-blocking)
am start -a android.intent.action.VIEW -d http://localhost:5000 &

# Start server (terminal stays visible)
python ptos_web.py
