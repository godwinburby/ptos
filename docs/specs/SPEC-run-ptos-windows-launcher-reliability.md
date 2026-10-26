# SPEC: Windows `run_ptos` launcher — reliable install and launch

**Project:** PTOS  
**Files:** `run_ptos.ps1` (primary), `run_ptos.bat` (bootstrap only)  
**Optional follow-up:** align `run_ptos_linux.sh` / `run_ptos_android.sh` with the same dependency gate  
**Priority:** P0 — fresh Windows machines fail to get a running app without manual Python/pip steps  

---

## Problem (observed on a fresh Windows PC)

1. User expected winget to install Python; detection after install failed or felt skipped; Git via winget worked.
2. App started without full deps → **crash** (not a clear error). Missing packages included at least **Flask** and **tomli-w**.
3. `python -m pip` failed or targeted the wrong environment; **`py -m pip`** worked (Windows Python launcher).
4. Current script only gates on `import flask`. If Flask is present and **tomli-w** (or any other requirement) is missing, **pip is skipped** entirely.
5. Failed `pip install` is only a WARNING; script still launches `ptos_web.py`.

---

## Goals

| Goal | Detail |
|------|--------|
| Hands-off first run | Python 3.11+, Git, and all of `requirements.txt` installed or clear hard-fail instructions |
| One interpreter | Same command for version check, pip, `ptos.py`, and `ptos_web.py` |
| Prefer `py` | Then fall back to a real `python` (not Store stub) |
| Full deps | Never key only on Flask |
| Fail loud | Do not start the web server if runtime imports fail |
| No behavior change for happy path | Existing installs that already work keep working |

## Non-goals

- Switching default package manager to Scoop (optional fallback only if already documented elsewhere — **out of scope** unless trivial).
- Security hardening of `GIT_SSL_NO_VERIFY` (separate change; do not expand scope unless one-line removal is trivial and tested).
- Fixing todo-list UI bugs (separate issue).
- venv-by-default (optional later; not required here).

---

## Current behavior (baseline)

`run_ptos.ps1` approximately:

1. `Get-PythonCmd`: try `py`, then `python`; require 3.11+.
2. If missing → `winget install Python.Python.3.13` (user scope) → refresh PATH → detect again.
3. Git: winget `Git.Git` if missing.
4. Clone repo if needed.
5. Set `PTOS_HOME` from `.ptos_home` or sibling `ptos-data`.
6. If `import flask` fails → `pip install -r requirements.txt` (may warn and continue).
7. `--init` if no config; sync-check; git pull; free port; start `ptos_web.py`.

---

## Required behavior

### 1. Python resolution (`Get-PythonCmd` or replacement)

Try **in order**, first match with `sys.version_info >= (3, 11)` wins:

1. `py -3.13` (if `py` exists; ignore failures)
2. `py -3.12`
3. `py -3` (launcher default 3.x if ≥ 3.11)
4. `py`
5. `python` (must pass version check; must not be a stub that fails `-c "import sys"`)

Return the **exact string/args** to invoke later (e.g. `py`, or `py -3.13`).  
Implementation note: if the command is multi-token (`py -3.13`), store as array or always invoke via a small helper:

```powershell
function Invoke-PtosPython([string[]]$PythonCmd, [string[]]$Args) {
    & $PythonCmd[0] @($PythonCmd[1..($PythonCmd.Length-1)] + $Args)
}
```

Or normalize to a single executable path via `py -3.13 -c "import sys; print(sys.executable)"` and use that path for the rest of the script (preferred for simplicity).

**Preferred normalization:**

```text
After selecting a working launcher invocation:
  $pythonExe = output of: <launcher> -c "import sys; print(sys.executable)"
  Use $pythonExe for all later steps (pip, init, web).
```

This avoids multi-token command issues.

### 2. After winget install of Python

1. Refresh Machine + User PATH into `$env:Path` (keep).
2. Re-run full detection (section 1), including `py -3.13` / `py -3`.
3. If still not found, try common install locations (if present and 3.11+), e.g.:
   - `$env:LocalAppData\Programs\Python\Python313\python.exe`
   - `$env:LocalAppData\Programs\Python\Python312\python.exe`
   - `$env:LocalAppData\Programs\Python\Python311\python.exe`
4. If still not found:
   - Print that winget was attempted
   - Print: close this window and run `run_ptos.bat` again
   - Print manual: `winget install -e --id Python.Python.3.13`
   - **exit 1** (do not continue)

### 3. Git (keep behavior, clearer failure)

Keep winget install for Git when missing. PATH refresh. If still missing → exit 1 with message (already largely correct).

### 4. Dependency install (replace Flask-only gate)

**Runtime check** — success only if all succeed:

```text
import flask
import tomli_w
```

If `requirements.txt` gains more packages later, either:

