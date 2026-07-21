# AGENTS.md — PTOS Development Guide

## Project overview

PTOS (Plain Text Operating System) is a plain-text life-logging and task management system. Core philosophy: no database, no cloud — just `.log` files, one line per record, TOML config, and a Flask web UI.

## Architecture

```
ptos.py          → Core engine (file I/O, parsing, analysis, CLI logic)
ptos_cli.py      → CLI argument parser and entry point
ptos_service.py  → Service layer (bridges web UI and engine, structured API responses)
ptos_web.py      → Flask web app (routes, SSE, background threads)
ptos_todo.py     → Todo module (todo.txt parser, CRUD, archiving, notifications)
web_templates/   → Jinja2 HTML templates
web_static/      → CSS, JS, icons
tests/           → pytest test suite
starters/        → Starter configs shipped with project (7 types, 15 queries, 15 presets)
```

Data lives in a separate `ptos-data/` directory (sibling to repo):
```
ptos-data/
config/          → User config (created by --init, gitignored)
records/         → Log files (YYYY.log)
journal/         → Markdown journal entries
todo/            → Todo files (todo.txt, done.txt, done.YYYY.txt)

ptos-backups/    → ZIP backups (sibling to ptos-data, outside sync scope)
```

## Tech stack

- Python 3.11+ (uses `tomllib` from stdlib)
- Flask (web framework)
- Jinja2 (templates)
- Vanilla CSS/JS (no build step, no npm)
- pytest (testing)
- SSE (Server-Sent Events for real-time notifications)

## Running tests

```bash
python -m pytest tests/ -v          # full suite
python -m pytest tests/test_todo.py -v  # todo tests only
python -m pytest tests/test_todo.py -k "test_name" -v  # specific test
```

## Code conventions

### Python style
- No comments unless asked
- Follow existing code patterns — look at neighboring files before writing new code
- Use existing libraries (check `package.json`/`requirements.txt`/imports before adding deps)
- Prefer editing existing files over creating new ones
- No emojis in code unless explicitly requested

### File naming
- `ptos_*.py` — core modules
- `web_templates/*.html` — Jinja2 templates
- `web_templates/icons/*.html` — SVG icon partials
- `tests/test_*.py` — test files
- `starters/starter_*.toml` — default configs

