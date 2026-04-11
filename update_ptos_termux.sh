#!/bin/bash
# PTOS Update Script for Termux
# Downloads latest version and updates code files
# Preserves user data (config/, records/, templates/, backups/)

TMP_DIR="$HOME/.ptos-temp"
PTOS_DIR="$HOME/storage/shared/ptos"

echo "=========================================="
echo "  PTOS Update"
echo "=========================================="
echo ""

if [ ! -d "$PTOS_DIR" ]; then
    echo "=========================================="
    echo "  PTOS is not installed!"
    echo "=========================================="
    echo ""
    echo "Run setup_ptos.sh first to install PTOS."
    exit 1
fi

cd "$PTOS_DIR"

echo "📥 Downloading latest PTOS..."
rm -rf "$TMP_DIR" 2>/dev/null
mkdir -p "$TMP_DIR"

curl -L --progress-bar -o "$TMP_DIR/ptos.zip" \
    https://github.com/godwinburby/ptos/archive/refs/heads/main.zip

if [ ! -f "$TMP_DIR/ptos.zip" ]; then
    echo ""
    echo "❌ Download failed!"
    exit 1
fi

echo ""
echo "📦 Extracting files..."
mkdir -p "$TMP_DIR/new"
unzip -o "$TMP_DIR/ptos.zip" -d "$TMP_DIR/new" > /dev/null 2>&1

if [ ! -d "$TMP_DIR/new/ptos-main" ]; then
    echo ""
    echo "❌ Extraction failed!"
    rm -rf "$TMP_DIR"
    exit 1
fi

echo "🔍 Checking for updates..."
FILES_CHANGED=0

for pyfile in "$TMP_DIR/new/ptos-main"/*.py; do
    filename=$(basename "$pyfile")
    if [ -f "$PTOS_DIR/$filename" ]; then
        if ! cmp -s "$pyfile" "$PTOS_DIR/$filename"; then
            FILES_CHANGED=1
            break
        fi
    else
        FILES_CHANGED=1
        break
    fi
done

if [ -d "$TMP_DIR/new/ptos-main/web_templates" ]; then
    if [ ! -d "$PTOS_DIR/web_templates" ] || ! cmp -s "$TMP_DIR/new/ptos-main/web_templates/base.html" "$PTOS_DIR/web_templates/base.html" 2>/dev/null; then
        FILES_CHANGED=1
    fi
fi

if [ "$FILES_CHANGED" -eq 1 ]; then
    echo "📦 Updating PTOS code..."
    cp "$TMP_DIR/new/ptos-main"/*.py "$PTOS_DIR/" 2>/dev/null || true
    cp "$TMP_DIR/new/ptos-main"/*.sh "$HOME/" 2>/dev/null || true
    rm -rf "$PTOS_DIR/web_templates" 2>/dev/null || true
    cp -r "$TMP_DIR/new/ptos-main/web_templates" "$PTOS_DIR/" 2>/dev/null || true
    echo ""
    echo "✨ PTOS has been updated!"
else
    echo ""
    echo "✅ PTOS is already up to date!"
fi

rm -rf "$TMP_DIR"

echo ""

echo "📱 Creating/Updating Termux Widget shortcuts..."
mkdir -p "$HOME/.shortcuts"

rm -f "$HOME/.shortcuts/setup_ptos.sh" 2>/dev/null
rm -f "$HOME/.shortcuts/start_ptos.sh" 2>/dev/null
rm -f "$HOME/.shortcuts/update_ptos.sh" 2>/dev/null

ln -s "$HOME/setup_ptos.sh" "$HOME/.shortcuts/setup_ptos.sh"
ln -s "$HOME/start_ptos.sh" "$HOME/.shortcuts/start_ptos.sh"
ln -s "$HOME/update_ptos.sh" "$HOME/.shortcuts/update_ptos.sh"

echo ""
echo "✅ Widget shortcuts ready!"
echo ""
echo "To start PTOS Web:"
echo "  ./start_ptos.sh"
