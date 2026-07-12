# Feature Spec: Windows Setup Reliability (Setup Consolidation + Error Handling)

Two independent fixes bundled into one delivery for Big Pickle, both
surfaced from the same troubleshooting thread (the `presets.toml` crash
on Windows). They touch different files and can be built/tested
separately — bundled here for convenience, not because they depend on
each other.

- **Part A** — consolidate Windows setup into one PowerShell script +
  auto-install Python/Git
- **Part B** — global error handler so config errors (like the alias
  line-42 bug) show a clean message instead of crashing

---

# Part A: Windows Setup — Auto-install Dependencies + Single-File Consolidation

## Goal (merges two prior asks into one deliverable)

Two things Godwin asked for, now rolled into one spec since they solve
the same underlying problem together:

1. **Auto-install Python and Git** on Windows via `winget`, instead of
   erroring out with manual install instructions — bringing Windows to
   parity with how Linux/Android setup scripts already handle missing
   dependencies.
2. **Consolidate `setup_ptos_windows.bat` + `setup_ptos_windows.py`** into
   a single `setup_ptos_windows.ps1`, matching the one-file model
   `setup_ptos_linux.sh` and `setup_ptos_android.sh` already use.
   PowerShell ships by default on every Windows 7+ machine — no install
   step, no chicken-and-egg problem — and has proper string handling,
   HTTP requests, and process management that `cmd.exe`/batch genuinely
   lacks. This is also what makes goal #1 clean to implement: PowerShell
   can install Python/Git *and* refresh its own session's PATH afterward,
   which batch cannot do reliably.

**Supersedes** the earlier standalone "winget auto-install for the
existing .bat+.py split" spec — that approach is dropped in favor of
doing the auto-install inside the new consolidated `.ps1` directly.

**Important scope note:** this does not reduce Windows to *literally* one
file. Double-clicking a `.ps1` in Explorer opens it in a text editor
rather than running it, so a minimal `.bat` launcher stub is still
required. That stub does nothing but hand off to PowerShell — it has no
branching or parsing logic, so it doesn't carry the fragility the current
`.bat` has.

---

## 1. `setup_ptos_windows.bat` — shrinks to a pure launcher

```bat
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_ptos_windows.ps1"
if errorlevel 1 pause
```

- `-ExecutionPolicy Bypass` applies only to this one invocation, not a
  system-wide policy change — no admin rights needed, nothing persisted
- No Python detection, no branching — this file can no longer be the
  source of the "batch has issues" class of bug, because it no longer
  does anything nontrivial

---

## 2. `setup_ptos_windows.ps1` — full logic, mirrors `setup_ptos_linux.sh`

### Python detection + auto-install
```powershell
function Get-PythonCmd {
    foreach ($cmd in @("py", "python")) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            $ver = & $cmd -c "import sys; print(sys.version_info>=(3,11))" 2>$null
            if ($ver -eq "True") { return $cmd }
        }
    }
    return $null
}

$python = Get-PythonCmd
if (-not $python) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Python not found. Installing via winget..."
        winget install -e --id Python.Python.3.13 --silent `
            --accept-package-agreements --accept-source-agreements --scope user

        # Refresh PATH in this session from the registry, no reopen needed
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        $python = Get-PythonCmd
    }
    if (-not $python) {
        Write-Host "ERROR: Python 3.11+ is required."
        Write-Host "Install it from https://python.org/downloads (tick 'Add to PATH'),"
        Write-Host "or close this window and re-run setup if you just installed it."
        Read-Host "Press Enter to exit"
        exit 1
    }
}
Write-Host "Using $python"
```

**PATH refresh — a genuine improvement over the batch/`.py` approach:**
PowerShell can re-read the registry-persisted `Path` values
(`[System.Environment]::GetEnvironmentVariable(..., "Machine"/"User")`)
and reassign `$env:Path` directly in the current session, without
reopening the terminal. This works because winget's install is
synchronous — the registry write completes before the command returns —
so re-reading immediately after is reliable. Still fall back to "close
and re-run" as the final safety net in case a given installer doesn't
register PATH in a way this catches, but this should be the exception,
not the normal path.

### Git detection + auto-install — same pattern
```powershell
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Git not found. Installing via winget..."
        winget install -e --id Git.Git --silent `
            --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: Git is required for Windows setup."
        Write-Host "Install from: https://git-scm.com/download/win"
        Write-Host "(You may need to close this window and re-run after installing.)"
        Read-Host "Press Enter to exit"
        exit 1
    }
}
```
Same UAC caveat as before: Git's installer may prompt for elevation
regardless of `--silent` on winget's own side — mention this once in the
printed output rather than promising a fully silent run.

### Locate or clone PTOS
```powershell
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ptosDir = if (Test-Path "$scriptDir\ptos.py") { $scriptDir } else { "$scriptDir\ptos" }

if (-not (Test-Path "$ptosDir\ptos.py")) {
    Write-Host "Cloning PTOS from GitHub..."
    git clone https://github.com/godwinburby/ptos.git $ptosDir
}
Set-Location $ptosDir
```

