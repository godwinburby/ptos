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
journal/         → Markdown journal entries (YYYY/MM/YYYY-MM-DD.md)
todo/            → Todo files (todo.txt, done.txt, done.YYYY.txt)
notes/           → Markdown notes organized by category (notes/{category}/{slug}.md)

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
- **Server config**: `[server]` section with `host` (default `127.0.0.1`) and `port` (default `5000`); `ptos_web.py` reads from config and warns on startup if `host != 127.0.0.1` and `[auth]` is disabled; `desktop_app.py` always binds `127.0.0.1`, reads port from config
- **Priority labels**: `[todo] priority_labels` config key (e.g. `{ A = "Critical", B = "Important", C = "Moderate", D = "Low" }`); labels are UI-only (not stored in todo.txt); used in quick pick chips, priority picker popup, form modal dropdown, todo list badge tooltips, filter chips, active filter bar, autocomplete dropdown (`pri:` and `(` prefixes), and help card; `ptos_web.py` passes labels to `todo.html` template as `priority_labels`; JS uses `_priLabels` object with fallback defaults
- **Pomodoro config**: `[pomodoro] duration_minutes` config key (default 25); read by `ptos_web.py` context processor as `pomo_minutes`, passed to `base.html` for JS timer engine

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
- `batch_edit_todos(todo_path, line_nos, updates)` — applies same updates to multiple todos (single load/save)
- `archive_done_todos(path, months)` — moves old done items to `done.YYYY.txt`

