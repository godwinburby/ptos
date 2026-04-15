#!/bin/bash
# PTOS Setup Script for Linux
# Run it anywhere: ./setup_ptos_linux.sh
# Clones the repo if not found, installs deps, and starts the web server.

echo "=========================================="
echo "  PTOS Setup for Linux"
echo "=========================================="
echo ""

# ── Locate PTOS directory ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "$SCRIPT_DIR/ptos.py" ]; then
    echo "ptos.py not found here — cloning from GitHub..."
    git clone https://github.com/godwinburby/ptos.git "$SCRIPT_DIR/ptos"
    cd "$SCRIPT_DIR/ptos"
else
    cd "$SCRIPT_DIR"
fi
PTOS_DIR="$(pwd)"

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
    echo ""
    echo "ERROR: Python 3.11 or higher is required but not found."
    echo "Install it, e.g.:  sudo apt install python3.11"
    exit 1
fi
echo "Using $PYTHON ($($PYTHON --version))"

# ── Check if already initialised ─────────────────────────────────────────────
if [ -d "$PTOS_DIR/config" ]; then
    echo "Already initialised (config/ exists). Skipping first-time setup."
    INIT_NEEDED=false
else
    INIT_NEEDED=true
fi

# ── Install Flask ─────────────────────────────────────────────────────────────
if [ "$INIT_NEEDED" = true ]; then
    echo ""
    echo "--- Installing Flask ---"
    # Ensure pip is available for the chosen Python
    if command -v apt &>/dev/null; then
        sudo apt update -qq && sudo apt install -y python3-pip 2>/dev/null || true
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3-pip 2>/dev/null || true
    elif command -v pacman &>/dev/null; then
        sudo pacman -Sy --noconfirm python-pip 2>/dev/null || true
    elif command -v zypper &>/dev/null; then
        sudo zypper install -y python3-pip 2>/dev/null || true
    fi

    $PYTHON -m pip install flask --break-system-packages --quiet
    echo "Flask installed."

    echo ""
    echo "--- Initialising PTOS ---"
    $PYTHON ptos.py --init

    echo ""
    echo "--- Your Name ---"
    echo "Enter your name (leave blank for 'User'):"
    read -r USER_NAME
    if [ -n "$USER_NAME" ]; then
        $PYTHON ptos.py --set-name "$USER_NAME"
    fi

    echo ""
    echo "PTOS initialised."
fi

# ── Make companion scripts executable ────────────────────────────────────────
for script in start_ptos_linux.sh update_ptos_linux.sh; do
    [ -f "$PTOS_DIR/$script" ] && chmod +x "$PTOS_DIR/$script" && echo "Marked executable: $script"
done

# ── Kill anything on port 5000 ────────────────────────────────────────────────
echo ""
echo "Checking port 5000..."
if command -v lsof &>/dev/null; then
    PID=$(lsof -ti:5000 2>/dev/null || true)
    if [ -n "$PID" ]; then
        echo "Stopping existing process on port 5000 (PID $PID)..."
        kill "$PID" 2>/dev/null || kill -9 "$PID" 2>/dev/null || true
        sleep 1
    fi
elif command -v fuser &>/dev/null; then
    fuser -k 5000/tcp 2>/dev/null || true
    sleep 1
fi
echo "Port 5000 ready."

# ── Start Flask, then open browser ───────────────────────────────────────────
echo ""
echo "=========================================="
echo "  Starting PTOS Web Server"
echo "=========================================="
echo ""
echo "Open in browser: http://localhost:5000"
echo "Press Ctrl+C to stop."
echo ""

# Start Flask in background, wait for it to be ready, then open browser
$PYTHON ptos_web.py &
FLASK_PID=$!
sleep 2
xdg-open http://localhost:5000 2>/dev/null || true

# Bring Flask back to foreground so Ctrl+C works naturally
wait $FLASK_PID
