#!/bin/bash
# PTOS Setup Script for Android (Termux)
# Installs PTOS via git clone, separating code and data directories.

CODE_DIR="$HOME/ptos"
DATA_DIR="$HOME/storage/shared/ptos-data"

echo "=========================================="
echo "  PTOS Setup for Android"
echo "=========================================="
echo ""

# ── Storage permission ────────────────────────────────────────────────────────
if [ ! -d "$HOME/storage/shared" ]; then
    echo "Requesting storage permission..."
    termux-setup-storage
    sleep 3
    if [ ! -d "$HOME/storage/shared" ]; then
        echo ""
        echo "Storage permission not granted (or dialog still pending)."
        echo "Grant the permission when prompted, then re-run this script."
        echo "If no dialog appeared, run:  termux-setup-storage"
        exit 1
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

# ── Check Flask installed ────────────────────────────────────────────────────
echo "Checking dependencies..."
if ! python -c "import flask" 2>/dev/null; then
    echo "Installing Flask and tomli-w..."
    python -m pip install flask tomli-w --quiet
else
    echo "Flask already installed."
fi

# ── Clone or update code ─────────────────────────────────────────────────────
if [ -d "$CODE_DIR/.git" ]; then
    echo "PTOS code already present at $CODE_DIR"
else
    echo "Cloning PTOS from GitHub..."
    git clone https://github.com/godwinburby/ptos.git "$CODE_DIR"
fi

mkdir -p "$DATA_DIR"
echo "$DATA_DIR" > "$CODE_DIR/.ptos_home"

cd "$CODE_DIR"

echo ""
echo "--- Initialising PTOS ---"
python ptos.py --init

# ── Set user name ─────────────────────────────────────────────────────────────
echo ""
echo "--- Your Name ---"
echo "Enter your name (leave blank for 'User'):"
read -r USER_NAME
if [ -n "$USER_NAME" ]; then
    python ptos.py --set-name "$USER_NAME"
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
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Starting PTOS..."
echo "Open in browser: http://localhost:5000"
echo ""

# Open browser (non-blocking)
am start -a android.intent.action.VIEW -d http://localhost:5000 >/dev/null 2>&1 &

# Start server in foreground
cd "$CODE_DIR"
python ptos_web.py
