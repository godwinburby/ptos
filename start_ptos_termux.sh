#!/bin/bash
# PTOS Web Server Start Script
# Starts the web server - no download/update

PTOS_DIR="$HOME/storage/shared/ptos"

echo "=========================================="
echo "  PTOS Web"
echo "=========================================="
echo ""

if [ ! -d "$PTOS_DIR" ]; then
    echo "=========================================="
    echo "  PTOS is not installed!"
    echo "=========================================="
    echo ""
    echo "Run setup_ptos_termux.sh first to install PTOS."
    exit 1
fi

cd "$PTOS_DIR"

echo "🚀 Starting PTOS Web Server..."
echo ""
echo "Open in browser: http://localhost:5000"
echo ""

# Kill any existing server
pkill -f "python.*ptos_web.py" 2>/dev/null || true
sleep 1

# Open browser (non-blocking)
am start -a android.intent.action.VIEW -d http://localhost:5000 > /dev/null 2>&1 &

# Start server (terminal stays visible)
python ptos_web.py
