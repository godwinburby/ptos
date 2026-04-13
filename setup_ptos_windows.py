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

REPO_URL   = "https://github.com/godwinburby/ptos.git"
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

    # Git is required for Windows (needed for updates)
    if shutil.which("git") is None:
        print("ERROR: Git is required for Windows setup.")
        print("       PTOS uses git to check for updates.")
        print("       Install Git from: https://git-scm.com/download/win")
        print("       Or use 'winget install Git.Git' if you have Windows Package Manager")
        input("\nPress Enter to exit.")
        sys.exit(1)

    step("Cloning PTOS from GitHub")
    rc, out, err = run(["git", "clone", REPO_URL, ptos_dir])
    if rc != 0:
        print(f"Git clone failed: {err}")
        input("\nPress Enter to exit.")
        sys.exit(1)

    print(f"PTOS cloned to: {ptos_dir}")

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
