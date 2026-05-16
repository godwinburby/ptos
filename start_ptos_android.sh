#!/bin/bash
# PTOS Start Script for Android (Termux)
# Automatically updates from GitHub if available, then starts the server.

PTOS_DIR="$HOME/storage/shared/ptos"
TMP_DIR="$HOME/.ptos-temp"

echo "=========================================="
echo "  PTOS Web"
echo "=========================================="
echo ""

if [ ! -d "$PTOS_DIR" ]; then
    echo "ERROR: PTOS not installed."
    echo "Run setup_ptos_android.sh first."
    exit 1
fi

cd "$PTOS_DIR"

# ── Find Python 3.11+ ─────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.11+ required. Run:  pkg install python"
    exit 1
fi

# ── Check/install dependencies ────────────────────────────────────────────────
if ! $PYTHON -c "import flask" 2>/dev/null; then
    echo "Installing Flask and tomli-w..."
    $PYTHON -m pip install flask tomli-w pytest --quiet
fi

# ── Check for updates via GitHub API ────────────────────────────────────────
echo "Checking for updates..."

# Fetch latest SHA from GitHub
LATEST_SHA=$(curl -sf "https://api.github.com/repos/godwinburby/ptos/commits/main" \
    | grep '"sha"' | head -1 | cut -d'"' -f4)

if [ -z "$LATEST_SHA" ]; then
    echo "Warning: Could not fetch latest version from GitHub."
else
    # Get current SHA (from .git or .version file)
    CURRENT_SHA=""
    if [ -d ".git" ]; then
        CURRENT_SHA=$(git rev-parse HEAD 2>/dev/null)
    elif [ -f ".version" ]; then
        CURRENT_SHA=$(cat .version)
    fi
    
    if [ "$CURRENT_SHA" = "$LATEST_SHA" ]; then
        echo "Already on latest version."
    else
        echo "Updating to latest version..."
        rm -rf "$TMP_DIR" 2>/dev/null
        mkdir -p "$TMP_DIR"
        
        curl -f -L -o "$TMP_DIR/ptos.zip" \
            "https://github.com/godwinburby/ptos/archive/refs/heads/main.zip"
        
        if [ -f "$TMP_DIR/ptos.zip" ]; then
            mkdir -p "$TMP_DIR/new"
            if ! unzip -q "$TMP_DIR/ptos.zip" -d "$TMP_DIR/new"; then
                echo "Warning: Zip extraction failed (download may be incomplete). Skipping update."
                rm -rf "$TMP_DIR"
            elif [ -d "$TMP_DIR/new/ptos-main" ]; then
                # Preserved directories and files (user data that must not be overwritten)
                PRESERVED="config records journal notes tasks scripts backups exports templates .version __pycache__ .git"
                
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
                
                # Save new version
                echo "$LATEST_SHA" > "$PTOS_DIR/.version"
                
                # Make shell scripts executable
                for f in "$PTOS_DIR"/*.sh; do [ -f "$f" ] && chmod +x "$f"; done
                
                echo "Updated to latest version."
            fi
        fi
        rm -rf "$TMP_DIR"
    fi
fi

# Stop any existing server
pkill -f "python.*ptos_web.py" 2>/dev/null || true
sleep 1

echo ""
echo "Starting PTOS Web Server..."
echo "Open in browser: http://localhost:5000"
echo ""

# Open browser (non-blocking, ignore failure)
am start -a android.intent.action.VIEW -d http://localhost:5000 >/dev/null 2>&1 &

# Start server in foreground
"$PYTHON" ptos_web.py
