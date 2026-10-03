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
    UPDATE_STAMP="$PTOS_DIR/.ptos_last_update"
    UPDATE_INTERVAL=21600
    NOW=$(date +%s 2>/dev/null || echo 0)
    LAST=0
    if [ -f "$UPDATE_STAMP" ]; then
        LAST=$(cat "$UPDATE_STAMP" 2>/dev/null || echo 0)
    fi
    case "$LAST" in ''|*[!0-9]*) LAST=0 ;; esac
    FORCE_UPDATE=0
    for arg in "$@"; do
        if [ "$arg" = "--update" ]; then FORCE_UPDATE=1; fi
    done
    if [ "$FORCE_UPDATE" = "1" ] || [ $((NOW - LAST)) -ge "$UPDATE_INTERVAL" ]; then
        echo "Checking for updates..."
        # Stamp before the fetch so an offline check still waits out the interval.
        echo "$NOW" > "$UPDATE_STAMP" 2>/dev/null || true
        # Bound the check so a dead network can't stall the launcher. Without
        # timeout we skip the check entirely rather than fetch unbounded.
        if command -v timeout >/dev/null 2>&1; then
            timeout 15 git fetch --quiet origin main 2>/dev/null
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
            echo "Skipping update check ('timeout' not available)."
        fi
    else
        echo "Skipping update check (checked recently)."
    fi
else
    echo "Not a git repo — skipping update check."
fi

# ── Port (ask ptos.py, which reads [server] port the same way) ─────────────
PTOS_PORT=$(python -c "import ptos; print(ptos.get_config().get('server', {}).get('port', 5000))" 2>/dev/null)
case "$PTOS_PORT" in
    ''|*[!0-9]*) PTOS_PORT=5000 ;;
esac
PTOS_URL="http://localhost:$PTOS_PORT"

# ── Kill anything already on the port ──────────────────────────────────────
pkill -f "python.*ptos_web.py" 2>/dev/null || true

# ── Start Flask, then open browser ──────────────────────────────────────────
echo ""
echo "Starting PTOS Web Server..."
echo "Open in browser: $PTOS_URL"
echo ""

python ptos_web.py &
FLASK_PID=$!

# Wait for Flask to be ready (up to 15s), polling 4x faster and giving up
# early if the server process died instead of waiting out the full timeout.
echo -n "Waiting for server "
SERVER_READY=0
for i in $(seq 1 60); do
    if curl -s "$PTOS_URL" >/dev/null 2>&1; then
        SERVER_READY=1
        echo ""
        break
    fi
    if ! kill -0 "$FLASK_PID" 2>/dev/null; then
        echo ""
        echo "Server process exited — see the errors above."
        SERVER_READY=-1
        break
    fi
    echo -n "."
    sleep 0.25
done

if [ "$SERVER_READY" = "1" ]; then
    echo "Server ready!"
    am start -a android.intent.action.VIEW -d "$PTOS_URL" >/dev/null 2>&1 || true
elif [ "$SERVER_READY" = "0" ]; then
    echo ""
    echo "Server is taking longer than usual to start"
    echo "Check the messages above for details."
    echo -n "Waiting "
    for i in $(seq 1 120); do
        if curl -s "$PTOS_URL" >/dev/null 2>&1; then
            echo ""
            echo "Server ready!"
            am start -a android.intent.action.VIEW -d "$PTOS_URL" >/dev/null 2>&1 || true
            break
        fi
        if ! kill -0 "$FLASK_PID" 2>/dev/null; then
            echo ""
            echo "Server process exited — see the errors above."
            break
        fi
        echo -n "."
        sleep 1
    done
    echo ""
fi
wait $FLASK_PID
