#!/bin/bash
# PTOS Setup Script for Termux
# Run ONCE to install PTOS (first-time only)
#
# This script:
# - Clones PTOS to ~/storage/shared/ptos
# - Installs Python and Flask
# - Initializes PTOS
#
# For updates, just run start_ptos.sh (it handles updates automatically)

set -e

PTOS_DIR="$HOME/storage/shared/ptos"

echo "=========================================="
echo "  PTOS Setup for Termux"
echo "=========================================="
echo ""

# Check if already installed
if [ -d "$PTOS_DIR" ]; then
    echo "❌ PTOS is already installed at $PTOS_DIR"
    echo ""
    echo "To update PTOS, just run:"
    echo "  ./start_ptos.sh"
    echo ""
    echo "This will automatically pull latest changes."
    exit 1
fi

echo "📥 Cloning PTOS repository..."
mkdir -p "$HOME/storage/shared"
git clone https://github.com/godwinburby/ptos.git "$PTOS_DIR"

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
echo "To start PTOS Web:"
echo "  cd $PTOS_DIR"
echo "  ./start_ptos.sh"
echo ""
echo "The start script will auto-update PTOS each time you run it."
