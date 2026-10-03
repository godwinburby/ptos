#!/bin/bash
# PTOS Launcher for Linux
# Handles both first-time setup and daily launch.
# Usage:  ./run_ptos_linux.sh

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
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

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

# ── Resolve data directory ────────────────────────────────────────────────────
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
            GIT_TERMINAL_PROMPT=0 timeout 8 git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=5 fetch --quiet origin main 2>/dev/null
            LOCAL=$(git rev-parse HEAD 2>/dev/null)
            REMOTE=$(git rev-parse origin/main 2>/dev/null)
            if [ "$LOCAL" = "$REMOTE" ]; then
                echo "Already on latest version."
            else
                echo "Updating..."
                if timeout 30 git pull --ff-only origin main; then
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

# ── Port (ask ptos.py, which reads [server] port the same way) ──────────────
PTOS_PORT=$("$PYTHON" -c "import ptos; print(ptos.get_config().get('server', {}).get('port', 5000))" 2>/dev/null)
case "$PTOS_PORT" in
    ''|*[!0-9]*) PTOS_PORT=5000 ;;
esac
PTOS_URL="http://localhost:$PTOS_PORT"

# ── Kill anything already on the port ───────────────────────────────────────
echo ""
echo "Checking port $PTOS_PORT..."
if command -v lsof &>/dev/null; then
    PID=$(lsof -ti:"$PTOS_PORT" 2>/dev/null || true)
    if [ -n "$PID" ]; then
        echo "Stopping process on port $PTOS_PORT (PID $PID)..."
        kill "$PID" 2>/dev/null || kill -9 "$PID" 2>/dev/null || true
    fi
elif command -v fuser &>/dev/null; then
    fuser -k "$PTOS_PORT"/tcp 2>/dev/null || true
fi
echo "Port $PTOS_PORT ready."

# ── Start Flask, then open browser ──────────────────────────────────────────
echo ""
echo "=========================================="
echo "  Starting PTOS Web Server"
echo "=========================================="
echo ""
echo "Open in browser: $PTOS_URL"
echo "Press Ctrl+C to stop."
echo ""

$PYTHON ptos_web.py &
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
    xdg-open "$PTOS_URL" 2>/dev/null || true
elif [ "$SERVER_READY" = "0" ]; then
    echo ""
    echo "Server is taking longer than usual to start"
    echo "Check the messages above for details."
    echo -n "Waiting "
    for i in $(seq 1 120); do
        if curl -s "$PTOS_URL" >/dev/null 2>&1; then
            echo ""
            echo "Server ready!"
            xdg-open "$PTOS_URL" 2>/dev/null || true
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
