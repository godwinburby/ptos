# Feature Spec: Two Open Fixes (Sync Gate, Windows Single-File Setup)

Two independent, unrelated fixes bundled into one delivery for Big
Pickle. Each is self-contained — build/test separately, bundled here for
convenience only.

- **Part A** — wire up the dead mtime-gate in `ptos_sync.py`'s periodic
  check (currently defined but never called)
- **Part B** — make Windows setup a true single-file download: the `.bat`
  fetches `setup_ptos_windows.ps1` itself if missing, so the user only
  ever downloads one file

**Not included:** Android data migration — handled manually, not by the
setup script.

---

# Part A: Wire up the sync mtime-gate

## Problem (confirmed in the repo)

`ptos_sync.py` already has a correctly-implemented
`folders_changed_since_last_sync(folders, base_dir)` — it compares file
mtimes in the data folders against a saved `.sync_state` timestamp
(written by `_save_state()` after every successful sync). **It's just
never called.** The periodic sync check in `ptos_web.py`'s
`_housekeeping_loop` currently does this:

```python
# current — ptos_web.py, inside _housekeeping_loop, ~line 2561
try:
    sync_cfg = svc.get_sync_config()
    if sync_cfg.get("enabled"):
        import ptos_sync
        result = ptos_sync.run_sync()
        import dataclasses
        _sse_broadcast("sync-status", dataclasses.asdict(result))
except Exception:
    pass
```

This runs a full `rclone bisync` every ~6th tick (~every 30 minutes at
the default 5-minute todo-notify interval) **regardless of whether
anything changed** — exactly the network-call/battery-drain cost the
mtime-gate function was built to avoid.

## Fix — one extra condition, no new function needed

```python
try:
    sync_cfg = svc.get_sync_config()
    if sync_cfg.get("enabled"):
        import ptos_sync
        if ptos_sync.folders_changed_since_last_sync(
            sync_cfg.get("folders", []), ptos.BASE_DIR
        ):
            result = ptos_sync.run_sync()
            import dataclasses
            _sse_broadcast("sync-status", dataclasses.asdict(result))
except Exception:
    pass
```

**Note on the `folders` argument:** since the Android code/data split
means `ptos.BASE_DIR` now resolves to a data-only directory post-
migration, this check can reasonably watch the whole `base_dir` tree
rather than a curated subfolder list — but the function already accepts
a folder list, so just pass `sync_cfg.get("folders", [])` (whatever's
configured in Settings) for now rather than changing the function
signature. Don't broaden this fix into a rewrite of the gate function
itself — it already works correctly, it's only missing a caller.

## Testing requirements

- Two consecutive ticks with no file changes in between: second tick's
  `folders_changed_since_last_sync()` returns `False`, `run_sync()` is
  **not** called, no SSE broadcast fires
- A file changed in one of the watched folders between ticks: next
  eligible tick correctly calls `run_sync()`
- First-ever tick (no `.sync_state` file yet): gate returns `True`
  (already correct in the existing function — just confirm the new call
  site doesn't accidentally suppress this)

# Part B: Windows — true single-file setup download

## Goal

Currently `setup_ptos_windows.bat` is a plain 3-line launcher that
assumes `setup_ptos_windows.ps1` already sits next to it — meaning a new
user has to know to download *both* files. Make the `.bat` fetch the
`.ps1` itself on first run, so a new user only ever needs to download one
file.

## Fix — `setup_ptos_windows.bat`

```bat
@echo off
setlocal
set PS1_PATH=%~dp0setup_ptos_windows.ps1
set PS1_URL=https://raw.githubusercontent.com/godwinburby/ptos/main/setup_ptos_windows.ps1

if not exist "%PS1_PATH%" (
    echo Downloading setup script...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri '%PS1_URL%' -OutFile '%PS1_PATH%'"
    if errorlevel 1 (
        echo ERROR: Could not download setup script. Check your internet connection.
        pause
        exit /b 1
    )
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1_PATH%"
if errorlevel 1 pause
```

**Design choices, both deliberate:**
- **Download-then-run-from-disk, not download-and-execute-in-memory.**
  Not using the `irm <url> | iex` one-liner pattern — saving the file
  first means there's always an inspectable `.ps1` next to the `.bat`,
  and it means it doesn't refetch from the internet on every launch.
- **Only downloads if missing, not on every run.** Once fetched,
  subsequent runs use the local copy — fast, works offline, and doesn't
  duplicate the update-check logic that already lives in
  `start_ptos_windows.bat` (which is explicitly out of scope and staying
  pure batch — see the earlier Windows reliability spec).

**Net result:** a new user downloads exactly one file —
`setup_ptos_windows.bat` — and everything else bootstraps from there.

## Testing requirements

- Fresh machine, only `setup_ptos_windows.bat` present (no `.ps1`):
  running it downloads `setup_ptos_windows.ps1` into the same folder,
  then proceeds through the full setup normally
- Second run, `.ps1` now present: no download attempt, goes straight to
  running the existing local copy
- No internet connection on first run: clear error message, exits
  cleanly, does not proceed to try running a nonexistent `.ps1`
- Confirm `setup_ptos_windows.ps1`'s own logic (Python/Git auto-install,
  PATH refresh, etc. — already implemented in a prior commit) is
  untouched by this change
