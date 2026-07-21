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

# ── Create data directory (sibling to repo) ──────────────────────────────────
PARENT_DIR="$(dirname "$PTOS_DIR")"
DATA_DIR="$PARENT_DIR/ptos-data"
if [ ! -d "$DATA_DIR" ]; then
    echo ""
    echo "--- Creating data directory ---"
    mkdir -p "$DATA_DIR"
    echo "Data directory created at: $DATA_DIR"
else
    echo "Data directory exists: $DATA_DIR"
fi
echo "$DATA_DIR" > "$PTOS_DIR/.ptos_home"
echo "Configured .ptos_home -> $DATA_DIR"

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
if [ -d "$DATA_DIR/config" ]; then
    echo "Already initialised (config/ exists). Skipping first-time setup."
    INIT_NEEDED=false
else
    INIT_NEEDED=true
fi

# ── Install/patch pip ─────────────────────────────────────────────────────────
# Always check for pip - install if needed
if command -v apt &>/dev/null; then
    sudo apt update -qq && sudo apt install -y python3-pip 2>/dev/null || true
elif command -v dnf &>/dev/null; then
    sudo dnf install -y python3-pip 2>/dev/null || true
elif command -v pacman &>/dev/null; then
    sudo pacman -Sy --noconfirm python-pip 2>/dev/null || true
elif command -v zypper &>/dev/null; then
    sudo zypper install -y python3-pip 2>/dev/null || true
fi

# ── Install rclone if missing ───────────────────────────────────────────────
if ! command -v rclone &>/dev/null; then
    echo "Installing rclone..."
    curl -fsSL https://rclone.org/install.sh | sudo bash
fi

# ── Install/verify Flask and tomli-w ────────────────────────────────────────────────
echo ""
echo "--- Checking Flask and tomli-w ---"
if ! $PYTHON -c "import flask" 2>/dev/null; then
    echo "Installing Flask..."
    $PYTHON -m pip install flask tomli-w --break-system-packages --quiet
    echo "Flask installed."
else
    echo "Flask already installed."
fi

# ── Initialise PTOS (only if first time) ─────────────────────────────────────────
if [ "$INIT_NEEDED" = true ]; then
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
for script in start_ptos_linux.sh; do
    [ -f "$PTOS_DIR/$script" ] && chmod +x "$PTOS_DIR/$script" && echo "Marked executable: $script"
done

# ── Create Start_PTOS shortcut in parent directory ──────────────────────────
PARENT_DIR="$(dirname "$PTOS_DIR")"
SHORTCUT="$PARENT_DIR/Start_PTOS"
if [ ! -L "$SHORTCUT" ] && [ ! -f "$SHORTCUT" ]; then
    ln -s "$PTOS_DIR/start_ptos_linux.sh" "$SHORTCUT"
    chmod +x "$SHORTCUT"
    echo "Created shortcut: $SHORTCUT -> start_ptos_linux.sh"
elif [ -L "$SHORTCUT" ]; then
    echo "Shortcut already exists: $SHORTCUT"
else
    echo "Shortcut already exists: $SHORTCUT"
fi

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

$PYTHON ptos_web.py &
FLASK_PID=$!

# Wait for Flask to be ready (up to 15s)
echo "Waiting for server..."
SERVER_READY=0
for i in $(seq 1 15); do
    if curl -s http://localhost:5000 >/dev/null 2>&1; then
        SERVER_READY=1
        break
    fi
    sleep 1
done

if [ "$SERVER_READY" = "1" ]; then
    xdg-open http://localhost:5000 2>/dev/null || true
else
    echo ""
    echo "Server is taking longer than usual to start (startup sync may"
    echo "still be running — check the messages above)."
    echo "Waiting for server to become available..."
    for i in $(seq 1 120); do
        if curl -s http://localhost:5000 >/dev/null 2>&1; then
            xdg-open http://localhost:5000 2>/dev/null || true
            break
        fi
        sleep 1
    done
fi

# Bring Flask back to foreground so Ctrl+C works naturally
wait $FLASK_PID
