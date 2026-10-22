# PTOS Spec: Pre-Modularization Readiness

Audit basis: `main` at `36b80db` (2026-10-17). 3,146 tests pass (7 skipped). All numbers below were measured on that commit.

Purpose: fix the bugs and build the safety nets that must exist **before** any code is moved between files, so the split is a mechanical move with no behavior change.

Rule for this phase: no feature work. Behavior changes are limited to the bug fixes in Part A.

---

## Current shape (measured)

| File | Lines | Functions | Coverage |
|---|---|---|---|
| `ptos.py` | 9,277 | 348 | 79% |
| `ptos_service.py` | 7,596 | 274 | 79% |
| `ptos_web.py` | 5,546 | 203 | **58%** |
| `ptos_cli.py` | 3,771 | 74 | **52%** |
| `ptos_todo.py` | 1,362 | n/a | 86% |
| `desktop_app.py` | 279 | n/a | not run (syntax error) |
| `notify_todo.py` | 70 | n/a | 0% |

- Import chain (top level): `ptos` ← `ptos_todo` ← `ptos_service` ← `ptos_web`; `ptos_cli` uses `ptos` and lazily `ptos_service`/`ptos_todo`. One inversion: `ptos.py` lazily imports `ptos_cli` and `ptos_todo`.
- Coupling: `ptos_service` uses 131 distinct `ptos.X` names; `ptos_web` uses 47 `ptos.X` and 162 distinct `svc.X`; `ptos_cli` uses 48 `ptos.X`.
- Tests patch module internals about **1,033** times (`monkeypatch.setattr(ptos…)`), and `ptos.py` has 74 module-level globals (mostly paths).
- `ptos.py` already has 28 section banners (the natural seams, see D3). `ptos_service.py` and `ptos_web.py` have none.
- Large functions: `ptos_cli.main` 619 lines, `save_queries_full` 386, `edit_post` 238, `doctor_check` 234.

---

# Part A: Bugs to fix first

## A1. `desktop_app.py` does not parse

**Cause:** commit `c28c24d` (2026-07-27) mis-indented two lines inside `_Api.close_app`:

```python
        try:
    import ptos_service as svc                      # wrong indent
    port = svc.get_config().get("server", {}).get("port", 5000)   # stray, unused here
            if svc.get_backup_config()...
```

`python -m py_compile desktop_app.py` fails with `IndentationError`. The Windows desktop wrapper cannot start. Tests and CI never compile this file.

**Fix:** restore `            import ptos_service as svc` (12 spaces) and delete the stray `port = ...` line in `close_app`. The correct `port = ...` lines already exist in the `__main__` block.

**Tests:** see A3 (compile gate). Add a smoke test that imports `desktop_app` with `webview`, `pystray` and `PIL` absent (the module already degrades without them) and checks `_Api(5000).close_app` runs without raising when `_destroy_window` is stubbed.

## A2. Four CLI paths raise `NameError`

Pyflakes reports undefined names in `ptos_cli.py`; calling each function confirms the crash.

| Function | Missing name(s) | Reached by |
|---|---|---|
| `_edit_line` (line 3074) | `tempfile` | `-e` on a record |
| `_edit_text` (line 3103) | `tempfile` | `-e config` merge flow |
| `_edit_todo_line` (line 3092) | `format_line`, `parse_todo_line` | `-e` on a todo |
| `_handle_retro_id` (line 2560) | `NOTES_DIR`, `ensure_note_id` | `--retro-id note` |

**Fix:** add `import tempfile`; qualify the rest (`ptos.NOTES_DIR`, `ptos.ensure_note_id`, and `format_line`/`parse_todo_line` from wherever they live now: check `ptos_todo`), or add them to the `from ptos import (...)` list.

