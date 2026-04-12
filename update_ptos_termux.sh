#!/bin/bash
# PTOS Update Script for Termux
# Downloads latest code files. Preserves config/, records/, journal/, templates/.

TMP_DIR="$HOME/.ptos-temp"
PTOS_DIR="$HOME/storage/shared/ptos"

echo "=========================================="
echo "  PTOS Update"
echo "=========================================="
echo ""

if [ ! -d "$PTOS_DIR" ]; then
    echo "ERROR: PTOS not installed. Run setup_ptos_termux.sh first."
    exit 1
fi

cd "$PTOS_DIR"

# ── Download latest zip ───────────────────────────────────────────────────────
echo "Downloading latest PTOS..."
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

if [ ! -d "$TMP_DIR/new/ptos-main" ]; then
    echo "ERROR: Extraction failed."
    rm -rf "$TMP_DIR"
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
    # Python files
    cp "$TMP_DIR/new/ptos-main"/*.py "$PTOS_DIR/" 2>/dev/null || true
    # Web templates
    rm -rf "$PTOS_DIR/web_templates" 2>/dev/null || true
    cp -r "$TMP_DIR/new/ptos-main/web_templates" "$PTOS_DIR/" 2>/dev/null || true
    # Shell scripts inside ptos dir
    cp "$TMP_DIR/new/ptos-main"/*_termux.sh "$PTOS_DIR/" 2>/dev/null || true
    chmod +x "$PTOS_DIR"/*_termux.sh 2>/dev/null || true
    echo "Code updated."
else
    echo "Already up to date."
fi

rm -rf "$TMP_DIR"

# ── Refresh companion scripts in $HOME ────────────────────────────────────────
# Always re-download so $HOME scripts stay current even if code didn't change
echo ""
echo "Refreshing companion scripts..."
curl -fsSL https://raw.githubusercontent.com/godwinburby/ptos/main/start_ptos_termux.sh \
     -o "$HOME/start_ptos_termux.sh"
curl -fsSL https://raw.githubusercontent.com/godwinburby/ptos/main/update_ptos_termux.sh \
     -o "$HOME/update_ptos_termux.sh"
curl -fsSL https://raw.githubusercontent.com/godwinburby/ptos/main/setup_ptos_termux.sh \
     -o "$HOME/setup_ptos_termux.sh"
chmod +x "$HOME/start_ptos_termux.sh" \
         "$HOME/update_ptos_termux.sh" \
         "$HOME/setup_ptos_termux.sh"

# ── Refresh widget shortcuts ──────────────────────────────────────────────────
echo "Refreshing widget shortcuts..."
mkdir -p "$HOME/.shortcuts"
for script in setup_ptos_termux.sh start_ptos_termux.sh update_ptos_termux.sh; do
    rm -f "$HOME/.shortcuts/$script"
    ln -s "$HOME/$script" "$HOME/.shortcuts/$script"
done

echo ""
echo "=========================================="
echo "  PTOS Updated!"
echo "=========================================="
echo ""

# ── Restart server (background this process first) ────────────────────────────
# Use double-fork: background a subshell that kills port 5000 and restarts
# This allows the main script to exit cleanly so Flask can return a response
(
    sleep 2
    echo "Stopping server..."
    pkill -f "python.*ptos_web.py" 2>/dev/null || true
    sleep 1
    echo "Starting server..."
    am start -a android.intent.action.VIEW -d http://localhost:5000 > /dev/null 2>&1 &
    nohup python "$PTOS_DIR/ptos_web.py" > /dev/null 2>&1 &
) &
disown
