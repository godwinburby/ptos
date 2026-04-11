#!/bin/bash
# PTOS Setup Script for Linux
# Run it anywhere: ./setup_ptos_linux.sh
# It will clone the repo if not found, or use existing one.

set -e

echo "=========================================="
echo "  PTOS Setup for Linux"
echo "=========================================="
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if already in a PTOS repository
if [ ! -f "$SCRIPT_DIR/ptos.py" ]; then
    echo "PTOS not found."
    # Clone into ptos subfolder
    git clone https://github.com/godwinburby/ptos.git "$SCRIPT_DIR/ptos"
    cd "$SCRIPT_DIR/ptos"
    echo "Clone complete!"
else
    cd "$SCRIPT_DIR"
fi
SCRIPT_DIR="$(pwd)"

# Check if already initialized
if [ -d "config" ]; then
    echo "PTOS is already initialized (config/ folder exists)."
    echo "Skipping initialization..."
    INIT_NEEDED=false
else
    INIT_NEEDED=true
fi

# Find Python
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "Error: Python not found. Please install python3."
    exit 1
fi
echo "Using Python: $PYTHON"

# Install dependencies if init is needed
if [ "$INIT_NEEDED" = true ]; then
    echo ""
    echo "=========================================="
    echo "  Installing Dependencies"
    echo "=========================================="
    echo ""

    # Detect package manager
    PKG_MGR=""
    PKG_CMD=""
    if command -v apt &>/dev/null; then
        PKG_MGR="apt"
        PKG_CMD="sudo apt update && sudo apt install -y python3 python3-pip"
    elif command -v dnf &>/dev/null; then
        PKG_MGR="dnf"
        PKG_CMD="sudo dnf install -y python3 python3-pip"
    elif command -v pacman &>/dev/null; then
        PKG_MGR="pacman"
        PKG_CMD="sudo pacman -Sy --noconfirm python python-pip"
    elif command -v zypper &>/dev/null; then
        PKG_MGR="zypper"
        PKG_CMD="sudo zypper install -y python3 python3-pip"
    elif command -v apk &>/dev/null; then
        PKG_MGR="apk"
        PKG_CMD="apk add python3 py3-pip"
    fi

    if [ -n "$PKG_MGR" ]; then
        echo "Detected package manager: $PKG_MGR"
        echo "Installing system packages..."
        eval "$PKG_CMD"
    else
        echo "Package manager not detected."
        echo "Assuming Python and pip are already installed..."
    fi

    # Install Flask via pip
    echo ""
    echo "Installing Flask..."
    pip install flask --break-system-packages

    # Initialize PTOS
    echo ""
    echo "Initializing PTOS..."
    $PYTHON ptos.py --init

    echo ""
    echo "=========================================="
    echo "  PTOS Initialized!"
    echo "=========================================="
fi

# Clean up port 5000
echo ""
echo "Checking for processes on port 5000..."
if command -v lsof &>/dev/null; then
    PID=$(lsof -ti:5000 2>/dev/null)
    if [ -n "$PID" ]; then
        echo "Killing process $PID on port 5000..."
        kill -9 $PID 2>/dev/null || sudo kill -9 $PID 2>/dev/null || true
    fi
elif command -v fuser &>/dev/null; then
    fuser -k 5000/tcp 2>/dev/null || true
fi
echo "Port 5000 is ready."

# Start Flask server
echo ""
echo "=========================================="
echo "  Starting PTOS Web Server"
echo "=========================================="
echo ""
echo "Open your browser and go to: http://localhost:5000"
echo "Press Ctrl+C to stop the server."
echo ""

# Open browser in background
xdg-open http://localhost:5000 2>/dev/null &
BROWSER_PID=$!

# Start Flask server
$PYTHON ptos_web.py
