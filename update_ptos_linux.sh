#!/bin/bash
# PTOS Update Script for Linux
# Git pull to update PTOS

set -e

echo "=========================================="
echo "  PTOS Update"
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

# Check if it's a git repo
if [ ! -d ".git" ]; then
    echo "Error: Not a git repository."
    echo "PTOS was not installed via git clone."
    exit 1
fi

# Check if Flask is running
RUNNING=false
if pgrep -f "python.*ptos_web.py" > /dev/null 2>&1; then
    RUNNING=true
    echo "Flask server is running. Stopping it first..."
    pkill -f "python.*ptos_web.py" 2>/dev/null || true
    sleep 1
fi

echo "Pulling latest changes..."
git pull

echo ""
echo "=========================================="
echo "  ✅ PTOS Updated!"
echo "=========================================="
echo ""

if [ "$RUNNING" = true ]; then
    echo "You can restart with:"
    echo "  ./start_ptos_linux.sh"
fi