### Data model
- Records: plain `.log` files, one line per record, `key=value` format
- Todos: `todo.txt` format (https://github.com/todotxt/todo.txt)
- Config: TOML files
- Schema: `schema.toml` defines record types, fields, validation
- Queries: `queries.toml` defines saved queries, metrics, dashboards
- Data folder: resolved by `PTOS_HOME` env var > `.ptos_home` file > SCRIPT_DIR; setup scripts (Windows/Linux) create `ptos-data` as a sibling to the repo dir; Android uses `~/storage/shared/ptos-data`; `--set-home PATH` writes `.ptos_home` and migrates existing data to the target
- Multi-device sync: `--bisync` runs `rclone bisync`, `--sync --confirm-delete` runs `rclone sync`; reads `[sync]` section from config.toml for remote_name, remote_path, folders; corruption pre-flight check detects zero-byte files before sync (excludes `todo/done.txt` since empty is expected after archiving or undoing); web UI: Settings → Sync card always visible with editable remote_name/remote_path inputs; sync action buttons (bisync/push/resync) only shown when remote is configured and valid; `_invalidate_all()` called after sync to refresh cached TOML config; `run_sync()` returns `{"ok", "output", "error", "returncode"}` dict (no `sys.exit()`); PID-based file lock (`.sync.lock`) prevents concurrent syncs across processes (web + CLI/cron); rclone flags: `--stats-one-line --log-level INFO` for clean captured output; sync card shows rclone status: "rclone not found" / "remote not found in rclone" / full interactive card; auto-sync on startup/shutdown via `auto_sync_on_startup`/`auto_sync_on_shutdown` config keys (default off); `sync.enabled` config key (default true) gates all sync paths — auto-sync, periodic sync, and manual UI button; periodic background sync via `sync_interval_minutes` (default 0 = disabled); **smart skip**: periodic sync checks local file mtimes/sizes in `.ptos_sync_state` before calling rclone (`skip_if_clean=True`); if no local files changed, rclone is skipped entirely; manual sync (UI/CLI), startup, and shutdown always run; periodic sync broadcasts `sync-start`/`sync-done` SSE events so the browser dot blinks and turns green/red; **live streaming**: `run_sync()` accepts `on_line=None` callback — each rclone output line is passed to the callback as it arrives; web UI uses `_sse_broadcast("sync-log", line)` for real-time Settings output, CLI uses `print(line, end="", flush=True)`; subprocess uses `Popen` with manual 300s timeout instead of blocking `subprocess.run`; **remote validation**: before running rclone, `rclone listremotes` is called to verify the remote exists in rclone config; returns clear error with available remotes if not found; **stale lock clearing**: `_clear_rclone_bisync_locks()` deletes `.lck` files from rclone's cache bisync directory before each bisync run (fixes interrupted bisync blocking subsequent runs)
- **Glob wildcard search**: `_glob_match(pattern, text)` in `ptos.py` — plain text uses `in` for substring match; patterns with `*` or `?` use `fnmatch.translate()` for glob matching. Used by all search paths: universal search, browse, todo page, query builder

### Error handling
- Engine functions raise `sys.exit()` on errors
- `ptos_service.py` defines `PTOSError` and `_safe_exit`; the Flask layer installs it per-request via `before_request`/`teardown_request` so web routes can handle errors gracefully without affecting tests
- Web routes catch `PTOSError` and return JSON error responses
- CLI catches `PTOSError` and prints user-friendly messages
- Web routes use `log = logging.getLogger("ptos_web")` — always `log.exception()` before fallback, never bare `except:`

### File safety
- All writes use `.bak` + `.tmp` + atomic rename pattern
- `save_todos()` in `ptos_todo.py` follows this pattern
- Never write directly to data files without backup

### Web patterns
- Routes in `ptos_web.py` call `svc.*` functions (service layer)
- Service functions call `ptos_*` module functions (engine)
- Templates use `{{ variable }}` and `{% if %}` / `{% for %}`
- Forms POST JSON, routes return JSON (`jsonify(ok=True/False, ...)`)
- SSE: daemon thread polls data, broadcasts events, browser handles notifications; `sync-log` event streams rclone output line-by-line to Settings page; **pending notification cache** (`_pending_notifications`) stores due-todo tasks and replays to newly connected SSE clients (fixes startup race condition where notifications fire before browser connects)

### Testing patterns
- Tests in `tests/` mirror module names (`test_todo.py` → `ptos_todo.py`)
- `tests/conftest.py` has an autouse fixture that patches all 16 path constants to `tmp_path` and copies starter configs — tests never touch real user data
- Test classes group related tests (e.g. `TestParseTodoLine`, `TestArchiveDoneTodos`)
- Always verify round-trip: parse → format → parse produces same result
- Test edge cases: empty files, missing files, malformed input

## Todo module specifics

### File format
```
(A) 2026-07-10 Call supplier +HearSpeechPro @phone due:2026-07-20T14:30
x 2026-07-12 2026-07-10 Completed task
```

### Dataclass fields
`raw_line`, `done`, `priority`, `completed_date`, `created_date`, `description`, `projects`, `contexts`, `due`, `due_time`, `threshold`, `threshold_time`, `line_no`

### Key functions
- `parse_todo_line(line)` — parses one line into Todo object
- `format_line(todo)` — formats Todo back to todo.txt line
- `preprocess_todo_text(text)` — converts `pri:a`, resolves NL dates, handles two-token time patterns
- `resolve_todo_date(s)` — returns `(date, time_str|None)` tuple; supports `today`, `tomorrow`, `yesterday`, weekdays, `this_week`, `next_week`, `this_month`, `next_month`, `+Nd`, `+Nw`, `+Nm`, `YYYY-MM-DD`
- `filter_todos(todos, project, context, priority, ...)` — filters by criteria; project/context/priority accept single value or list (OR within group, AND across groups)
- `archive_done_todos(path, months)` — moves old done items to `done.YYYY.txt`

### CLI commands
- `--todo-add TEXT` — add a todo (interactive if no args)
- `--todo-list` — list open todos (with `--all`: include done)
- `--todo-done N` — mark complete
- `--todo-edit N key=value ...` — edit fields (supports multiple key=value pairs, `+Project`, `-+Project`, `@Context`, `-@Context`)
- `--todo-delete N` — delete
- `--todo-undo N` — undo completion (done.txt → todo.txt)
- `--todo-done-list` — list completed todos
- `--todo-done-delete N` — permanently delete from done.txt
- `--todo-done-edit N key=value ...` — edit a completed todo
- `--todo-projects` — list all projects with counts
- `--todo-contexts` — list all contexts with counts
- `--todo-due [DAYS]` — show due/overdue todos (default: today+overdue, optional lookahead)
- `--todo-archive` — archive old done items to done.YYYY.txt

### Filter flags (use with --todo-list)
- `--project NAME` — filter by +Project (repeatable)
- `--context NAME` — filter by @context (repeatable)
- `--priority P` — filter by priority A-D (repeatable)
- `--due-range` — overdue/today/tomorrow/upcoming/someday/none
- `--todo-search TEXT` — glob search on description
- `--table` — table output format
- `--count` — show count only

### Web UI features
- **Quick add bar** with autocomplete dropdown (prefix-aware: `+`, `@`, `due:`, `t:`, `(`); always visible at top of todo page (no collapsible)
- **Quick pick chips** (collapsible) — Due shortcuts (with "pick date & time..." chip), Priority (A-D), Projects, Contexts, Scheduled (with "pick date & time..." chip + "Now" chip), Repeat as toggle chips; open on input focus, close on blur (with 200ms delay to allow chip clicks); on mobile, groups stack vertically instead of scrolling horizontally
- **Filter chips** (collapsible) — Priority (A-D), Due Range (overdue/today/tomorrow/upcoming/someday/none), Context — all toggle on click; on mobile, groups stack vertically
- **Search** (always visible) — text input with glob wildcard `*`/`?` support; filters todos by description; preserves other active filters; desktop sidebar has persistent search bar
- **Form modal** (shared add+edit) — Priority as dropdown (None/A/B/C/D), Projects and Contexts as clickable toggle chips with "+ New" for adding new ones
- **Clickable todo chips** — project, context, and priority chips on each todo row link to filtered view; clicking an active filter chip removes that filter
- **Project rail** — horizontal scroll filter with toggle behavior
- **Overdue/Tomorrow/Today/Upcoming/Someday** bucket view with collapsible Done section; overdue visible by default, collapsible by clicking header
- **Done tasks** — edit and delete buttons on each done row; edit opens the shared modal targeting `done.txt` (`/todo/edit-done`), delete removes permanently from `done.txt` (`/todo/delete-done`); undo (checkmark click) moves back to `todo.txt`
- **Threshold todos** — Todos with `t > today` are hidden until their threshold date arrives (standard todo.txt behavior: `t` means "don't show until")
- **Today progress** counter (done/total)
- **Help card** — color-coded annotated todo.txt example with priority, project, context, due, threshold, recurrence
- **Inline field popups** — click due/threshold badges for date picker, priority badge for priority picker; popups use `position:fixed` and live in `base.html` (outside `<main>` to avoid overflow clipping)
- **Floating add button** (`.floating-add`) — `floatingAddAction()` defined in `base.html` before `{% block scripts %}` so child templates can override; defaults to `/add` page; todo page does NOT override (add area is always visible)
- **PTOS brand** — clickable `<a href="/">` in both mobile topbar and desktop sidebar, links to home page
- **System notifications** — native OS notifications via `_system_notify()` in background thread; detects platform (Linux: `notify-send`, macOS: `osascript`, Windows: WinRT Toast via PowerShell with legacy `ShowBalloonTip` fallback, Android: `termux-notification`); runs alongside browser SSE notifications; notification check runs immediately on server startup, then repeats every `notify_interval` minutes (default 5); **Android requires**: `pkg install termux-api` in Termux + Termux:API app from F-Droid/Play Store + notification permission in Android Settings; **Windows uses** `[Windows.UI.Notifications.ToastNotificationManager]` for native Win10/11 toast notifications; **housekeeping** filters to today-only (no tomorrow), computes `arrived` boolean per task (due_time <= now), notification body prioritizes arrived tasks ("due now"), `_showTodoToast` shows arrived task description first
- **Service worker** (`web_static/sw.js`) — caches GET requests for static assets; excludes `/api/events` (SSE) so real-time notifications work in PWA mode; POST requests always pass through to network
- **Share Schema** (Backup page) — select record types to export a filtered bundle of schema, queries, presets, and config as a ZIP; `[global_fields]` included if defined; `[shared]` included only if referenced by selected types via `use = "shared.X"`; `[fields]` filtered to those used by selected types; queries/metrics/dashboards filtered to selected types; config.toml copied in full; route: `POST /backup/share-schema`, engine: `export_schema_bundle()` + `build_schema_bundle_zip()` in ptos.py

### Autocomplete system
- `_acData` object holds suggestions per prefix (`+`, `@`, `due:`, `t:`, `(`)
- `_getCurrentToken()` parses the word being typed and detects its prefix
- `onTodoInput()` filters `_acData` by typed text and shows dropdown
- `handleInputKey()` handles ArrowUp/Down/Enter/Escape navigation
- `pickAC()` inserts selected suggestion with trailing space; handles `__PICKER__:` values to open datetime-local picker
- `pickAddDate(prefix)` opens the hidden datetime-local picker from quick pick chips
- Input clears on successful add (`input.value = ''` then reload)

### Archiving
- Runs on web server startup
- Items older than 6 months move from `done.txt` to `done.YYYY.txt`
- Archive files are plain text backup, never loaded by web UI

## Key files to check before making changes

| Change type | Files to read first |
|-------------|-------------------|
| Record CRUD | `ptos.py` (engine), `ptos_service.py` (service), `ptos_web.py` (routes) |
| Todo features | `ptos_todo.py`, `ptos_service.py`, `ptos_web.py`, `web_templates/todo.html` |
| Todo CLI | `ptos_cli.py` (argparse + handlers), `ptos_todo.py` (engine) |
| Schema/validation | `ptos.py`, `schema.toml` |
| Web UI patterns | `web_templates/base.html`, neighboring templates |
| CLI flags | `ptos_cli.py`, `ptos.py` |
| Config | `config/config.toml`, `starters/starter_config.toml` |
| Tests | `tests/test_*.py` |
| Start scripts | `start_ptos_linux.sh`, `start_ptos_android.sh`, `start_ptos_windows.bat` + `start_ptos_windows.ps1` |

### Start scripts
All three scripts follow the same pattern: start server in background → health check loop with animated dots (wait up to 15s for port 5000) → conditional browser open → wait for server to exit. `SERVER_READY` flag tracks whether the health check succeeded; browser only opens on confirmed readiness, otherwise prints "Server is taking longer than usual" and keeps polling (up to 2 min) — browser opens automatically once the server becomes available. Linux/Android use `curl -s` (no `-f` flag — works through auth 401); Windows uses `curl.exe -s` (PowerShell's `curl` is an alias for `Invoke-WebRequest`, not the real curl binary). The health check just verifies the server is responding (any HTTP status). Windows uses `.bat`-stub-plus-`.ps1` pattern (same as `setup_ptos_windows.bat`): the `.bat` is a 3-line launcher, `start_ptos_windows.ps1` has full logic with `Start-Process -PassThru` + `Register-EngineEvent PowerShell.Exiting` to kill Flask on exit + `try/finally { Wait-Process; Stop-Process }` as fallback. Ctrl+C via `.bat` shows "Terminate batch job (Y/N)?" (cmd.exe limitation); running `.ps1` directly avoids this. Android widget symlinks to repo's start script (not a stale `$HOME/` copy).

## Commits

- Write concise commit messages matching repo style
- Only commit when explicitly asked
- Stage only intended files, never commit secrets
- Run `python -m pytest tests/ -v` before committing

## Pre-commit hook

A git pre-commit hook runs the test suite and blocks commits on failure.

```bash
cp scripts/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

Use `git commit --no-verify` to bypass (only for genuinely unrelated
pre-existing failures).
