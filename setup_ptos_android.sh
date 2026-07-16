#!/bin/bash
# PTOS Setup Script for Android (Termux)
# Clones the repo, installs deps, and starts the web server.

echo "=========================================="
echo "  PTOS Setup for Android"
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

# ── Storage permission (optional) ──────────────────────────────────────────────
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

# ── Create data folder in shared storage ──────────────────────────────────────
# Android separates code ($HOME/ptos) from data (~/storage/shared/ptos-data)
# so Syncthing/file managers can access the data folder directly.
DATA_DIR="$HOME/storage/shared/ptos-data"
if [ -d "$HOME/storage/shared" ]; then
    if [ ! -d "$DATA_DIR" ]; then
        echo "Creating data folder: $DATA_DIR"
        mkdir -p "$DATA_DIR"
    else
        echo "Data folder exists: $DATA_DIR"
    fi
    # Write .ptos_home so PTOS uses the shared data folder
    BOOTSTRAP="$PTOS_DIR/.ptos_home"
    CURRENT_HOME=""
    if [ -f "$BOOTSTRAP" ]; then
        CURRENT_HOME="$(cat "$BOOTSTRAP")"
    fi
    if [ "$CURRENT_HOME" != "$DATA_DIR" ]; then
        echo "$DATA_DIR" > "$BOOTSTRAP"
        echo "Wrote .ptos_home -> $DATA_DIR"
    fi
else
    echo "Shared storage not available — data will stay in code folder."
    echo "Run 'termux-setup-storage' and re-run setup to separate data from code."
fi

# ── Check Python version ──────────────────────────────────────────────────────
if ! python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
    echo "ERROR: Python 3.11+ required. Run:  pkg install python"
    exit 1
fi

# ── Install git if missing ────────────────────────────────────────────────────
if ! command -v git &>/dev/null; then
    echo "Installing git..."
    pkg update -y
    pkg install -y git
fi

# ── Install rclone if missing ─────────────────────────────────────────────────
if ! command -v rclone &>/dev/null; then
    echo "Installing rclone..."
    pkg install -y rclone
fi

# ── Check Flask installed ────────────────────────────────────────────────────
echo "Checking dependencies..."
if ! python -c "import flask" 2>/dev/null; then
    echo "Installing Flask and tomli-w..."
    python -m pip install flask tomli-w --quiet
else
    echo "Flask already installed."
fi

# ── Check if already initialised ─────────────────────────────────────────────
# Check the data folder (ptos-data), not the code folder.
INIT_DIR="$PTOS_DIR"
if [ -f "$PTOS_DIR/.ptos_home" ]; then
    INIT_DIR="$(cat "$PTOS_DIR/.ptos_home")"
fi
if [ -d "$INIT_DIR/config" ]; then
    echo "Already initialised (config/ exists in data folder). Skipping first-time setup."
    INIT_NEEDED=false
else
    INIT_NEEDED=true
fi

# ── Initialise PTOS (only if first time) ─────────────────────────────────────
if [ "$INIT_NEEDED" = true ]; then
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

# ── Download setup script to $HOME (for easy re-run) ──────────────────────────
echo ""
echo "Downloading setup script..."
cp "$PTOS_DIR/setup_ptos_android.sh" "$HOME/setup_ptos_android.sh" 2>/dev/null || true
chmod +x "$HOME/setup_ptos_android.sh" 2>/dev/null || true

# ── Refresh widget shortcuts ────────────────────────────────────────────────────
echo ""
echo "Creating widget shortcuts..."
mkdir -p "$HOME/.shortcuts"
rm -f "$HOME/.shortcuts"/*.sh
ln -s "$PTOS_DIR/start_ptos_android.sh" "$HOME/.shortcuts/Start_PTOS.sh" 2>/dev/null || true
echo "Shortcuts created."

echo ""
echo "Starting PTOS..."
echo "Open in browser: http://localhost:5000"
echo ""

# Start server in background
python ptos_web.py &
FLASK_PID=$!

# Wait for server to be ready (up to 15s)
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
    am start -a android.intent.action.VIEW -d http://localhost:5000 >/dev/null 2>&1 || true
else
    echo ""
    echo "Server is taking longer than usual to start (startup sync may"
    echo "still be running — check the messages above)."
    echo "Waiting for server to become available..."
    for i in $(seq 1 120); do
        if curl -s http://localhost:5000 >/dev/null 2>&1; then
            am start -a android.intent.action.VIEW -d http://localhost:5000 >/dev/null 2>&1 || true
            break
        fi
        sleep 1
    done
fi
wait $FLASK_PID
