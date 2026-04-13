"""
PTOS Update Script for Windows (non-git fallback)
Called by update_ptos_windows.bat when .git folder is not present.
Downloads the latest ZIP, preserves config/ records/ journal/, copies new code.
"""

import sys
import os
import subprocess
import shutil
import urllib.request
import zipfile
import tempfile

ZIP_URL  = "https://github.com/godwinburby/ptos/archive/refs/heads/main.zip"
PRESERVE = {"config", "records", "journal", "exports", "backups"}


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


ptos_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(ptos_dir)

# ── Download ──────────────────────────────────────────────────────────────────
print("Downloading latest PTOS...")
tmp_zip = os.path.join(tempfile.gettempdir(), "ptos_update.zip")
try:
    urllib.request.urlretrieve(ZIP_URL, tmp_zip)
except Exception as e:
    print(f"ERROR: Download failed: {e}")
    sys.exit(1)

# ── Verify ────────────────────────────────────────────────────────────────────
print("Verifying download...")
try:
    with zipfile.ZipFile(tmp_zip, "r") as zf:
        bad = zf.testzip()
        if bad:
            print(f"ERROR: Corrupted download ({bad}). Try again.")
            os.remove(tmp_zip)
            sys.exit(1)
except zipfile.BadZipFile:
    print("ERROR: Downloaded file is not a valid ZIP.")
    os.remove(tmp_zip)
    sys.exit(1)

# ── Extract ───────────────────────────────────────────────────────────────────
print("Extracting...")
tmp_dir = os.path.join(tempfile.gettempdir(), "ptos_update_extract")
if os.path.exists(tmp_dir):
    shutil.rmtree(tmp_dir)
with zipfile.ZipFile(tmp_zip, "r") as zf:
    zf.extractall(tmp_dir)
os.remove(tmp_zip)

src_dir = os.path.join(tmp_dir, "ptos-main")
if not os.path.isdir(src_dir):
    print("ERROR: Unexpected ZIP structure.")
    shutil.rmtree(tmp_dir)
    sys.exit(1)

# ── Check for changes ─────────────────────────────────────────────────────────
import filecmp

changed = False
for fname in os.listdir(src_dir):
    src = os.path.join(src_dir, fname)
    dst = os.path.join(ptos_dir, fname)
    if fname in PRESERVE:
        continue
    if not os.path.exists(dst):
        changed = True
        break
    if os.path.isfile(src) and not filecmp.cmp(src, dst, shallow=False):
        changed = True
        break

if not changed:
    print("Already up to date.")
    shutil.rmtree(tmp_dir)
    sys.exit(0)

# ── Apply update — copy everything except preserved folders ───────────────────
print("Applying update...")
for fname in os.listdir(src_dir):
    if fname in PRESERVE:
        continue
    src = os.path.join(src_dir, fname)
    dst = os.path.join(ptos_dir, fname)
    if os.path.isdir(src):
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)

shutil.rmtree(tmp_dir)
print("Update complete.")
