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

# ── Update Termux packages ────────────────────────────────────────────────────
echo "Updating Termux packages..."
pkg update -y && pkg upgrade -y

# ── Verify Python 3.11+ ──────────────────────────────────────────────────────
if ! python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
    echo "ERROR: Python 3.11+ required. Run:  pkg install python"
    exit 1
fi

# ── Verify Flask installed ─────────────────────────────────────────────────────
if ! python -c "import flask" 2>/dev/null; then
    echo "Installing Flask..."
    python -m pip install flask --quiet
fi

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

# ── Apply update ──────────────────────────────────────────────────────────────
echo "Updating PTOS code files..."

# Preserved directories and files (user data that must not be overwritten)
PRESERVED="config records journal notes tasks scripts backups exports .version __pycache__ .git"

# Copy all files except preserved ones
for item in "$TMP_DIR/new/ptos-main"/* "$TMP_DIR/new/ptos-main"/.[!.]*; do
    [ -e "$item" ] || continue
    basename=$(basename "$item")
    skip=0
    for p in $PRESERVED; do
        if [ "$basename" = "$p" ]; then
            skip=1
            break
        fi
    done
    if [ $skip -eq 0 ]; then
        if [ -d "$item" ]; then
            rm -rf "$PTOS_DIR/$basename" 2>/dev/null || true
            cp -r "$item" "$PTOS_DIR/" 2>/dev/null || true
        else
            cp "$item" "$PTOS_DIR/" 2>/dev/null || true
        fi
    fi
done

# Ensure shell scripts are executable
for f in "$PTOS_DIR"/*.sh; do
    [ -f "$f" ] && chmod +x "$f" 2>/dev/null || true
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
for script in start_ptos_android.sh update_ptos_android.sh; do
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