### CLI commands
- `--todo-add TEXT` — add a todo (interactive if no args)
- `--todo-list` — list open todos (with `--all`: include done)
- `--todo-done N` — mark complete
- `--todo-edit N key=value ...` — edit fields (supports multiple key=value pairs, `+Project`, `-+Project`, `@Context`, `-@Context`)
- `--todo-bulk-edit LINE_NOS key=value ...` — bulk edit multiple todos (comma/range notation: `1,3,5-7`)
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
- **Quick pick chips** (collapsible) — Due shortcuts (with "pick date & time..." chip), Priority (A-D with labels from config), Projects, Contexts, Scheduled (with "pick date & time..." chip + "Now" chip), Repeat as toggle chips; open on input focus, close on blur (with 200ms delay to allow chip clicks); on mobile, groups stack vertically instead of scrolling horizontally
- **Filter chips** (collapsible) — Priority (A-D with labels), Due Range (overdue/today/tomorrow/upcoming/someday/none), Context — all toggle on click; on mobile, groups stack vertically
- **Search** (always visible) — text input with glob wildcard `*`/`?` support and prefix autocomplete (same `+`/`@`/`pri:`/`(` prefixes as quick-add); filters todos by description; preserves other active filters; desktop sidebar has persistent search bar
- **Form modal** (shared add+edit) — Priority as dropdown (None/A/B/C/D with labels from config), Projects and Contexts as clickable toggle chips with "+ New" for adding new ones
- **Clickable todo chips** — project, context, and priority chips on each todo row link to filtered view; clicking an active filter chip removes that filter
- **Project rail** — horizontal scroll filter with toggle behavior
- **Overdue/Tomorrow/Today/Upcoming/Someday** bucket view with collapsible Done section; overdue visible by default, collapsible by clicking header; **Group by** toggle bar (Timeline / Priority / Project / Context) switches between grouping modes — timeline uses existing time buckets, priority groups by A-D with labels, project groups by `+Project`, context groups by `@Context`; todos with multiple projects/contexts appear in each section; URL param `groupby=timeline|priority|project|context`, preserves active filters; **Section sort** — sort button (↕) in groupby bar cycles through 4 modes: default (backend order), reverse name, most todos first, fewest todos first; state stored in `localStorage` per groupby mode (`ptos_todo_sort_{mode}`); within-section row order untouched (priority → due → description)
- **Done tasks** — edit and delete buttons on each done row; edit opens the shared modal targeting `done.txt` (`/todo/edit-done`), delete removes permanently from `done.txt` (`/todo/delete-done`); undo (checkmark click) moves back to `todo.txt`
- **Threshold todos** — Todos with `t > today` are hidden until their threshold date arrives (standard todo.txt behavior: `t` means "don't show until")
- **Today progress** counter (done/total)
- **Help card** — color-coded annotated todo.txt example with priority, project, context, due, threshold, recurrence; priority labels from config shown in help table
- **Inline field popups** — click due/threshold badges for date picker, priority badge for priority picker; popups use `position:fixed` and live in `base.html` (outside `<main>` to avoid overflow clipping); priority picker labels sourced from config `priority_labels` with fallback to defaults
- **Floating add button** (`.floating-add`) — `floatingAddAction()` defined in `base.html` before `{% block scripts %}` so child templates can override; defaults to `/add` page; todo page does NOT override (add area is always visible)
- **PTOS brand** — clickable `<a href="/">` in both mobile topbar and desktop sidebar, links to home page
- **System notifications** — native OS notifications via `_system_notify()` in background thread; detects platform (Linux: `notify-send`, macOS: `osascript`, Windows: WinRT Toast via PowerShell with legacy `ShowBalloonTip` fallback, Android: `termux-notification`); runs alongside browser SSE notifications; notification check runs immediately on server startup, then repeats every `notify_interval` minutes (default 5); **Android requires**: `pkg install termux-api` in Termux + Termux:API app from F-Droid/Play Store + notification permission in Android Settings; **Windows uses** `[Windows.UI.Notifications.ToastNotificationManager]` for native Win10/11 toast notifications; **housekeeping** filters to today-only (no tomorrow), computes `arrived` boolean per task (due_time <= now), notification body prioritizes arrived tasks ("due now"), `_showTodoToast` shows arrived task description first
- **Service worker** (`web_static/sw.js`) — caches GET requests for static assets; excludes `/api/events` (SSE) so real-time notifications work in PWA mode; POST requests always pass through to network
- **Share Schema** (Backup page) — select record types to export a filtered bundle of schema, queries, presets, and config as a ZIP; `[global_fields]` included if defined; `[shared]` included only if referenced by selected types via `use = "shared.X"`; `[fields]` filtered to those used by selected types; queries/metrics/dashboards filtered to selected types; config.toml copied in full; route: `POST /backup/share-schema`, engine: `export_schema_bundle()` + `build_schema_bundle_zip()` in ptos.py
- **Pomodoro timer** — per-todo play button (▶) in `.todo-actions` starts a configurable countdown; floating pill (`.pomo-pill`) persists across all pages via `localStorage`; engine lives in `base.html` (global, runs on every page); `startPomodoro(lineNo, desc)` defined on `window` so todo page can call it; pill shows task name + MM:SS countdown; click pill to expand (stop button); icon button toggles pause/resume; timer resumes on page load from `localStorage`; on completion: browser notification + `_showTodoToast`; duration from `[pomodoro] duration_minutes` config (default 25); pill positioned bottom-left (fixed), z-index 160
- **Selection mode (bulk edit)** — click `☐ Select` in the groupby bar to activate selection mode; each todo row's check circle becomes a square checkbox; click rows to toggle selection; `.sel-bar` shows selected count + Cancel/Edit Selected buttons; **Edit Selected** opens the form modal with only priority/due/threshold/recurrence fields visible (description/projects/contexts hidden since they vary per task); backend `batch_edit_todos()` applies updates in a single load/save; CLI: `--todo-bulk-edit LINE_NOS key=value` supports comma/range notation (`1,3,5-7`)

### Autocomplete system
- `_acData` object holds suggestions per prefix (`+`, `@`, `due:`, `t:`, `(`)
- `_getCurrentToken(inputEl)` parses the word being typed and detects its prefix (accepts any input element)
- `onTodoInput()` filters `_acData` by typed text and shows dropdown for quick-add
- `handleInputKey()` handles ArrowUp/Down/Enter/Escape navigation for quick-add
- `pickAC()` inserts selected suggestion with trailing space; handles `__PICKER__:` values to open datetime-local picker
- `pickAddDate(prefix)` opens the hidden datetime-local picker from quick pick chips
- Input clears on successful add (`input.value = ''` then reload)
- **Search autocomplete** — `onSearchInput()` / `handleSearchKey()` / `pickSearchAC()` — same prefix system as quick-add, renders into `#search-ac-list`; also supports `[[` bracket autocomplete via `attachBracketAutocomplete()`; `goSearch()` extracts `due:VALUE` tokens → `?due=` URL param and `pri:X` tokens → `?priority=` param (not sent as text search)

