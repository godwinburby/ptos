#!/bin/bash
# PTOS Setup Script for Termux
# Run ONCE to install PTOS, or anytime to update
#
# First run:  Full setup (clone, install dependencies, init)
# Update run:  Quick git pull (data never touched)

set -e

PTOS_DIR="$HOME/storage/shared/ptos"

echo "=========================================="
echo "  PTOS Setup for Termux"
echo "=========================================="
echo ""

# Determine if first run or update
if [ ! -d "$PTOS_DIR" ]; then
    # FIRST RUN
    echo "📥 Cloning PTOS repository..."
    mkdir -p "$HOME/storage/shared"
    git clone https://github.com/godwinburby/ptos.git "$PTOS_DIR"
    echo "✅ Cloned PTOS to $PTOS_DIR"
    IS_FIRST_RUN=true
else
    # UPDATE
    echo "✅ PTOS directory found at $PTOS_DIR"
    cd "$PTOS_DIR"
    echo "📥 Pulling latest changes..."
    git pull
    IS_FIRST_RUN=false
fi

cd "$PTOS_DIR"

if [ "$IS_FIRST_RUN" = true ]; then
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
echo "=========================================="
echo "  ✅ PTOS is ready!"
echo "=========================================="
echo ""
echo "To start PTOS Web:"
echo "  cd $PTOS_DIR"
echo "  ./start_ptos.sh"
echo ""
echo "To update PTOS anytime:"
echo "  ./setup_ptos.sh"
