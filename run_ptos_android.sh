#!/bin/bash
# PTOS Launcher for Android (Termux)
# Handles both first-time setup and daily launch.
# Usage:  bash run_ptos_android.sh

# Strip CRLF if present (curl / git may deliver Windows line endings)
if grep -q $'\r' "$0" 2>/dev/null; then
    sed 's/\r$//' "$0" > "$0.tmp" && mv "$0.tmp" "$0"
    exec bash "$0" "$@"
fi

echo "=========================================="
echo "  PTOS"
echo "=========================================="
echo ""

# ── Locate PTOS directory ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "$SCRIPT_DIR/ptos.py" ] && [ -f "$HOME/ptos/ptos.py" ]; then
    SCRIPT_DIR="$HOME/ptos"
fi

if [ ! -f "$SCRIPT_DIR/ptos.py" ]; then
    echo "ptos.py not found — cloning from GitHub..."
    git clone https://github.com/godwinburby/ptos.git "$HOME/ptos"
    cd "$HOME/ptos"
else
    cd "$SCRIPT_DIR"
fi
PTOS_DIR="$(pwd)"

# ── Resolve data directory (sibling to repo, like the other scripts) ────────
# Fresh installs use Termux internal storage ($HOME/ptos-data) — fast, and no
# storage permission is needed. An existing install's location (e.g.
# ~/storage/shared/ptos-data from older versions) is honored via .ptos_home.
# Note: only the Termux-started Syncthing daemon can reach internal storage;
# the Syncthing Android app cannot. To move to shared storage instead later:
#   termux-setup-storage && python ptos.py --set-home ~/storage/shared/ptos-data
PARENT_DIR="$(dirname "$PTOS_DIR")"
if [ -f "$PTOS_DIR/.ptos_home" ]; then
    DATA_DIR="$(cat "$PTOS_DIR/.ptos_home" | tr -d '[:space:]')"
    echo "Data directory: $DATA_DIR (from .ptos_home)"
else
    DATA_DIR="$PARENT_DIR/ptos-data"
    if [ ! -d "$DATA_DIR" ]; then
        echo ""
        echo "--- Creating data directory ---"
        mkdir -p "$DATA_DIR"
        echo "Data directory created at: $DATA_DIR"
    else
        echo "Data directory: $DATA_DIR"
    fi
    echo "$DATA_DIR" > "$PTOS_DIR/.ptos_home"
    echo "Configured .ptos_home -> $DATA_DIR"
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

    # Install Syncthing if missing
    if ! command -v syncthing &>/dev/null; then
        echo "Installing Syncthing..."
        pkg install -y syncthing termux-services
    fi
    if ! command -v syncthing &>/dev/null; then
        echo "Syncthing could not be installed automatically."
        echo "Install it manually:  pkg install syncthing termux-services"
    else
        echo ""
        echo "Syncthing installed. Next: pair this device with your other device(s)."
        echo "Open http://127.0.0.1:8384 on each device and:"
        echo "  1. Actions -> Show ID, then Add Remote Device with the OTHER"
        echo "     device's ID — do this on BOTH devices (pairing is mutual)."
        echo "  2. Add Folder with Folder ID 'ptos-data', path '$DATA_DIR',"
        echo "     Share it with the other device as 'Send & Receive'."
        echo "     (Your data is in Termux internal storage — only the Termux-started"
        echo "     daemon can sync it, not the Syncthing Android app.)"
        echo "  3. On the other device ACCEPT the folder and set its path to"
        echo "     its own ptos-data directory (the folder ID must match on both)."
        echo "  4. Verify later with: ptos --sync-status"
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
rm -f "$HOME/.shortcuts/run_ptos.sh"
cp "$PTOS_DIR/run_ptos_android.sh" "$HOME/.shortcuts/run_ptos.sh" 2>/dev/null || true
chmod +x "$HOME/.shortcuts/run_ptos.sh" 2>/dev/null || true
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

# ── Keep Syncthing running (unless disabled) ─────────────────────────────────
SERVE="$(python ptos.py --get-config syncthing.serve 2>/dev/null | tr -d '[:space:]')"
if [ "$SERVE" = "true" ] && command -v syncthing &>/dev/null; then
    termux-wake-lock 2>/dev/null || true
    if command -v sv-enable &>/dev/null; then
        sv-enable syncthing 2>/dev/null || true
        sv up syncthing 2>/dev/null || true
    fi
    if ! pgrep -x syncthing >/dev/null 2>&1; then
        nohup syncthing serve --no-browser >/dev/null 2>&1 &
    fi
    echo "Syncthing is running (http://127.0.0.1:8384). Disable with: ptos --set-config syncthing.serve false"
elif command -v syncthing &>/dev/null; then
    echo "Syncthing is installed but not set to start automatically."
    echo "Enable it in Settings -> Syncthing, or run: ptos --set-config syncthing.serve true"
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
    echo "Server is taking longer than usual to start"
    echo "Check the messages above for details."
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
