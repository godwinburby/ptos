#!/bin/bash
# PTOS Setup Script for Termux
# Downloads and installs PTOS, or updates scripts and shortcuts if already installed

TMP_DIR="$HOME/.ptos-temp"
PTOS_DIR="$HOME/storage/shared/ptos"

echo "=========================================="
echo "  PTOS Setup for Termux"
echo "=========================================="
echo ""

if [ -d "$PTOS_DIR" ]; then
    echo "PTOS is already installed at: $PTOS_DIR"
    cd "$PTOS_DIR"
else
    echo "=========================================="
    echo "  Downloading and Installing PTOS"
    echo "=========================================="
    echo ""

    echo "📥 Downloading PTOS..."
    mkdir -p "$HOME/storage/shared"
    cd "$HOME/storage/shared"

    rm -rf "$TMP_DIR" 2>/dev/null
    mkdir -p "$TMP_DIR"

    curl -L --progress-bar -o "$TMP_DIR/ptos.zip" \
        https://github.com/godwinburby/ptos/archive/refs/heads/main.zip

    echo ""
    echo "📦 Extracting files..."
    mkdir -p "$TMP_DIR/new"
    unzip -o "$TMP_DIR/ptos.zip" -d "$TMP_DIR/new" > /dev/null 2>&1
    mv "$TMP_DIR/new/ptos-main" ptos
    rm -rf "$TMP_DIR"

    cd "$PTOS_DIR"

    echo ""
    echo "📦 Updating Termux packages..."
    pkg update && pkg upgrade -y

    echo ""
    echo "🐍 Installing Python..."
    pkg install python -y

    echo ""
    echo "📥 Installing Flask..."
    pip install flask

    echo ""
    echo "🚀 Initializing PTOS..."
    python ptos.py --init
fi

echo ""
echo "📥 Downloading start and update scripts to home folder..."
curl -fsSL https://raw.githubusercontent.com/godwinburby/ptos/main/start_ptos_termux.sh -o "$HOME/start_ptos_termux.sh"
curl -fsSL https://raw.githubusercontent.com/godwinburby/ptos/main/update_ptos_termux.sh -o "$HOME/update_ptos_termux.sh"
chmod +x "$HOME/start_ptos_termux.sh" "$HOME/update_ptos_termux.sh"
echo "Scripts downloaded and made executable."

echo ""
echo "📱 Creating Termux Widget shortcuts..."
mkdir -p "$HOME/.shortcuts"

rm -f "$HOME/.shortcuts/setup_ptos_termux.sh" 2>/dev/null
rm -f "$HOME/.shortcuts/start_ptos_termux.sh" 2>/dev/null
rm -f "$HOME/.shortcuts/update_ptos_termux.sh" 2>/dev/null

ln -s "$HOME/setup_ptos_termux.sh" "$HOME/.shortcuts/setup_ptos_termux.sh"
ln -s "$HOME/start_ptos_termux.sh" "$HOME/.shortcuts/start_ptos_termux.sh"
ln -s "$HOME/update_ptos_termux.sh" "$HOME/.shortcuts/update_ptos_termux.sh"

echo ""
echo "=========================================="
echo "  ✅ Setup Complete!"
echo "=========================================="
echo ""
echo "To start PTOS Web:"
echo "  ./start_ptos_termux.sh"
echo ""
echo "To update PTOS (when new version available):"
echo "  ./update_ptos_termux.sh"
