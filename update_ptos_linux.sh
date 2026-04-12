#!/bin/bash
# PTOS Update Script for Linux
# Pulls latest code via git. Run from the PTOS folder.

echo "=========================================="
echo "  PTOS Update"
echo "=========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "$SCRIPT_DIR/ptos_web.py" ]; then
    echo "ERROR: ptos_web.py not found in $SCRIPT_DIR"
    echo "Run setup_ptos_linux.sh first."
    exit 1
fi

cd "$SCRIPT_DIR"

if [ ! -d ".git" ]; then
    echo "ERROR: Not a git repository. Cannot update."
    echo "PTOS was not installed via git clone."
    exit 1
fi

# ── Stop Flask if running ─────────────────────────────────────────────────────
RUNNING=false
if pgrep -f "python.*ptos_web.py" > /dev/null 2>&1; then
    RUNNING=true
    echo "Stopping running server..."
    pkill -f "python.*ptos_web.py" 2>/dev/null || true
    sleep 1
fi

# ── Pull latest ───────────────────────────────────────────────────────────────
echo "Pulling latest changes from GitHub..."
git pull

echo ""
echo "=========================================="
echo "  PTOS Updated!"
echo "=========================================="
echo ""

if [ "$RUNNING" = true ]; then
    echo "Restarting server..."
    # Open browser and start server
    xdg-open http://localhost:5000 2>/dev/null &
    python3 ptos_web.py
fi
