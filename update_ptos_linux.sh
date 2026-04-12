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

# ── Pull latest first ────────────────────────────────────────────────────────
echo "Pulling latest changes from GitHub..."
git pull

# ── Update .version file with new SHA ────────────────────────────────────────
NEW_SHA=$(git rev-parse HEAD 2>/dev/null)
if [ -n "$NEW_SHA" ]; then
    echo "$NEW_SHA" > .version
    echo "Updated version to: ${NEW_SHA:0:8}"
fi

echo ""
echo "=========================================="
echo "  PTOS Updated!"
echo "=========================================="
echo ""

# ── Restart server (background this process first) ───────────────────────────
# Use double-fork: background a subshell that kills port 5000 and restarts
# This allows the main script to exit cleanly so Flask can return a response
(
    sleep 1
    echo "Stopping server on port 5000..."
    if command -v lsof &>/dev/null; then
        PIDS=$(lsof -ti:5000 2>/dev/null)
        if [ -n "$PIDS" ]; then
            echo "$PIDS" | xargs kill -9 2>/dev/null || true
        fi
    elif command -v fuser &>/dev/null; then
        fuser -k 5000/tcp 2>/dev/null || true
    fi
    sleep 1
    echo "Starting server..."
    cd "$SCRIPT_DIR"
    xdg-open http://localhost:5000 2>/dev/null &
    nohup python3 ptos_web.py > /dev/null 2>&1 &
) &
disown
