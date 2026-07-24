#!/bin/bash
# PTOS Launcher for Linux
# Handles both first-time setup and daily launch.
# Usage:  ./run_ptos_linux.sh

echo "=========================================="
echo "  PTOS"
echo "=========================================="
echo ""

# ── Locate PTOS directory ─────────────────────────────────────────────────────
_SOURCE="${BASH_SOURCE[0]}"
while [ -L "$_SOURCE" ]; do
    _DIR="$(cd -P "$(dirname "$_SOURCE")" && pwd)"
    _SOURCE="$(readlink "$_SOURCE")"
    [[ $_SOURCE != /* ]] && _SOURCE="$_DIR/$_SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$_SOURCE")" && pwd)"

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
    echo "Python 3.11+ not found. Installing..."
    if command -v apt &>/dev/null; then
        sudo apt update -qq && sudo apt install -y python3.11 2>/dev/null || sudo apt install -y python3 2>/dev/null
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3.11 2>/dev/null || sudo dnf install -y python3 2>/dev/null
    elif command -v pacman &>/dev/null; then
        sudo pacman -Sy --noconfirm python 2>/dev/null
    elif command -v zypper &>/dev/null; then
        sudo zypper install -y python311 2>/dev/null || sudo zypper install -y python3 2>/dev/null
    fi

    for cmd in python3.13 python3.12 python3.11 python3 python; do
        if command -v "$cmd" &>/dev/null; then
            if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
                PYTHON="$cmd"
                break
            fi
        fi
    done
fi

if [ -z "$PYTHON" ]; then
    echo ""
    echo "ERROR: Python 3.11 or higher is required but could not be installed."
    echo "Install it manually, e.g.:  sudo apt install python3.11"
    exit 1
fi
echo "Using $PYTHON ($($PYTHON --version))"

# ── Create data directory (sibling to repo) ──────────────────────────────────
PARENT_DIR="$(dirname "$PTOS_DIR")"
DATA_DIR="$PARENT_DIR/ptos-data"
if [ ! -d "$DATA_DIR" ]; then
    echo ""
    echo "--- Creating data directory ---"
    mkdir -p "$DATA_DIR"
    echo "Data directory created at: $DATA_DIR"
else
    echo "Data directory: $DATA_DIR"
fi

# ── Write .ptos_home if missing ──────────────────────────────────────────────
if [ ! -f "$PTOS_DIR/.ptos_home" ]; then
    echo "$DATA_DIR" > "$PTOS_DIR/.ptos_home"
    echo "Configured .ptos_home -> $DATA_DIR"
fi

# ── Set PTOS_HOME for this session ──────────────────────────────────────────
export PTOS_HOME="$DATA_DIR"

# ── Install pip if missing (first-time only) ─────────────────────────────────
if [ ! -d "$DATA_DIR/config" ]; then
    if command -v apt &>/dev/null; then
        sudo apt update -qq && sudo apt install -y python3-pip 2>/dev/null || true
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3-pip 2>/dev/null || true
    elif command -v pacman &>/dev/null; then
        sudo pacman -Sy --noconfirm python-pip 2>/dev/null || true
    elif command -v zypper &>/dev/null; then
        sudo zypper install -y python3-pip 2>/dev/null || true
    fi

    # Install rclone if missing
    if ! command -v rclone &>/dev/null; then
        echo "Installing rclone..."
        curl -fsSL https://rclone.org/install.sh | sudo bash
    fi
fi

# ── Install Flask + tomli-w if missing ──────────────────────────────────────
if ! $PYTHON -c "import flask" 2>/dev/null; then
    echo ""
    echo "--- Installing Flask and tomli-w ---"
    $PYTHON -m pip install flask tomli-w --break-system-packages --quiet
    echo "Flask installed."
fi

# ── First-time init (only if config/ doesn't exist) ─────────────────────────
if [ ! -d "$DATA_DIR/config" ]; then
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

# ── Git pull (if repo) ──────────────────────────────────────────────────────
if [ -d ".git" ]; then
    echo "Checking for updates..."
    if git pull --ff-only 2>&1; then
        echo "Updated."
    else
        echo "Could not reach GitHub — continuing with local version."
    fi
else
    echo "Not a git repo — skipping update check."
fi

# ── Kill anything on port 5000 ──────────────────────────────────────────────
echo ""
echo "Checking port 5000..."
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

$PYTHON ptos_web.py &
FLASK_PID=$!

# Wait for Flask to be ready (up to 15s)
echo -n "Waiting for server "
SERVER_READY=0
for i in $(seq 1 15); do
    if curl -s http://localhost:5000 >/dev/null 2>&1; then
        SERVER_READY=1
        echo ""
        break
    fi
    echo -n "."
    sleep 1
done

if [ "$SERVER_READY" = "1" ]; then
    echo "Server ready!"
    xdg-open http://localhost:5000 2>/dev/null || true
else
    echo ""
    echo "Server is taking longer than usual to start (startup sync may"
    echo "still be running — check the messages above)."
    echo -n "Waiting "
    for i in $(seq 1 120); do
        if curl -s http://localhost:5000 >/dev/null 2>&1; then
            echo ""
            echo "Server ready!"
            xdg-open http://localhost:5000 2>/dev/null || true
            break
        fi
        echo -n "."
        sleep 1
    done
    echo ""
fi
wait $FLASK_PID
