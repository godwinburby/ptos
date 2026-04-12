#!/bin/bash
# PTOS Update Script for Android (Termux)
# Downloads latest code files. Preserves config/, records/, journal/, templates/.
# Uses robust error handling with atomic operations.

TMP_DIR="$HOME/.ptos-temp"
PTOS_DIR="$HOME/storage/shared/ptos"

# Cleanup on exit
cleanup() {
    rm -rf "$TMP_DIR" 2>/dev/null
}
trap cleanup EXIT

echo "=========================================="
echo "  PTOS Update"
echo "=========================================="
echo ""

if [ ! -d "$PTOS_DIR" ]; then
    echo "ERROR: PTOS not installed. Run setup_ptos_android.sh first."
    exit 1
fi

cd "$PTOS_DIR"

# ── Download latest zip ───────────────────────────────────────────────────────
echo "Downloading PTOS..."
rm -rf "$TMP_DIR" 2>/dev/null
mkdir -p "$TMP_DIR"

curl -f -L -o "$TMP_DIR/ptos.zip" \
    https://github.com/godwinburby/ptos/archive/refs/heads/main.zip

if [ $? -ne 0 ] || [ ! -f "$TMP_DIR/ptos.zip" ]; then
    echo "ERROR: Download failed. Check your internet connection."
    exit 1
fi

# ── Verify zip integrity ─────────────────────────────────────────────────────
echo "Verifying download..."
unzip -t "$TMP_DIR/ptos.zip" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "ERROR: Downloaded file is corrupted."
    exit 1
fi

echo ""
echo "Extracting..."
mkdir -p "$TMP_DIR/new"
unzip -q "$TMP_DIR/ptos.zip" -d "$TMP_DIR/new"

if [ ! -d "$TMP_DIR/new/ptos-main" ]; then
    echo "ERROR: Extraction failed."
    exit 1
fi

# ── Check what changed ────────────────────────────────────────────────────────
echo "Checking for changes..."
FILES_CHANGED=0

for f in "$TMP_DIR/new/ptos-main"/*.py; do
    fname="$(basename "$f")"
    if [ ! -f "$PTOS_DIR/$fname" ] || ! cmp -s "$f" "$PTOS_DIR/$fname"; then
        FILES_CHANGED=1
        break
    fi
done

if [ -d "$TMP_DIR/new/ptos-main/web_templates" ] && [ "$FILES_CHANGED" -eq 0 ]; then
    if [ ! -d "$PTOS_DIR/web_templates" ] || \
       ! cmp -s "$TMP_DIR/new/ptos-main/web_templates/base.html" \
              "$PTOS_DIR/web_templates/base.html" 2>/dev/null; then
        FILES_CHANGED=1
    fi
fi

# ── Apply update ──────────────────────────────────────────────────────────────
if [ "$FILES_CHANGED" -eq 1 ]; then
    echo "Updating PTOS code files..."
    
    # Backup old Python files to .bak
    for f in "$PTOS_DIR"/*.py; do
        [ -f "$f" ] && cp "$f" "$f.bak" 2>/dev/null || true
    done
    
    # Python files
    cp "$TMP_DIR/new/ptos-main"/*.py "$PTOS_DIR/" 2>/dev/null || true
    
    # Web templates
    rm -rf "$PTOS_DIR/web_templates" 2>/dev/null || true
    cp -r "$TMP_DIR/new/ptos-main/web_templates" "$PTOS_DIR/" 2>/dev/null || true
    
    # Shell scripts inside ptos dir
    cp "$TMP_DIR/new/ptos-main"/*_android.sh "$PTOS_DIR/" 2>/dev/null || true
    chmod +x "$PTOS_DIR"/*_android.sh 2>/dev/null || true
    
    # Remove .bak files on success
    for f in "$PTOS_DIR"/*.bak; do
        [ -f "$f" ] && rm "$f" 2>/dev/null || true
    done
    
    echo "Code updated."
    
    # ── Save latest SHA to .version file ───────────────────────────────────────
    echo "Saving version..."
    SHA=$(curl -sf "https://api.github.com/repos/godwinburby/ptos/commits/main" \
        | grep '"sha"' | head -1 | cut -d'"' -f4)
    if [ -n "$SHA" ]; then
        echo "$SHA" > "$PTOS_DIR/.version"
    else
        echo "WARNING: Failed to fetch version. Will retry on next update."
        rm -f "$PTOS_DIR/.version"
    fi
else
    echo "Already up to date."
fi

# ── Refresh scripts in $HOME ─────────────────────────────────────────────────
echo ""
echo "Refreshing scripts..."
for script in start_ptos_android.sh update_ptos_android.sh setup_ptos_android.sh; do
    curl -fsSL "https://raw.githubusercontent.com/godwinburby/ptos/main/$script" \
         -o "$HOME/$script" 2>/dev/null || true
    chmod +x "$HOME/$script" 2>/dev/null || true
done

# ── Refresh widget shortcuts ──────────────────────────────────────────────────
echo "Refreshing shortcuts..."
mkdir -p "$HOME/.shortcuts"
for script in setup_ptos_android.sh start_ptos_android.sh update_ptos_android.sh; do
    rm -f "$HOME/.shortcuts/$script"
    ln -s "$HOME/$script" "$HOME/.shortcuts/$script" 2>/dev/null || true
done

echo ""
echo "=========================================="
echo "  PTOS Updated!"
echo "=========================================="
echo ""

# ── Restart server ────────────────────────────────────────────────────────────
echo "Restarting server..."
(
    sleep 2
    pkill -f "python.*ptos_web.py" 2>/dev/null || true
    sleep 1
    # Open browser
    am start -a android.intent.action.VIEW -d http://localhost:5000 >/dev/null 2>&1 &
    # Start server
    nohup python "$PTOS_DIR/ptos_web.py" > /dev/null 2>&1 &
) &
disown

echo "Done. PTOS will open in browser."
