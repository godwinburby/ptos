#!/bin/bash
# PTOS Setup Script for Termux
# Downloads and installs PTOS, or refreshes scripts if already installed.

TMP_DIR="$HOME/.ptos-temp"
PTOS_DIR="$HOME/storage/shared/ptos"

echo "=========================================="
echo "  PTOS Setup for Termux"
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

# ── Check Python version ──────────────────────────────────────────────────────
check_python() {
    if command -v python &>/dev/null; then
        if python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

# ── Install or use existing ───────────────────────────────────────────────────
if [ -d "$PTOS_DIR" ]; then
    echo "PTOS already installed at: $PTOS_DIR"
    cd "$PTOS_DIR"
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

    # Verify Python version
    if ! check_python; then
        echo ""
        echo "ERROR: Installed Python is older than 3.11."
        echo "Try:  pkg install python"
        echo "Then re-run this script."
        exit 1
    fi

    echo ""
    echo "--- Installing Flask ---"
    python -m pip install flask --quiet

    echo ""
    echo "--- Initialising PTOS ---"
    python ptos.py --init

    # ── Save initial version ───────────────────────────────────────────────────
    echo "Saving version..."
    curl -s "https://api.github.com/repos/godwinburby/ptos/commits/main" \
        | grep '"sha"' | head -1 | cut -d'"' -f4 > "$PTOS_DIR/.version"
fi

# ── Download start/update scripts to $HOME ───────────────────────────────────
echo ""
echo "Downloading companion scripts..."
curl -fsSL https://raw.githubusercontent.com/godwinburby/ptos/main/start_ptos_termux.sh \
     -o "$HOME/start_ptos_termux.sh"
curl -fsSL https://raw.githubusercontent.com/godwinburby/ptos/main/update_ptos_termux.sh \
     -o "$HOME/update_ptos_termux.sh"
curl -fsSL https://raw.githubusercontent.com/godwinburby/ptos/main/setup_ptos_termux.sh \
     -o "$HOME/setup_ptos_termux.sh"
chmod +x "$HOME/start_ptos_termux.sh" \
         "$HOME/update_ptos_termux.sh" \
         "$HOME/setup_ptos_termux.sh"
echo "Scripts ready."

# ── Termux Widget shortcuts ───────────────────────────────────────────────────
echo ""
echo "Creating widget shortcuts..."
mkdir -p "$HOME/.shortcuts"
for script in setup_ptos_termux.sh start_ptos_termux.sh update_ptos_termux.sh; do
    rm -f "$HOME/.shortcuts/$script"
    ln -s "$HOME/$script" "$HOME/.shortcuts/$script"
done
echo "Shortcuts created."

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Start PTOS:   ./start_ptos_termux.sh"
echo "Update PTOS:  ./update_ptos_termux.sh"
