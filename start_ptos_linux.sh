#!/bin/bash
# PTOS Start Script for Linux
# Starts the Flask web server

set -e

echo "=========================================="
echo "  PTOS Web Server"
echo "=========================================="
echo ""

# Get directory where script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check for ptos_web.py
if [ ! -f "$SCRIPT_DIR/ptos_web.py" ]; then
    echo "Error: ptos_web.py not found in $SCRIPT_DIR"
    echo "Make sure you're running this script from the PTOS directory."
    exit 1
fi

cd "$SCRIPT_DIR"

# Find Python
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "Error: Python not found."
    exit 1
fi

# Kill any existing process on port 5000
echo "Checking for existing server..."
if command -v lsof &>/dev/null; then
    PID=$(lsof -ti:5000 2>/dev/null)
    if [ -n "$PID" ]; then
        echo "Killing existing process $PID on port 5000..."
        kill -9 $PID 2>/dev/null || sudo kill -9 $PID 2>/dev/null || true
    fi
elif command -v fuser &>/dev/null; then
    fuser -k 5000/tcp 2>/dev/null || true
fi

# Also kill any existing ptos_web.py processes
pkill -f "python.*ptos_web.py" 2>/dev/null || true

echo ""
echo "Starting PTOS Web Server..."
echo ""
echo "Open in browser: http://localhost:5000"
echo "Press Ctrl+C to stop."
echo ""

# Open browser (non-blocking)
xdg-open http://localhost:5000 2>/dev/null &

# Start Flask server
$PYTHON ptos_web.py
