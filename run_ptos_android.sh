#!/bin/bash
# PTOS Launcher for Android (Termux)
# Handles both first-time setup and daily launch.
# Usage:  bash run_ptos_android.sh

echo "=========================================="
echo "  PTOS"
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

# ── Storage permission (optional) ──────────────────────────────────────────
if [ ! -d "$HOME/storage/shared" ]; then
    echo "Requesting storage permission (optional — needed for data folder)..."
    termux-setup-storage
    sleep 3
    if [ -d "$HOME/storage/shared" ]; then
        echo "Storage permission granted."
    else
        echo "Storage permission not granted (you can grant it later if needed)."
    fi
fi

# ── Create data folder in shared storage ────────────────────────────────────
# Android separates code ($HOME/ptos) from data (~/storage/shared/ptos-data)
# so Syncthing/file managers can access the data folder directly.
DATA_DIR="$HOME/storage/shared/ptos-data"
if [ -d "$HOME/storage/shared" ]; then
    if [ ! -d "$DATA_DIR" ]; then
        echo "Creating data folder: $DATA_DIR"
        mkdir -p "$DATA_DIR"
    else
        echo "Data folder: $DATA_DIR"
    fi
    # Write .ptos_home if missing or different
    BOOTSTRAP="$PTOS_DIR/.ptos_home"
    CURRENT_HOME=""
    if [ -f "$BOOTSTRAP" ]; then
        CURRENT_HOME="$(cat "$BOOTSTRAP")"
    fi
    if [ "$CURRENT_HOME" != "$DATA_DIR" ]; then
        echo "$DATA_DIR" > "$BOOTSTRAP"
        echo "Configured .ptos_home -> $DATA_DIR"
    fi
else
    echo "Shared storage not available — data will stay in code folder."
    echo "Run 'termux-setup-storage' and re-run to separate data from code."
    DATA_DIR="$PTOS_DIR"
fi

# ── Set PTOS_HOME for this session ─────────────────────────────────────────
export PTOS_HOME="$DATA_DIR"

# ── Install Python if missing ────────────────────────────────────────────────
if ! command -v python &>/dev/null || ! python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
    echo "Python 3.11+ not found. Installing..."
    pkg update -y
    pkg install -y python
fi

if ! python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
    echo "ERROR: Python 3.11+ could not be installed."
    echo "Try manually:  pkg install python"
    exit 1
fi

# ── Install git if missing (first-time only) ───────────────────────────────
if [ ! -d "$DATA_DIR/config" ]; then
    if ! command -v git &>/dev/null; then
        echo "Installing git..."
        pkg update -y
        pkg install -y git
    fi

    # Install rclone if missing
    if ! command -v rclone &>/dev/null; then
        echo "Installing rclone..."
        pkg install -y rclone
    fi

    # Install termux-api for notifications
    if ! command -v termux-notification &>/dev/null; then
        echo "Installing termux-api for notifications..."
        pkg install -y termux-api
    fi
fi

# ── Install Flask + tomli-w if missing ─────────────────────────────────────
if ! python -c "import flask" 2>/dev/null; then
    echo "Installing Flask and tomli-w..."
    python -m pip install flask tomli-w --quiet
fi

# ── Warn if termux-api missing ─────────────────────────────────────────────
if ! command -v termux-notification &>/dev/null; then
    echo "WARNING: termux-api not installed — notifications won't work."
    echo "Install with: pkg install termux-api"
    echo "Also install Termux:API app from F-Droid or Play Store."
fi

# ── First-time init (only if config/ doesn't exist) ────────────────────────
if [ ! -d "$DATA_DIR/config" ]; then
    echo ""
    echo "--- Initialising PTOS ---"
    python ptos.py --init

    echo ""
    echo "--- Your Name ---"
    echo "Enter your name (leave blank for 'User'):"
    read -r USER_NAME
    if [ -n "$USER_NAME" ]; then
        python ptos.py --set-name "$USER_NAME"
    fi

    echo ""
    echo "PTOS initialised."
fi

# ── Copy script to $HOME for easy re-run ───────────────────────────────────
cp "$PTOS_DIR/run_ptos_android.sh" "$HOME/run_ptos_android.sh" 2>/dev/null || true
chmod +x "$HOME/run_ptos_android.sh" 2>/dev/null || true

# ── Refresh widget shortcut ────────────────────────────────────────────────
mkdir -p "$HOME/.shortcuts"
rm -f "$HOME/.shortcuts"/*.sh
ln -s "$PTOS_DIR/run_ptos_android.sh" "$HOME/.shortcuts/run_ptos.sh" 2>/dev/null || true
echo "Widget shortcut: ~/.shortcuts/run_ptos.sh"

# ── Git pull (if repo) ─────────────────────────────────────────────────────
if [ -d ".git" ]; then
    echo "Checking for updates..."
    git fetch --quiet origin main 2>/dev/null
    LOCAL=$(git rev-parse HEAD 2>/dev/null)
    REMOTE=$(git rev-parse origin/main 2>/dev/null)
    if [ "$LOCAL" = "$REMOTE" ]; then
        echo "Already on latest version."
    else
        echo "Updating..."
        if git pull --ff-only origin main; then
            echo "Updated to latest version."
        else
            echo "Could not reach GitHub — continuing with local version."
        fi
    fi
else
    echo "Not a git repo — skipping update check."
fi

# ── Kill anything on port 5000 ─────────────────────────────────────────────
pkill -f "python.*ptos_web.py" 2>/dev/null || true
sleep 1

# ── Start Flask, then open browser ──────────────────────────────────────────
echo ""
echo "Starting PTOS Web Server..."
echo "Open in browser: http://localhost:5000"
echo ""

python ptos_web.py &
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
    am start -a android.intent.action.VIEW -d http://localhost:5000 >/dev/null 2>&1 || true
else
    echo ""
    echo "Server is taking longer than usual to start (startup sync may"
    echo "still be running — check the messages above)."
    echo -n "Waiting "
    for i in $(seq 1 120); do
        if curl -s http://localhost:5000 >/dev/null 2>&1; then
            echo ""
            echo "Server ready!"
            am start -a android.intent.action.VIEW -d http://localhost:5000 >/dev/null 2>&1 || true
            break
        fi
        echo -n "."
        sleep 1
    done
    echo ""
fi
wait $FLASK_PID