### Archiving
- Runs on web server startup
- Items older than 6 months move from `done.txt` to `done.YYYY.txt`
- Archive files are plain text backup, never loaded by web UI

## Notes module specifics

### Storage
- Notes live in `notes/{category}/{slug}.md` (e.g. `notes/meeting/2026-07-21-standup.md`)
- Slug format: `YYYY-MM-DD-title-slug` (auto-generated, collision-safe)
- Category folders created on demand

### Template fallback chain
- `get_note_template(category, context)` checks in order:
  1. `templates/{category}.md` — category-specific template (user-editable)
  2. `templates/note.md` — generic note default (created by `--init` from `starters/starter_note.md`)
  3. `_load_starter(category)` — ships with PTOS (e.g. `starters/starter_book.md`)
  4. `_load_starter("note")` — ships with PTOS (final fallback)
  5. Hardcoded stub: `# {{title}}\n\n_Created: {{date}}_\n`
- Placeholders: `{{title}}`, `{{date}}` — substituted at creation time
- Metadata: Key-value lines at top of template (e.g. `Author:`, `Rating:`, `Tags:`) are plain markdown, parseable for future search

### Key functions (in `ptos.py`)
- `list_note_categories()` — sorted list of category folder names
- `list_notes(category)` — list of `{slug, title, date, file}` dicts, newest first
- `read_note(category, slug)` — returns file content or `None`
- `create_note(category, title, content=None)` — creates file, returns `{category, slug, path}`
- `save_note(category, slug, content)` — overwrites file content
- `delete_note(category, slug)` — deletes file, raises `FileNotFoundError` if missing
- `get_note_template(category, context)` — returns template string with placeholders substituted

### Web routes
- `GET /notes` — category browser with create form
- `GET /notes/<category>` — note list in a category
- `GET /notes/<category>/<slug>` — view/edit note (uses shared `_markdown_editor.html`)
- `POST /notes/save` — save note content (JSON: `{category, slug, content}`)
- `POST /notes/create` — create new note (JSON: `{category, title}`)
- `POST /notes/delete` — delete note (JSON: `{category, slug}`)

### Search integration
- Universal search (`/search`) scans note content using `_glob_match`
- Results show `category/title` with snippet, link to note view

## Bracket cross-linking (`[[Target]]`)

### Overview
Wiki-style `[[links]]` sit on top of existing project conventions — not a replacement for `project=value` (Records) or `+project` (Todo). A `[[link]]` in a note or journal entry is a real cross-reference; if it matches an existing project name, that's a bonus.

### Backend — `/api/link-candidates`
- `GET /api/link-candidates?q=...` — returns up to 20 sorted candidates
- Scans `[[Target]]` brackets from journal, notes, and todo files — any text inside `[[ ]]` becomes a candidate (multi-word phrases like `[[buy house]]` work)
- Scans `project=` and `context=` values from record `.log` files
- Todo project names (stripped of `+`) from `get_projects()`

### Frontend — shared JS in `base.html`
- `_getBracketToken(inputEl)` — scans backward for unclosed `[[`, returns `{query, start, fullToken}` or null
- `attachBracketAutocomplete(inputEl)` — fetches from `/api/link-candidates`, renders dropdown, handles Arrow/Enter/Escape; used on all input fields that support bracket linking
- `preprocessLinks(src)` — converts `[[Target]]` → `[Target](/search?q=Target)` markdown links for preview rendering