**Tests:** one test per path using a no-op editor script in the config (`[editor] command`), asserting the command completes and changes (or doesn't change) the file as expected. Include `--retro-id note --search <text>`.

## A3. Static-analysis gate

**Change:**
1. A test (or CI step) that runs `python -m compileall -q` over every root `*.py` and `scripts/`.
2. A test that runs `pyflakes` (add to `requirements-dev.txt`) over the root modules and **fails on undefined names, redefinitions of unused names, and unused imports**. For existing lower-severity warnings (unused local variables, f-strings without placeholders) record a baseline count per file and fail if the count rises (a ratchet), then clean them as part of Part B.
3. Clean the current findings so the gate starts green: 27 unused imports in `ptos_cli.py`, the redefined `json`, `csv`, `render_group`, `render_pivot` in `ptos_cli.py`, and the redefined `request`, `Response`, `tempfile` in `ptos_web.py`.

**Why it matters:** moving functions between files breaks references in exactly the way A2 shows; this gate is the cheapest safety net for a split.

## A4. SSE leaks one blocked thread per page view (verified)

**Code:** `/api/events` (`ptos_web.py`, about line 4926). The stream loops on `q.get()` with no timeout and sends no heartbeat. It notices a closed client only when it next writes, which happens only on a broadcast (todo-due, reminder, shutdown). Every page loads `sse.js`, which opens an `EventSource`, and nothing closes it explicitly on page unload.

**Measured:** 40 SSE connections opened and then closed by the client. After 8 seconds the server still held 40 client queues and 40 blocked threads. One broadcast cleared them all. On a phone that navigates often, the thread count and memory grow until a broadcast happens, which is a likely contributor to the Android lag.

**Change (server, `api_events`):**
- Replace `q.get()` with `q.get(timeout=_SSE_HEARTBEAT_SECONDS)` (default 15). On `queue.Empty`, yield an SSE comment line (`: ping\n\n`). The write fails on a dead socket, which raises `GeneratorExit` and runs the existing `finally` cleanup.
- Send `retry: 3000\n\n` once at stream start.
- Response headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- Cap concurrent streams (default 32). When the cap is exceeded, put `None` on the oldest client's queue so its stream ends.
- Make `_SSE_HEARTBEAT_SECONDS` a module constant tests can lower.

**Change (client, `sse.js`):**
- Keep the `EventSource` in a variable; call `es.close()` on `pagehide`; recreate it on `pageshow` when `event.persisted` is true (back/forward cache).
- Optional: close the stream when the tab has been hidden for more than 60 seconds and reopen on `visibilitychange`.

**Tests:**
- Open 20 sockets to `/api/events`, close them, and assert `_sse_clients` drops to zero within about 2 × the (lowered) heartbeat, with the thread count returning to baseline.
- Cap test: opening cap + 5 streams keeps `len(_sse_clients) <= cap`.
- A live client still receives a broadcast, and the stream does not emit anything other than `data:` events and comment lines.
- Static check: `sse.js` registers a `pagehide` handler that calls `close()`.

## A5. Lock probe runs in the temp folder

**Problem:** `_run_lock_probe` calls `tempfile.mkstemp(prefix="ptos-lockprobe-", suffix=".lock")` with no `dir=`, so it tests the system temp filesystem, not the data folder. On Termux with data in shared storage that is a different filesystem, so the probe can pass while the data folder's `flock` does not exclude.

**Fix:** pass the data root (or the directory of the first locked path) as `dir=`; skip quietly if it is not writable; `--doctor` probes the same folder.

**Tests:** assert the probe file is created inside the data folder (monkeypatch `tempfile.mkstemp` to record `dir`); the existing no-op lock simulation still downgrades to lock-file mode.

---

# Part B: Repo hygiene (before files move)

## B1. Root markdown

Move into `docs/specs/`: `SPEC-format-v2-quoted-values.md`, `SPEC-status-change-stamp-and-jobsearch-schema.md`, `entity_view_and_funnel_spec.md`, `ptos-charts-spec.md`, `ptos-modularization-shelved.md`, and the new `ptos-*-spec.md` files. Keep in root: `README.md`, `README_START_HERE.md` (or merge), `CHANGELOG.md`, `FORMAT.md`, `AGENTS.md`, `LICENSE`. Fix links and any tests that read those paths.

## B2. Personal-data history scan, and rewrite if needed, **before** the refactor

- Run gitleaks or trufflehog over the full history; review manually the early scripts and templates (`ptos_clinic_add.py`, `ptos_life_add.py`, `templates/`, `system/`) and the commits that mention `hearspeech`.
- If a rewrite is needed, do it now with `git filter-repo` (keep the Gmail author identity, add `.mailmap` for the `godwinburby.gmail.com` typo), then tag.
- After a rewrite every device's checkout diverges: the launchers' `git pull --ff-only` will fail and fall back to the local version. Plan a one-time `git fetch && git reset --hard origin/main` (or a fresh clone) on the phone, the work PC and the home machine.

**Result (2026-10-17): CLEAN — no rewrite needed.** gitleaks/trufflehog were uninstallable (GitHub release CDN unreachable from this machine), so a custom offline scan walked all 740 commits / 2,680 unique blobs with secret + PII regexes: no private keys, AWS/GitHub/Slack/Google/OpenAI tokens, JWTs, URL credentials, or international phone numbers; every `password|secret|token = "..."` hit was the README `yourpassword` placeholder or an HTML `data-token` false positive; the only emails in history are the author's own Gmail and `git@github.com`. No records/journal/todo data file was ever committed. Manual review: `ptos_clinic_add.py` is vocabulary-only (prompts for names at runtime, never stores any), `ptos_life_add.py` carries three family-name vocab tags (`jayden`, `maria`, `mom`), `templates/` and `system/` are generic, `hearspeechpro` appears only in old test fixtures (since removed) and no commit message mentions it. filter-repo, `.mailmap` and the device-reset plan are therefore not triggered; the author-identity typo in old commits stays as-is.

## B3. Update and branch policy

- Do the refactor on a branch (for example `modularize`). The launchers pull `main` on every launch, so half-finished commits on `main` reach every device.
- Tag the baseline (`v0.x-premodular`) so any later regression can be bisected against it.
- Before public sharing, make launcher auto-update opt-in (config flag or environment variable), since anyone cloning the repo would otherwise run whatever lands on `main`.

---

# Part C: Safety nets (before any code moves)

## C1. Coverage floors

- Add `pytest-cov` to `requirements-dev.txt` and a CI step that reports per-file coverage and fails below a floor, raised over time: `ptos_web.py` 58% → 75%, `ptos_cli.py` 52% → 70%, `ptos_service.py` and `ptos.py` stay at 79% or above.
- Smoke tests for `notify_todo.py` (0%) and `desktop_app.py` (A1).

## C2. Characterization tests for what will be split

- **CLI:** a table-driven test that every flag in `build_parser` dispatches to the intended handler (stubbing handlers), plus a golden file of `--help` output so accidental flag changes show up. Break `main` (619 lines) into a dispatch table in the same step, with the golden test guarding it.
- **Web:** a golden file of the route table (rule, methods, endpoint name) and a GET smoke test over every parameterless route with starter data (status below 500). JSON shape snapshots for the key APIs (records, todo, notes save/load, favorites, journal).

## C3. Public-API inventory and guard

- A script generates `docs/api-surface.txt`: every `ptos.X` used by the other modules (131 + 47 + 48 distinct) and every `svc.X` used by `ptos_web` (162 distinct).
- A test fails if any listed name stops resolving on the module that used to provide it. During the split, `ptos.py` and `ptos_service.py` keep re-exporting moved names, so this test stays green and proves nothing was dropped.

## C4. Import-direction rules

- A test that enforces layers: `ptos` (core) imports nothing from `ptos_service`, `ptos_web`, `ptos_cli`; `ptos_todo` imports only `ptos`; `ptos_service` may import `ptos` and `ptos_todo`; `ptos_web` and `ptos_cli` sit on top.
- Remove the inversion: `ptos.py` lazily imports `ptos_cli` and `ptos_todo`. Move the code that needs them to the callers, or pass the dependency in.

---

# Part D: Decisions (with recommendations)

## D1. Globals and test patching

Problem: 74 globals in `ptos.py` plus about 1,033 `monkeypatch.setattr(ptos, …)` calls. After a split, code in a new module that reads `CONFIG_PATH` from its own namespace will ignore a test patching `ptos.CONFIG_PATH`, and tests will pass or fail for the wrong reasons.

Recommendation, as step 0 of the split:
1. Put paths and mutable state in one module (`ptos_paths.py`) that everything reads through module attributes (`ptos_paths.CONFIG_PATH`), never `from … import CONFIG_PATH`.
2. Replace the scattered patches with one fixture (`ptos_home(tmp_path)`) that calls `ptos_paths.set_home(...)`. This is mechanical and can be done before any function moves, shrinking 1,033 patches to a handful.
3. Keep `ptos.CONFIG_PATH` and the other old names available as read-through aliases only while the migration runs, then remove.

## D2. Layout and portability

- Recommendation: **flat modules in the root** (`ptos_time.py`, `ptos_locking.py`, …), matching the current `ptos_*.py` convention. A `ptos/` package cannot coexist with a root `ptos.py` and would change launchers, the PyInstaller spec, `desktop_app.py` imports and every test import at once.
- Keep your portable CLI promise with a build step: `scripts/build_pyz.py` uses the standard-library `zipapp` to produce a single `ptos-cli.pyz` from the core and CLI modules. It runs with only Python, no install. Add a test that builds it and runs `--version`.
- Keep the module list in `tests/test_ci_workflow.py` and the PyInstaller spec in sync with the new files.

## D3. Order of extraction (lowest coupling first)

Source: the section banners in `ptos.py` (line counts approximate).

1. Time engine (363) and favorites writer (342): few globals.
2. Demo data (825) and doctor (274).
3. Backups (313) and external change detection (567).
4. File locking (324) and atomic writes (517): high value, many callers; keep re-exports.
5. Notes (261) and journal (139).
6. Cross-record links (382).
7. Record parsing (761), validation (807), query engine (174), analysis (150), dashboards (333): the core data path; do last, with the most tests.
8. Schema helpers and schema interpreter (834) and interactive prompts (143).

Then `ptos_service.py`: add section banners first, group the 274 functions by domain (records, todo, notes, journal, favorites, config, backup, queries/dashboards), and split by domain. Then `ptos_web.py`: split into Flask blueprints along the same domains, with shared helpers (auth, Origin guard, error mapping, gzip) in a small `ptos_web_common.py`. Do the CLI last, after `main` is a dispatch table.

## D4. Commit discipline

- One extraction per commit; **move only, no edits** in the same commit (keep real changes in separate commits so review and blame stay readable).
- Each commit leaves the full suite, the pyflakes gate, the API-surface guard and the layer test green.
- Mention the source file and line range in each commit message, since function-level blame does not follow a move.
- After every few extractions, rerun coverage to confirm no file's floor dropped.

---

# Order and effort

| Step | Items | Estimate |
|---|---|---|
| 1 | A1, A2, A3 (bugs and gate) | half a day |
| 2 | A4, A5 (SSE, probe) | half a day to a day |
| 3 | B1, B2, B3 (docs, history, branch policy) | half a day, plus device resets |
| 4 | C1–C4 (coverage floors, golden tests, API guard, layers) | 2–3 days |
| 5 | D1 (paths module and fixture) | 1–2 days |
| 6 | D2–D4 (extractions, in the order above) | incremental |

# Definition of done (ready to start moving code)

- `compileall` and pyflakes gates pass with zero undefined names and zero unused imports.
- All five Part A items fixed and tested; `desktop_app.py` imports.
- Coverage floors in place and met; CLI and web golden tests exist.
- API-surface file and layer test exist and pass.
- The path/state fixture replaces the bulk of the `monkeypatch.setattr(ptos…)` patches.
- History scan done (and rewrite finished if needed); root docs moved; baseline tagged; work happens on a branch.

# Not verified

CI status on the Windows runner; the real-device effect of the SSE fix (the leak itself was reproduced on Linux); how `ptos_service.py` and `ptos_web.py` divide by domain, since neither has section banners yet; the full behavior of `desktop_app.py` beyond the syntax error.
