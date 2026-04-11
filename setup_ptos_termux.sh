#!/bin/bash
# PTOS Setup Script for Termux
# Run ONCE to install PTOS (first-time only)

TMP_DIR="$HOME/.ptos-temp"
PTOS_DIR="$HOME/storage/shared/ptos"

echo "=========================================="
echo "  PTOS Setup for Termux"
echo "=========================================="
echo ""

if [ -d "$PTOS_DIR" ]; then
    echo "=========================================="
    echo "  PTOS is already installed!"
    echo "=========================================="
    echo ""
    echo "PTOS is at: $PTOS_DIR"
    echo ""
    echo "To start PTOS Web:"
    echo "  ./start_ptos.sh"
    echo ""
    echo "To update PTOS:"
    echo "  ./update_ptos.sh"
    exit 1
fi

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

echo ""
echo "=========================================="
echo "  ✅ Setup Complete!"
echo "=========================================="
echo ""


echo "📱 Creating Termux Widget shortcuts..."
mkdir -p "$HOME/.shortcuts"

rm -f "$HOME/.shortcuts/setup_ptos.sh" 2>/dev/null
rm -f "$HOME/.shortcuts/start_ptos.sh" 2>/dev/null
rm -f "$HOME/.shortcuts/update_ptos.sh" 2>/dev/null

ln -s "$HOME/setup_ptos.sh" "$HOME/.shortcuts/setup_ptos.sh"
ln -s "$HOME/start_ptos.sh" "$HOME/.shortcuts/start_ptos.sh"
ln -s "$HOME/update_ptos.sh" "$HOME/.shortcuts/update_ptos.sh"

echo ""
echo "✅ All done! Widget shortcuts ready."
echo ""
echo "To start PTOS Web:"
echo "  ./start_ptos.sh"
echo ""
echo "To update PTOS (when new version available):"
echo "  ./update_ptos.sh"