### Flask install (with retry, matching current `.py` behavior)
```powershell
& $python -m pip install flask tomli-w --quiet
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install flask tomli-w
}
```

### Init (first run only) + name prompt
Same as current `.py` logic — check for `config/`, run `ptos.py --init`,
prompt for name, run `ptos.py --set-name`.

### Port 5000 cleanup — this is where PowerShell is a clear upgrade
```powershell
$conn = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    Write-Host "Stopping existing process on port 5000..."
    Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
```
Replaces the current `netstat -ano` text-parsing + manual token-splitting
+ `taskkill` approach with a single structured cmdlet call — this was
exactly the class of fragile string-parsing the `.py` file existed to
avoid.

### Start server, poll, open browser
```powershell
$proc = Start-Process -FilePath $python -ArgumentList "ptos_web.py" -PassThru -NoNewWindow

Write-Host "Waiting for server" -NoNewline
for ($i = 0; $i -lt 15; $i++) {
    try {
        Invoke-WebRequest -Uri "http://localhost:5000" -TimeoutSec 1 -UseBasicParsing | Out-Null
        break
    } catch {
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 1
    }
}
Write-Host ""
Start-Process "http://localhost:5000"

try {
    Wait-Process -Id $proc.Id
} catch {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}
```
`Invoke-WebRequest` replaces the `.py` file's `urllib.request` polling
loop — same behavior, now native to the single script instead of
requiring Python for HTTP.

---

## 3. Companion file: `start_ptos_windows.bat` / `.ps1`

If a separate start script exists for subsequent runs (referenced in the
current `.py` output: *"To start PTOS next time: start_ptos_windows.bat"*),
apply the same pattern: trivial `.bat` stub launching a `.ps1` with the
actual update-check + launch logic, for consistency.

---

## 4. Files removed

- `setup_ptos_windows.py` — fully replaced, delete after migration
- No change to `setup_ptos_linux.sh` / `setup_ptos_android.sh`

---

## How It Works (plain English)

Windows setup now works like Linux and Android's — one real script file
containing all the logic, instead of splitting it between a batch file
and a Python file. The only Windows-specific quirk is that a `.ps1` file
can't be double-clicked directly (Windows opens it in a text editor
instead of running it), so a tiny 3-line batch file exists purely to
launch the PowerShell script — it has no logic of its own, so it can't be
a source of bugs the way the old batch file was.

If Python or Git is missing, the script installs them automatically using
Windows' built-in package manager, then immediately re-reads the system's
PATH so it can typically continue without needing you to reopen the
window — a real improvement over the previous approach, which always
needed a manual re-run.

---

## Testing requirements (mandatory)

- Fresh Windows sandbox, nothing installed: `setup_ptos_windows.bat` →
  `.ps1` installs Python via winget, PATH refresh succeeds without
  reopening, script continues straight through to Git check, clone,
  Flask install, init, and server launch in one run
- Same, but simulate PATH refresh not picking up the new install: script
  falls back to "close and re-run" message, second run completes
  successfully
- Git missing only: same auto-install + refresh pattern, verified
  independently of the Python path
- `winget` unavailable: both Python and Git fall back to today's manual
  install messages, unchanged wording
- Port 5000 already occupied by another process: `Get-NetTCPConnection`
  correctly identifies and stops it before server launch
- Ctrl+C during server run: child Python process is terminated cleanly,
  no orphaned `python.exe` left running
- Confirm `-ExecutionPolicy Bypass` in the `.bat` stub does not alter the
  system's persistent execution policy (check `Get-ExecutionPolicy`
  before and after — should be unchanged)
- Confirm behavior is identical whether launched via double-click on
  `setup_ptos_windows.bat` or by running the `.ps1` directly in an
  already-open PowerShell terminal

---

# Part B: Global Error Handler for PTOSError

## Root cause (confirmed)