- parse and document that the check must stay in sync, or  
- prefer: always run pip, then check the known critical imports listed in this SPEC / requirements.

**Install algorithm:**

```text
if runtime imports fail OR env PTOS_FORCE_PIP=1:
  Write-Step installing dependencies
  & $pythonExe -m pip install -r "<ptosDir>\requirements.txt"
  if pip failed:
    re-run without --quiet (show errors)
    print exact command for the user
    exit 1
  re-check runtime imports
  if still fail:
    print error + exact command
    exit 1
else:
  optional: skip pip (fast daily launch)
```

**Rules:**

- Always use `$pythonExe -m pip`, never bare `pip`.
- Do **not** continue to start the server on import failure.
- First attempt may use `--quiet`; on failure, retry verbose.

**Minimum packages** (must match repo `requirements.txt` at implement time; verify file):

- `flask`
- `tomli-w` (import name `tomli_w`)

### 5. Do not start the app on soft dependency failure

Remove the path that prints WARNING and still runs `ptos_web.py`.

Before starting the server, run runtime import check once more; exit 1 on failure.

### 6. Launch

Keep existing: init, name prompt, sync-check, update pull, port handling, start web, open browser.

Use `$pythonExe` for:

- `ptos.py --init` / `--set-name` / `--sync-check`
- `ptos_web.py`

### 7. `run_ptos.bat`

No functional change required except ensuring it still invokes the updated `.ps1`.  
If the `.ps1` is missing, download behavior may remain as today (out of scope to redesign).

---

## Messages (user-facing)

**Python missing after winget:**

```text
ERROR: Python 3.11+ was not found after installation.
1. Close this window completely.
2. Run run_ptos.bat again.
Or install manually: winget install -e --id Python.Python.3.13
```

**Deps failed:**

```text
ERROR: Could not install Python packages required by PTOS.
Run this exact command, then re-run run_ptos.bat:

  "<pythonExe>" -m pip install -r "<ptosDir>\requirements.txt"
```

**Deps missing at launch:**

```text
ERROR: PTOS dependencies are missing (flask / tomli-w).
```

---

## Testing checklist

### Automated (if feasible in repo)

- Unit-style: pure functions for version parsing hard to test in CI on Windows only — optional.
- Document manual tests as required acceptance.

### Manual (Windows)

1. **Clean deps:** With Python present, uninstall flask/tomli-w from that env → run launcher → packages installed → server starts.  
2. **Flask present, tomli-w missing:** Must install (not skip) → start.  
3. **pip failure:** Simulate bad network or typo path → script exits non-zero, does not start server.  
4. **py only:** Machine where `py` works and `python` does not → launcher uses `py` / resolved executable end-to-end.  
5. **python only:** Old layout with only `python` 3.11+ on PATH → still works.  
6. **Daily launch:** Deps already OK → no unnecessary failure; optional skip of pip OK.  
7. **Friend path:** After winget Python in same session, either finds interpreter or exits with re-run message (no silent continue).

### Regression

- Existing configured `ptos-data` / `.ptos_home` still used.  
- Git clone / pull paths unchanged in intent.  
- Linux/Android not required for this SPEC; optional parity note in CHANGELOG.

---

## Acceptance criteria

- [ ] Dependency gate is **not** Flask-only; **tomli-w** (and flask) must import before server start.
- [ ] Failed pip or failed imports → **exit 1**, server not started.
- [ ] All Python invocations use the same resolved interpreter (`sys.executable` or equivalent).
- [ ] Prefer `py` / `py -3.x` over `python` when both exist and meet 3.11+.
- [ ] After winget Python install, improved re-detect OR explicit re-run message; no silent continue without Python.
- [ ] Uses `-m pip install -r requirements.txt` against repo file.
- [ ] CHANGELOG entry under a clear Windows launcher / setup heading.
- [ ] AGENTS.md one-line note if launchers are documented there (optional but preferred).

---

## Implementation order

1. Resolve `$pythonExe` via ordered detection + `sys.executable`.  
2. Replace Flask-only block with full dep check + hard fail.  
3. Harden post-winget Python detection + messages.  
4. Wire all later `& $python ...` calls to `$pythonExe`.  
5. Manual test checklist; CHANGELOG.

---

## Out of scope (do not block this SPEC)

- Scoop fallback  
- Todo page empty-list bug  
- Removing `GIT_SSL_NO_VERIFY` (recommend separate PR)  
- Port-kill process matching  
- Creating a venv by default  

---

## Summary for implementer

> Fresh Windows must get Python (winget + robust detect), then **`"$pythonExe" -m pip install -r requirements.txt`**, then prove **`import flask` and `import tomli_w`**, or **exit with the exact command**. Never start PTOS with missing runtime deps. Prefer **`py`**, fall back to **`python`**, one interpreter for everything.
