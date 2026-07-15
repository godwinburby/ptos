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
    echo "Requesting storage permission (optional — needed only for --set-home)..."
    termux-setup-storage
    sleep 3
    if [ -d "$HOME/storage/shared" ]; then
        echo "Storage permission granted."
    else
        echo "Storage permission not granted (you can grant it later if needed)."
    fi
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
if [ -d "$PTOS_DIR/config" ]; then
    echo "Already initialised (config/ exists). Skipping first-time setup."
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

# ── Download Android scripts to $HOME ────────────────────────────────────────
echo ""
echo "Downloading scripts..."
for script in start_ptos_android.sh setup_ptos_android.sh; do
    curl -fsSL "https://raw.githubusercontent.com/godwinburby/ptos/main/$script" \
         -o "$HOME/$script" 2>/dev/null || true
    chmod +x "$HOME/$script" 2>/dev/null || true
done

# ── Refresh widget shortcuts ────────────────────────────────────────────────────
echo ""
echo "Creating widget shortcuts..."
mkdir -p "$HOME/.shortcuts"
rm -f "$HOME/.shortcuts"/*.sh
ln -s "$HOME/start_ptos_android.sh" "$HOME/.shortcuts/Start_PTOS.sh" 2>/dev/null || true
echo "Shortcuts created."

echo ""
echo "Starting PTOS..."
echo "Open in browser: http://localhost:5000"
echo ""

# Start server in background
"$PYTHON" ptos_web.py &
FLASK_PID=$!

# Wait for server to be ready (up to 15s)
echo "Waiting for server..."
SERVER_READY=0
for i in $(seq 1 15); do
    if curl -sf http://localhost:5000 >/dev/null 2>&1; then
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
        if curl -sf http://localhost:5000 >/dev/null 2>&1; then
            am start -a android.intent.action.VIEW -d http://localhost:5000 >/dev/null 2>&1 || true
            break
        fi
        sleep 1
    done
fi
wait $FLASK_PID