### Where bracket autocomplete is attached
| Location | Element |
|---|---|
| Todo quick-add | `#todo-input` (checked first in `onTodoInput()`, before `+`/`@`/`pri:`) |
| Journal editor | `#md-editor` (via `_markdown_editor.html` partial) |
| Notes editor | `#md-editor` (via `_markdown_editor.html` partial) |
| Add Record note field | `input[name="note"]` in `add.html` |
| Edit Record note field | `input[name="note"]` in `edit.html` |
| Sidebar search | `#sidebar-search` in `base.html` |
| Search page | `#search-input` in `search.html` |

### Rendering in preview
- `preprocessLinks()` runs in `_markdown_editor.html` before `marked.parse()`
- `[[Fit]]` becomes a clickable link to `/search?q=Fit`
- Only affects Journal and Notes preview — todo textarea shows raw `[[text]]`

### Integration points
- Todo: `_getBracketToken()` checked first in `onTodoInput()` — `[[` takes priority over `+`/`@`/`pri:`
- Markdown editor: `_markdown_editor.html` calls `preprocessLinks()` before `marked.parse()` in `renderPreview()`
- Records note fields: `add.html` and `edit.html` call `attachBracketAutocomplete()` on `DOMContentLoaded`
- Search/sidebar: `attachBracketAutocomplete()` called on page load

## Key files to check before making changes

| Change type | Files to read first |
|-------------|-------------------|
| Record CRUD | `ptos.py` (engine), `ptos_service.py` (service), `ptos_web.py` (routes) |
| Todo features | `ptos_todo.py`, `ptos_service.py`, `ptos_web.py`, `web_templates/todo.html` |
| Todo CLI | `ptos_cli.py` (argparse + handlers), `ptos_todo.py` (engine) |
| Notes | `ptos.py` (CRUD + template), `ptos_service.py`, `ptos_web.py`, `web_templates/notes*.html` |
| Bracket linking | `ptos_web.py` (`/api/link-candidates`), `web_templates/base.html` (shared JS), `_markdown_editor.html`, `todo.html`, `add.html`, `edit.html`, `search.html` |
| Schema/validation | `ptos.py`, `schema.toml` |
| Web UI patterns | `web_templates/base.html`, neighboring templates |
| CLI flags | `ptos_cli.py`, `ptos.py` |
| Config | `config/config.toml`, `starters/starter_config.toml` |
| Tests | `tests/test_*.py` |
| Start scripts | `run_ptos.bat` (Windows), `run_ptos_linux.sh`, `run_ptos_android.sh` |

### Start scripts
Each platform has a single unified script that handles both first-time setup and daily launch. The script detects whether PTOS is already initialised (`config/` exists) and branches accordingly: first-time runs do full setup (install deps, clone repo, `--init`, name prompt); subsequent runs do update (`git pull`) + start. Linux/Android use a single `.sh` script; Windows uses a `.bat`-stub-plus-`.ps1` pattern: `run_ptos.bat` is a thin launcher that downloads `run_ptos.ps1` from GitHub if missing (bootstrapping first-time users who download just the `.bat`), then hands off to it. `run_ptos.ps1` has full logic with `Start-Process -PassThru` + `Register-EngineEvent PowerShell.Exiting` to kill Flask on exit + `try/finally { Wait-Process; Stop-Process }` as fallback. Ctrl+C via `.bat` shows "Terminate batch job (Y/N)?" (cmd.exe limitation); running `.ps1` directly avoids this. Health check uses TCP socket (no curl dependency). `run_ptos.ps1` sets `$env:PTOS_HOME` for the session so ptos.py resolves the data dir immediately; it also writes `.ptos_home` without BOM (Python's `open(encoding="utf-8")` can't read BOM-prefixed paths). Android widget uses copy approach (not symlink) — `run_ptos_android.sh` copies itself to `~/.shortcuts/run_ptos.sh` because Termux:Widget v0.13+ blocks symlinks outside `~/.shortcuts/`; includes fallback to `$HOME/ptos/ptos.py` if `SCRIPT_DIR` doesn't contain `ptos.py`. All scripts have CRLF guards that detect `\r` characters, strip them via sed, and re-exec cleanly. Linux script auto-installs Python via distro package manager (apt/dnf/pacman/zypper) if missing; Android script uses `pkg install -y python`.

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
