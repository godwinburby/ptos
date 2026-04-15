#!/bin/bash
# PTOS Start Script for Android (Termux)

PTOS_DIR="$HOME/storage/shared/ptos"

echo "=========================================="
echo "  PTOS Web"
echo "=========================================="
echo ""

if [ ! -d "$PTOS_DIR" ]; then
    echo "ERROR: PTOS not installed."
    echo "Run setup_ptos_android.sh first."
    exit 1
fi

cd "$PTOS_DIR"

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
    echo "ERROR: Python 3.11+ required. Run:  pkg install python"
    exit 1
fi

# Stop any existing server
pkill -f "python.*ptos_web.py" 2>/dev/null || true
sleep 1

echo "Starting PTOS Web Server..."
echo "Open in browser: http://localhost:5000"
echo ""

# Open browser (non-blocking, ignore failure)
am start -a android.intent.action.VIEW -d http://localhost:5000 >/dev/null 2>&1 &

# Start server in foreground
"$PYTHON" ptos_web.py
