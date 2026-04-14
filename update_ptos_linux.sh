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

echo "Pulling latest changes from GitHub..."
git pull

echo ""
echo "=========================================="
echo "  PTOS Updated!"
echo "=========================================="
echo ""

# Restart server in background
(
    sleep 2
    pkill -f "python.*ptos_web.py" 2>/dev/null || true
    sleep 1
    xdg-open http://localhost:5000 2>/dev/null &
    nohup python3 ptos_web.py > /dev/null 2>&1 &
) &
disown

echo "Done. PTOS will restart in browser."
