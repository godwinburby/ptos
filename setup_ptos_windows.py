"""
PTOS Setup Script for Windows
Handles: Python version check, Git check/install hint, clone or locate repo,
         Flask install, ptos --init, then launches the web server.
Run via:  setup_ptos_windows.bat   (which finds Python first)
"""

import sys
import os
import subprocess
import time
import webbrowser
import shutil
import urllib.request
import zipfile
import tempfile

REPO_URL   = "https://github.com/godwinburby/ptos.git"
ZIP_URL    = "https://github.com/godwinburby/ptos/archive/refs/heads/main.zip"
MIN_PYTHON = (3, 11)


def banner(text):
    print()
    print("=" * 42)
    print(f"  {text}")
    print("=" * 42)


def step(text):
    print(f"\n--- {text} ---")


def run(cmd, **kwargs):
    """Run a command, return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, **kwargs
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


# ── 1. Python version ─────────────────────────────────────────────────────────
if sys.version_info < MIN_PYTHON:
    print(f"ERROR: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required.")
    print(f"       You are running Python {sys.version_info.major}.{sys.version_info.minor}.")
    print("       Download the latest version from https://python.org/downloads")
    input("\nPress Enter to exit.")
    sys.exit(1)

print(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} — OK")

# ── 2. Locate PTOS directory ──────────────────────────────────────────────────
script_dir = os.path.dirname(os.path.abspath(__file__))

if os.path.isfile(os.path.join(script_dir, "ptos.py")):
    ptos_dir = script_dir
    print(f"PTOS found at: {ptos_dir}")
else:
    ptos_dir = os.path.join(script_dir, "ptos")
    if os.path.isfile(os.path.join(ptos_dir, "ptos.py")):
        print(f"PTOS found at: {ptos_dir}")
    else:
        ptos_dir = None

# ── 3. Download PTOS if not found ─────────────────────────────────────────────
if ptos_dir is None:
    ptos_dir = os.path.join(script_dir, "ptos")

    # Try git clone first
    git_ok = shutil.which("git") is not None
    if git_ok:
        step("Cloning PTOS from GitHub")
        rc, out, err = run(["git", "clone", REPO_URL, ptos_dir])
        if rc != 0:
            print(f"Git clone failed: {err}")
            git_ok = False

    if not git_ok:
        # Fallback: download ZIP
        step("Downloading PTOS ZIP from GitHub")
        tmp_zip = os.path.join(tempfile.gettempdir(), "ptos_setup.zip")
        try:
            print(f"Downloading {ZIP_URL} ...")
            urllib.request.urlretrieve(ZIP_URL, tmp_zip)
        except Exception as e:
            print(f"ERROR: Download failed: {e}")
            print("Check your internet connection and try again.")
            input("\nPress Enter to exit.")
            sys.exit(1)

        print("Extracting...")
        tmp_dir = os.path.join(tempfile.gettempdir(), "ptos_setup_extract")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            zf.extractall(tmp_dir)
        os.remove(tmp_zip)

        # GitHub ZIP extracts to ptos-main/
        extracted = os.path.join(tmp_dir, "ptos-main")
        if not os.path.isdir(extracted):
            print("ERROR: Unexpected ZIP structure.")
            input("\nPress Enter to exit.")
            sys.exit(1)

        shutil.copytree(extracted, ptos_dir)
        shutil.rmtree(tmp_dir)
        print(f"PTOS installed to: {ptos_dir}")

os.chdir(ptos_dir)

# ── 4. Install Flask ───────────────────────────────────────────────────────────
step("Installing Flask")
rc, out, err = run(
    [sys.executable, "-m", "pip", "install", "flask", "--quiet"],
)
if rc != 0:
    # Try without --quiet in case it's a flag issue
    rc, out, err = run([sys.executable, "-m", "pip", "install", "flask"])
    if rc != 0:
        print(f"WARNING: Flask install may have failed.\n{err}")
        print("You can try manually:  py -m pip install flask")
    else:
        print("Flask installed.")
else:
    print("Flask ready.")

# ── 5. Initialise PTOS ────────────────────────────────────────────────────────
config_dir = os.path.join(ptos_dir, "config")
if not os.path.isdir(config_dir):
    step("Initialising PTOS")
    rc, out, err = run([sys.executable, "ptos.py", "--init"])
    if rc != 0:
        print(f"ERROR: ptos --init failed:\n{err}")
        input("\nPress Enter to exit.")
        sys.exit(1)
    print("PTOS initialised.")
else:
    print("PTOS already initialised (config/ exists).")

# ── 6. Kill anything on port 5000 ────────────────────────────────────────────
step("Checking port 5000")
rc, out, _ = run(["netstat", "-ano"])
for line in out.splitlines():
    if ":5000" in line and "LISTENING" in line:
        parts = line.split()
        if parts:
            pid = parts[-1]
            run(["taskkill", "/F", "/PID", pid])
            print(f"Stopped process {pid} on port 5000.")
print("Port 5000 ready.")

# ── 7. Start Flask and open browser ──────────────────────────────────────────
banner("Starting PTOS Web Server")
print("Open in browser: http://localhost:5000")
print("Press Ctrl+C in this window to stop the server.")
print()
print("To start PTOS next time:  start_ptos_windows.bat")
print("To update PTOS:           update_ptos_windows.bat")
print()

flask_proc = subprocess.Popen(
    [sys.executable, "ptos_web.py"],
    cwd=ptos_dir,
)
time.sleep(2)
webbrowser.open("http://localhost:5000")

try:
    flask_proc.wait()
except KeyboardInterrupt:
    flask_proc.terminate()
    print("\nServer stopped.")
