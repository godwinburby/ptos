#!/bin/bash
# PTOS Web Server Start Script
# Works with Termux Widget - one-tap start
#
# If server already running: opens browser
# If not running: starts server + opens browser

set -e

PTOS_DIR="$HOME/storage/shared/ptos"
cd "$PTOS_DIR"

echo "=========================================="
echo "  PTOS Web"
echo "=========================================="
echo ""

# Check if server is already running on port 5000
if curl -s --connect-timeout 2 http://localhost:5000 > /dev/null 2>&1; then
    echo "🌐 PTOS Web is already running!"
    echo ""
    echo "Opening browser..."
    am start -a android.intent.action.VIEW -d http://localhost:5000
else
    echo "🚀 Starting PTOS Web Server..."
    echo ""
    echo "Open in browser: http://localhost:5000"
    echo ""
    
    # Open browser (non-blocking)
    am start -a android.intent.action.VIEW -d http://localhost:5000 &
    
    # Start server (terminal stays visible)
    python ptos_web.py
fi
