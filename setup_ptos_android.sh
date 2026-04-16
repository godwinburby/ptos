#!/bin/bash
# PTOS Setup Script for Android (Termux)
# Downloads and installs PTOS, or refreshes scripts if already installed.

TMP_DIR="$HOME/.ptos-temp"
PTOS_DIR="$HOME/storage/shared/ptos"

echo "=========================================="
echo "  PTOS Setup for Android"
echo "=========================================="
echo ""

# ── Storage permission ────────────────────────────────────────────────────────
if [ ! -d "$HOME/storage/shared" ]; then
    echo "Requesting storage permission..."
    termux-setup-storage
    echo ""
    echo "If a permission dialog appeared, grant it, then re-run this script."
    echo "If no dialog appeared and ~/storage/shared still doesn't exist, run:"
    echo "  termux-setup-storage"
    exit 0
fi

cd "$HOME/storage/shared"

# ── Check Python version ──────────────────────────────────────────────────────
if ! python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
    echo "ERROR: Python 3.11+ required. Run:  pkg install python"
    exit 1
fi

# ── Check Flask installed ─────────────────────────────────────────────────────
if ! python -c "import flask" 2>/dev/null; then
    echo "Installing Flask..."
    python -m pip install flask --quiet
fi

# ── Install or use existing ────────────────────────────────────────────────────
if [ -d "$PTOS_DIR" ]; then
    echo "PTOS already installed at: $PTOS_DIR"
    echo "Updating Termux packages..."
    pkg update -y && pkg upgrade -y
else
    echo "--- Downloading PTOS ---"
    mkdir -p "$HOME/storage/shared"
    cd "$HOME/storage/shared"

    rm -rf "$TMP_DIR" 2>/dev/null
    mkdir -p "$TMP_DIR"

    curl -L --progress-bar -o "$TMP_DIR/ptos.zip" \
        https://github.com/godwinburby/ptos/archive/refs/heads/main.zip

    if [ ! -f "$TMP_DIR/ptos.zip" ]; then
        echo "ERROR: Download failed. Check your internet connection."
        exit 1
    fi

    echo ""
    echo "Extracting..."
    mkdir -p "$TMP_DIR/new"
    unzip -o "$TMP_DIR/ptos.zip" -d "$TMP_DIR/new" > /dev/null 2>&1
    mv "$TMP_DIR/new/ptos-main" ptos
    rm -rf "$TMP_DIR"

    cd "$PTOS_DIR"

    echo ""
    echo "--- Updating Termux packages ---"
    pkg update -y && pkg upgrade -y

    echo ""
    echo "--- Installing Python ---"
    pkg install python -y

    echo ""
    echo "--- Installing Flask ---"
    python -m pip install flask --quiet

    echo ""
    echo "--- Initialising PTOS ---"
    python ptos.py --init

    # ── Set user name ─────────────────────────────────────────────────────────
    echo ""
    echo "--- Your Name ---"
    echo "Enter your name (leave blank for 'User'):"
    read -r USER_NAME
    if [ -n "$USER_NAME" ]; then
        python ptos.py --set-name "$USER_NAME"
    fi

    # ── Save initial version ───────────────────────────────────────────────────
    echo "Saving version..."
    SHA=$(curl -sf "https://api.github.com/repos/godwinburby/ptos/commits/main" \
        | grep '"sha"' | head -1 | cut -d'"' -f4)
    if [ -n "$SHA" ]; then
        echo "$SHA" > "$PTOS_DIR/.version"
    else
        echo "WARNING: Failed to fetch version. Run update to track version."
    fi
fi

# ── Download Android scripts to $HOME ────────────────────────────────────────
echo ""
echo "Downloading scripts..."
for script in start_ptos_android.sh update_ptos_android.sh setup_ptos_android.sh; do
    curl -fsSL "https://raw.githubusercontent.com/godwinburby/ptos/main/$script" \
         -o "$HOME/$script" 2>/dev/null || true
    chmod +x "$HOME/$script" 2>/dev/null || true
done
chmod +x "$HOME/start_ptos_android.sh" \
         "$HOME/update_ptos_android.sh" \
         "$HOME/setup_ptos_android.sh" 2>/dev/null || true

# ── Refresh widget shortcuts ────────────────────────────────────────────────────
echo ""
echo "Creating widget shortcuts..."
mkdir -p "$HOME/.shortcuts"
rm -f "$HOME/.shortcuts"/*.sh
ln -s "$HOME/start_ptos_android.sh" "$HOME/.shortcuts/Start_PTOS.sh" 2>/dev/null || true
ln -s "$HOME/update_ptos_android.sh" "$HOME/.shortcuts/Update_PTOS.sh" 2>/dev/null || true
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
cd "$PTOS_DIR"
python ptos_web.py
