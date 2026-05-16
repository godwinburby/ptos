#!/bin/bash
# PTOS Start Script for Linux
# Run from the PTOS folder: ./start_ptos_linux.sh
# Automatically updates from git if available, then starts the server.

echo "=========================================="
echo "  PTOS Web Server"
echo "=========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "$SCRIPT_DIR/ptos_web.py" ]; then
    echo "ERROR: ptos_web.py not found in $SCRIPT_DIR"
    echo "Run setup_ptos_linux.sh first."
    exit 1
fi

cd "$SCRIPT_DIR"

# ── Find Python 3.11+ ─────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.11+ not found. Run setup_ptos_linux.sh first."
    exit 1
fi

# ── Check for updates (if git repo) ───────────────────────────────────────────
if [ -d ".git" ]; then
    echo "Checking for updates..."
    if git pull --ff-only 2>&1; then
        echo "Updated."
    else
        echo "Warning: git pull failed. Continuing with local version."
    fi
else
    echo "Not a git repo - skipping update check."
fi

# ── Check/install dependencies ────────────────────────────────────────────────
if ! $PYTHON -c "import flask" 2>/dev/null; then
    echo "Installing Flask and tomli-w..."
    $PYTHON -m pip install flask tomli-w pytest --break-system-packages --quiet
fi

# ── Kill any existing PTOS server ────────────────────────────────────────────
echo ""
echo "Checking for existing server..."
pkill -f "python.*ptos_web.py" 2>/dev/null || true

if command -v lsof &>/dev/null; then
    PID=$(lsof -ti:5000 2>/dev/null || true)
    if [ -n "$PID" ]; then
        echo "Stopping process on port 5000 (PID $PID)..."
        kill "$PID" 2>/dev/null || kill -9 "$PID" 2>/dev/null || true
        sleep 1
    fi
elif command -v fuser &>/dev/null; then
    fuser -k 5000/tcp 2>/dev/null || true
    sleep 1
fi

# ── Start Flask, then open browser ───────────────────────────────────────────
echo ""
echo "Starting PTOS..."
echo "Open in browser: http://localhost:5000"
echo "Press Ctrl+C to stop."
echo ""

$PYTHON ptos_web.py &
FLASK_PID=$!

# Wait for Flask to be ready (up to 15s)
echo "Waiting for server..."
for i in $(seq 1 15); do
    if curl -sf http://localhost:5000 >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

xdg-open http://localhost:5000 2>/dev/null || true
wait $FLASK_PID