`ptos.py`'s `_load()` already validates TOML syntax correctly and produces
a clean, specific message on failure (e.g. "Config error in presets.toml:
Expected newline or end of document after a statement (at line 42, column
14)"). That message is converted into a `PTOSError` via `_safe_exit()` in
`ptos_service.py`.

**The gap:** nothing in `ptos_web.py` catches `PTOSError`. It falls
through to Flask's default handling and renders Werkzeug's raw debugger
page — full traceback, interactive console — instead of the clean message
that was already generated. This affects every one of the ~30 call sites
across `ptos_service.py` that raise `PTOSError` (bad presets, bad due
config, missing alias targets, invalid queries, malformed schema, etc.),
not just presets.toml. Confirmed example: the `[presets.co] alias =
"coffee"` line — a table header and a key-value pair on the same line,
which TOML doesn't allow — was correctly caught by the parser; the
resulting `PTOSError` just never reached the user as anything readable.

**This spec does not change the TOML parser or add a new validator.** The
existing syntax validation already works. This is purely about catching
an already-correct error and displaying it properly.

---

## 1. Two response shapes needed

The app has two different route styles, and the handler must serve both
correctly:

- **Page routes** (`home`, `/todo`, `/journal`, `/browse`, `/due`, etc.) —
  no local try/except around service calls today. A `PTOSError` here
  should render a full friendly HTML error page.
- **AJAX/API routes** (`/todo/add`, `/records/add`, etc.) — many of these
  already have local try/except returning
  `jsonify({"success": False, "error": str(e)}), 500`. Those are already
  safe. The global handler is a backstop for any route — present or
  future — that doesn't have its own local catch.

The global handler must detect which shape to return, so it doesn't break
the JSON contract the frontend JS already expects from AJAX calls.

---

## 2. Implementation — `ptos_web.py`

```python
from ptos_service import PTOSError

def _wants_json():
    return (
        request.path.startswith("/api/")
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )

@app.errorhandler(PTOSError)
def handle_ptos_error(e):
    app.logger.warning(f"PTOSError on {request.path}: {e}")
    if _wants_json():
        return jsonify({"success": False, "error": str(e)}), 500
    return render_template("error.html", message=str(e)), 500

@app.errorhandler(Exception)
def handle_unexpected_error(e):
    app.logger.error(f"Unhandled exception on {request.path}: {e}", exc_info=True)
    if _wants_json():
        return jsonify({"success": False, "error": "Something went wrong."}), 500
    return render_template("error.html",
        message="Something went wrong. Check the server log for details."), 500
```

**Two handlers, deliberately different behavior:**
- `PTOSError` messages are already sanitized/intentional (written by the
  app itself to be user-readable) — safe to show verbatim.
- A generic `Exception` catch-all is a second, separate handler for truly
  unexpected crashes (a real bug, not a config problem). These should
  **never** show the raw exception text or traceback to the user — only
  a generic message — while the full traceback still goes to the server
  log via `exc_info=True`, so it's not lost, just not exposed in the
  browser. This also closes the broader exposure risk of Werkzeug's
  interactive debugger ever appearing to a user, regardless of exception
  type.

Adjust the exact JSON-detection check in `_wants_json()` to match
whatever convention the existing fetch calls in the templates already
use (check what header/path pattern the JS `fetch()` calls send today —
match that, don't introduce a new convention).

---

## 3. New template: `error.html`

Should match existing visual language — same base layout, `.card`
container, same typography/spacing as other pages, not a bare Flask
default error page. Structure:

- Same page shell/nav as other pages (so the user isn't dropped into a
  totally different-looking screen)
- A `.card` with:
  - Short heading, e.g. "Something needs fixing"
  - The message, rendered as plain text (never `|safe`, since messages
    can echo back file paths/user data — no HTML injection risk)
  - A single action: link back to `/` (Home)
- No traceback, no debug console, ever — regardless of Flask's debug
  setting

---

## 4. Verify debug mode

Confirm the app is never launched in a way that enables Werkzeug's
interactive debugger — the code already sets `app.run(debug=False, ...)`
in `ptos_web.py`, but the crash you hit shows the interactive debugger
console, meaning something in that run (likely `flask run` with
`FLASK_DEBUG` set in the environment, or a different launch path) was
overriding it. Add an explicit safeguard so this can't silently happen
again:

```python
app.config["DEBUG"] = False
```
set explicitly at app creation time, not just passed to `.run()` — this
protects against the case where the app is launched via `flask run`
(which doesn't go through the `app.run()` call at the bottom of
`ptos_web.py` at all) or via `desktop_app.py`'s separate `app.run()` call,
which currently doesn't pass `debug=` either way.

---

## How It Works (plain English)

PTOS already correctly detects broken config files — that part isn't
changing. What's missing is the last step: showing you the answer instead
of a scary crash screen. This adds one place in the app that catches
those already-correct error messages and displays them as a normal page,
using the same look as the rest of PTOS. A second, separate catch-all
handles any truly unexpected bug the same way — safe generic message on
screen, full details still logged on the server so nothing is lost for
debugging later.

---

## Testing requirements (mandatory)

- A malformed `presets.toml` (e.g. table header + key-value on one line)
  hit via a page route (`/`) renders `error.html` with the exact
  `PTOSError` message, not a traceback
- Same malformed file hit via an AJAX route returns
  `{"success": false, "error": "..."}` with status 500, not HTML
- A genuinely unexpected exception (e.g. mock a `TypeError` inside a
  service call) renders the generic "Something went wrong" message via
  `error.html` — never the raw exception text — while the full traceback
  appears in the server log
- Existing routes that already have local try/except → jsonify continue
  to behave exactly as before (global handler doesn't double-handle
  already-caught exceptions)
- Confirm `app.config["DEBUG"]` is `False` regardless of launch method
  (`python ptos_web.py`, `flask run`, `desktop_app.py`)
- Manual regression: intentionally reintroduce the `[presets.co] alias =
  "coffee"` one-line bug, confirm the app boots (config errors happen at
  request time via `_load()`'s cache, not at process startup, so the app
  itself doesn't fail to start — only the specific page/route touching
  that file does) and shows the clean error page instead of crashing
