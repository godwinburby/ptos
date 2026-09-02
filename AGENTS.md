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
notes/           → Markdown notes (arbitrary folder depth, browsable as file explorer)

ptos-backups/    → ZIP backups (sibling to ptos-data, outside sync scope)
```

> **Shelved: modularizing `ptos.py`.** A split of the 5,411-line engine into domain modules was planned but **deferred** (see `ptos-modularization-shelved.md`). Approved rule: do not start it without revisiting the decision. `ptos.py` stays a monolith for now.
>
> **Deliberate property (do not break): CLI standalone portability.** `ptos.py` + `ptos_cli.py` are two standalone files (plus data files `schema.toml`/`config.toml`) that run the full engine with **no install step, no package manager, no dependency tree** — `ptos_cli.py` imports only `ptos` and the standard library. This is a valued property, not an accident; keep it intact in all future work. Any modularization must preserve it (e.g. via an amalgamation/reassembly step) or it is incomplete.

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
- **Filter expression syntax** (`apply_where` in `ptos.py`): boolean expressions with `AND`/`OR`/`NOT`/parentheses; operators `=  !=  >  <  >=  <=  ~(contains)  !~(not contains)`. Operators may be surrounded by whitespace (`tag != snacks` works — `_tok_where` collapses spaced `field op value` token triples via `_collapse_spaced_ops`); unspaced (`tag!=snacks`) and `NOT (tag=snacks)` behave identically; `!=`/`!~` also match records missing the field entirely (NaN-like, equal to `NOT (field=x)`), while ordered/`=` comparisons are False for missing fields. Used by browse expression box, `--where`, and query/metric definitions.
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
- **Record dates in web forms** — the date input in `add.html` and `edit.html` has **no `max` cap**, so past, present, and future dates can all be entered (the backend `add_post`/`edit_post` never restricted dates; only the HTML blocked future dates)
- **Todo Overdue section** — collapsed by default in the timeline grouping (see Todo module specifics)

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
- **Overdue/Tomorrow/Today/Upcoming/Someday** bucket view with collapsible Done section; **Overdue collapsed by default** (`sec_key == 'overdue'` renders `style="display:none"`, still toggleable by clicking the header); **Group by** toggle bar (Timeline / Priority / Project / Context) switches between grouping modes — timeline uses existing time buckets, priority groups by A-D with labels, project groups by `+Project`, context groups by `@Context`; todos with multiple projects/contexts appear in each section; URL param `groupby=timeline|priority|project|context`, preserves active filters; **Section sort** — sort button (↕) in groupby bar cycles through 4 modes: default (backend order), reverse name, most todos first, fewest todos first; state stored in `localStorage` per groupby mode (`ptos_todo_sort_{mode}`); within-section row order untouched (priority → due → description)
- **Done tasks** — edit and delete buttons on each done row; edit opens the shared modal targeting `done.txt` (`/todo/edit-done`), delete removes permanently from `done.txt` (`/todo/delete-done`); undo (checkmark click) moves back to `todo.txt`
- **Threshold todos** — Todos with `t > today` are hidden until their threshold date arrives (standard todo.txt behavior: `t` means "don't show until")
- **Today progress** counter (done/total)
- **Help card** — color-coded annotated todo.txt example with priority, project, context, due, threshold, recurrence; priority labels from config shown in help table
- **Inline field popups** — click due/threshold badges for date picker, priority badge for priority picker; popups use `position:fixed` and live in `base.html` (outside `<main>` to avoid overflow clipping); priority picker labels sourced from config `priority_labels` with fallback to defaults
- **Floating add button** (`.floating-add`) — `floatingAddAction()` defined in `base.html` before `{% block scripts %}` so child templates can override; defaults to `/add` page; todo page does NOT override (add area is always visible)
- **PTOS brand** — clickable `<a href="/">` in both mobile topbar and desktop sidebar, links to home page
- **System notifications** — native OS notifications via `_system_notify()` in background thread; detects platform (Linux: `notify-send`, macOS: `osascript`, Windows: WinRT Toast via PowerShell with legacy `ShowBalloonTip` fallback, Android: `termux-notification`); runs alongside browser SSE notifications; notification check runs immediately on server startup, then repeats every `notify_interval` minutes (default 5); **Android requires**: `pkg install termux-api` in Termux + Termux:API app from F-Droid/Play Store + notification permission in Android Settings; **Windows uses** `[Windows.UI.Notifications.ToastNotificationManager]` for native Win10/11 toast notifications; **housekeeping** filters to today-only (no tomorrow), computes `arrived` boolean per task (due_time <= now), notification body prioritizes arrived tasks ("due now"), `_showTodoToast` shows arrived task description first; **due-time proximity reminders** — separate `_reminder_loop` thread fires a "Todo due soon" notice once when an open todo's `due_time` is within `[todo] remind_before_minutes` (default 0 = off, thread not started); checked every `[todo] reminder_check_interval` (default 2, clamped ≤ remind_before) on its own timer independent of `notify_interval`; scans all open todos with a `due_time` (not just today's), skips done/past, dedups by `(line_no, due, due_time)`; started via `_start_reminder_thread()` in `__main__` (prints a note at startup if `remind_before_minutes < notify_interval`); broadcasts `todo-reminder` SSE event (task dict `{line_no, description, priority, due, due_time, mins_until}`) for the web toast + browser Notification "Todo due soon" — live-only, NOT added to `_pending_notifications` (avoids the hardcoded `todo-due` replay type and the housekeeping `clear()` race); browser handler lives next to the `todo-due` handler in `base.html`
- **Service worker** (`web_static/sw.js`) — caches GET requests for static assets; excludes `/api/events` (SSE) so real-time notifications work in PWA mode; POST requests always pass through to network
- **Share Schema** (Backup page) — select record types to export a filtered bundle of schema, queries, presets, and config as a ZIP; `[global_fields]` included if defined; `[shared]` included only if referenced by selected types via `use = "shared.X"`; `[fields]` filtered to those used by selected types; queries/metrics/dashboards filtered to selected types; config.toml copied in full; route: `POST /backup/share-schema`, engine: `export_schema_bundle()` + `build_schema_bundle_zip()` in ptos.py
- **Pomodoro timer** — per-todo play button (▶) in `.todo-actions` starts a configurable countdown; floating pill (`.pomo-pill`) persists across all pages via `localStorage`; engine lives in `base.html` (global, runs on every page); `startPomodoro(lineNo, desc)` defined on `window` so todo page can call it; pill shows task name + MM:SS countdown; click pill to expand (stop button); icon button toggles pause/resume; timer resumes on page load from `localStorage`; on completion: browser notification + `_showTodoToast`; duration from `[pomodoro] duration_minutes` config (default 25); pill positioned bottom-left (fixed), z-index 160; **row indicators** — the active todo row gets a green (running) or yellow (paused) left border glow; the pomo button on the active row toggles to ⏸ (running) or ▶ (paused), with a ⏹ stop button that appears only on the active row
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
- Notes live in `notes/` directory, browsable as a file explorer with arbitrary folder depth
- No forced date prefixes or slug conventions — files are named by the user
- Each folder may contain a `template.md` — a local template applied to new files created in that folder
- `template.md` is excluded from file listings (it's a folder property, not a note)

### Template resolution
- `find_parent_template(rel_path)` walks up from `rel_path` toward `NOTES_DIR` root, returning the nearest ancestor's `template.md`
- `resolve_new_file_template(rel_path)` returns:
  - `{source: "local", content: str}` — silent, no prompt needed
  - `{source: "choice", parent: {...} or None}` — prompt needed
- Fallback chain: local `template.md` → parent's `template.md` → blank

### Key functions (in `ptos.py`)
- `_safe_path(rel_path)` — resolve relative path under NOTES_DIR, reject escapes
- `_validate_name(name)` — reject empty, `/`, `\`, `.`, `..`
- `note_id_of(fpath)` — extract `ptos-id` from a note's first-line HTML comment, or `None` (was `_note_id_of`; promoted to public — `_note_id_of` kept as an internal alias)
- `ensure_note_id(rel_path)` — return note's id, generating+prepending `<!-- ptos-id: XXXXX -->` if absent (opt-in, never on creation)
- `list_dir(rel_path="")` — return `{folders: [...], files: [...]}` for a directory
- `create_folder(rel_path, name)` — mkdir under rel_path
- `create_file(rel_path, name, content)` — create `name.md` (auto-append `.md`)
- `rename_note(rel_path, new_name)` — rename file or folder
- `delete_note_entry(rel_path)` — delete file or recursive folder delete
- `find_parent_template(rel_path)` — walk up to find nearest `template.md`
- `resolve_new_file_template(rel_path)` — local → silent; parent → choice
- `get_note_template(category, context)` — legacy template resolution (still available)

### Web routes
- `GET /notes` — root listing (also `GET /notes/browse`)
- `GET /notes/browse/<path:rel_path>` — folder listing with breadcrumbs
- `GET /notes/edit/<path:rel_path>` — edit view (markdown editor + backlinks panel)
- `POST /notes/new-folder` — create folder (JSON: `{path, name}`)
- `POST /notes/template-check` — AJAX template resolution (JSON: `{path}`)
- `POST /notes/new-file` — create file (JSON: `{path, name, content}`)
- `POST /notes/rename` — rename file/folder (JSON: `{path, new_name}`)
- `POST /notes/delete` — delete file/folder (JSON: `{path, force?}`); checks for backlinks first, returns `needs_confirm` if note has incoming links
- `POST /notes/save` — save file content (JSON: `{path, content}`)
- `POST /api/note-link-id` — generate+persist an id for a note (JSON: `{path}`); returns `{id, target}`

### Search integration
- Universal search (`/search`) scans note content using `os.walk` + `_glob_match`
- Results show `rel_path` with snippet, link to edit view

### Concept tags
- `[[Target]]` in notes is scanned by `_iter_link_matches()` via `os.walk` over `NOTES_DIR`
- Existing bracket-linking infrastructure handles everything: `get_link_candidates()`, `get_backlinks()`, `attachBracketAutocomplete()`, `initBacklinksPanel()`
- No separate concept-tag API needed — reuse existing `_BRACKET_RE` and `_iter_link_matches()`

## Board module specifics

### Config storage
- Boards stored in `queries.toml` as `[board.NAME]` sections
- Keys: `columns` (list of record types), `time_window` (default `this-month`), `limit` (default 0 = unlimited), `card_title_fields` (comma-separated string or list of field names for card header), `rollup_field` + `rollup_op` (`sum`/`avg`/`count`, default `count`) for lane rollups
- Board editor in Query Builder: drag-reorderable column chips, time window/max cards fields, card title priority chip picker, rollup field/op dropdowns
- Board time windows use the full named set (`td`/`yd`/`tw`/`lw`/`tm`/`lm`/`last-3-months`/`tq`/`lq`/`ty`/`ly`/`all`) plus custom cycles; resolved via `resolve_time()` in `get_board_data()` (only `last-3-months` is special-cased); board page has a live `<select>` that persists via `POST /api/board/time-window` → `update_board_time_window()`; Query Builder board editor options generated from `_timeOpts` filtered via `_boardTimeOpts()`
- **Rollups**: `get_board_data()` computes `rollups` per column type (raw float values) over the FULL matched record set *before* limit truncation, skipping non-numeric values; column types lacking the rollup field get `None` (per spec: "skip that column's rollup"); op `sum`/`avg`/`count`; avg returns `None` on empty (no ZeroDivision); `rollup_op` returned in board data; display formatting done template-side — `/board` route passes `rollup_fmt`/`rollup_avg_fmt` (`ptos.fmt`/`fmt_avg`) and board.html renders `rollup_fmt(rollup_val)` / `avg {{ rollup_avg_fmt(rollup_val) }}` / `count {{ rollup_val }}`
- **Rollup validation on save**: `save_queries_full()` board loop persists `rollup_field`/`rollup_op` and raises `PTOSError` if the field lacks `aggregatable = true` in `schema[fields]` or applies to none of the board's column types (via `filter_fields_for_type`)
- **Rollup field dropdown**: Query Builder board editor populates the Rollup Field select from `aggregatable_all` (aggregatable fields present on any column type) so mixed-type boards can roll up a field only some lanes have — columns lacking the field show count only (per spec)

### Card title fields
- `card_title_fields` config key per board controls which record fields appear as the card header
- Chip picker in board editor: only fields common to all column types shown as toggle chips, selected fields drag-reorderable for priority
- First 2 matching fields on each card displayed; unused if no matching fields
- Fallback if not configured: `['name', 'client', 'intent', 'title', 'subject']`
- Passed to template as `board_data.card_title_fields` (list) from `get_board_data()`

### API
- `POST /api/board/field-overlap` — returns `{overlap: [...], all_fields: [...], aggregatable_overlap: [...], aggregatable_all: [...]}` (shared + union of all fields across columns; `aggregatable_overlap` = shared aggregatable subset, `aggregatable_all` = aggregatable fields on any column — the latter drives the rollup field dropdown)
- `POST /board/advance` — creates a new record of target type, copies shared fields; returns `missing_required` + `new_line`/`new_filepath`/`new_lineno` for edit redirect
- `GET /board` — renders Kanban view, board selected via `?board=NAME` query param; auto-selects first board if none specified

### return_to flow
- Board cards (edit/delete buttons) pass `return_to=pathname+search` to preserve board context
- Drag→edit flow and multi-preset add also pass `return_to` through to redirect back to board
- `onParentChange` in edit.html preserves `return_to` in URL when reloading field cascades

## Browse module (group-by / sort-by)

- **Group by / Sort by dropdowns** — on `/browse`, `#b-group` and `#b-sort` are populated with **dimension fields**, not every schema field. Dimensions exclude `[fields].dimension=false` (via `non_dimension_fields()`) and int fields, and always include `date`/`day`/`month`/`year` — the same rule `api_type_fields` uses for its per-type `dimensions` list.
- **Cross-type (no type selected)** — dropdowns show the global union computed server-side by `_global_dimensions(schema)` in `ptos_web.py` (`browse_get` passes it as `browse.html`'s `_globalDims`).
- **Per-type narrowing** — when a single type is selected in the FilterBuilder, `_refreshGroupSortForType()` in `browse.html` populates the dropdowns from that type's `/api/type_fields/{type}` `dimensions` (cached per type in `_typeDimsCache`), so fields from other types never appear. It fires via the FilterBuilder's `onTypeFields` hook (which `filter_builder.js` calls after `_fetch` on cache-hit/success/error) and on every `runBrowse`, and resets the dropdown to placeholder-only immediately on type change (no cross-type flash). `onTypeFields` receives the fresh `dimensions` from the shared `_fetch` cache to avoid a duplicate API call.
- **Static cache-busting** — `filter_builder.js` is included as `/static/js/filter_builder.js?v=2` in `browse.html`/`query_builder.html` (and the service worker cache is `ptos-v3`) so stale cached JS can't silently revert browse group/sort behavior; if group/sort looks wrong after a code change, hard-refresh the browser.

## Habits module (`/habits` heatmap + streak)

- **Data model** — a habit is just a record. Dedicated `type=habit name=X` (zero required fields beyond `name`) is the recommended model; existing types work too via per-habit `filters` (e.g. `filters = ["type=exercise"]` for "did I exercise today"). No new write path — logging reuses `append_record`/presets
- **Config** — `[habit.NAME]` in `queries.toml` (quoted dotted key `["habit.NAME"]`, same as boards — the bare `[habit.NAME]` nested-table form does NOT load): `filters` (list of `field=value` strings, same syntax `find_records_with_location` takes), `weeks` (default 12). Multiple entries = multiple tracked habits on one page
- **Service** (`ptos_service.py`): `get_habit_names()` lists configured habits; `get_habit_data(habit_name, time=None, from_date=None, to_date=None)` raises `PTOSError` if unconfigured/no filters, resolves the window (explicit `from_date`/`to_date` inclusive range → `time` keyword/literal via `_resolve_time` → else the habit's configured `weeks` ending today), floors the start to **Monday** so columns are real calendar weeks (grid always starts a week boundary; future days past today are never rendered; giant windows like `all` are capped at 260 columns by trimming whole weeks from the front), calls `find_records_with_location(filters, start, end)`, builds `days_present` set (any matching record marks the day), computes streak walking back from today (yesterday if today not yet logged — "today isn't over yet" rule), returns `{habit_name, streak, weeks, grid:[{date,present,is_today}], months:[{name, days:[{date|None,present,is_today}]}], month_labels, range_label, total_days, days_done}`. `months` renders as **per-month calendar blocks**: leading `None` (blank) cells align the 1st under its weekday (Monday=0), trailing blanks pad each month to full weeks; the current month never renders past today; `month_labels` keeps the legacy absolute-week-column form for tests/back-compat; `range_label` is "Aug 11 – Sep 2, 2026"-style (intent window, not floored grid start). Grid presence is boolean — logging twice in one day still = one present cell; `_fmt_range` helper formats the caption dates
- **Caching** — `get_habit_data` cached per habit + window under `habit:{name}:{time|'default'}:{from_date}:{to_date}`; `_invalidate_history_cache()` pops `habit:` keys alongside `history:`/`condsug:` so all 7 record-write paths already invalidate habits (no new call sites)
- **Route** — `GET /habits` renders `habits.html` (one card per habit: streak badge, **per-month calendar blocks** — each month is its own bordered block with a "July 2026" name header, M-T-W-T-F-S-S weekday row, weeks as rows, leading/trailing blanks, today outlined via `.habit-cell.today`, "X of Y days · range" summary, Less/More + Today legend); **time-window dropdown** — curated `_habit_time_options()` (This/Last month, This/Last quarter, This/Last year, All time + custom cycles + Month/Date range pickers reusing `_time_picker.html` with prefix `hab-` and `time_picker.js`); tiny windows (today/yesterday/this,last week) excluded since they break a week-grid view; select round-trips `time`/`custom_time`/`from_date`/`to_date` URL params like `/thresholds`; empty state shows the config snippet. Nav link in `base.html` next to Board (`icons/habits.html`)
- **CLI** — `--habits [NAME]` (`ptos_cli.py` `run_habits()`, lazily imports `ptos_service`): prints the same per-month calendar blocks in text (`#` present, `.` miss, `^` today pointer) with a `streak / days-done / range` header; `--habits NAME` filters to one configured habit (missing name → friendly exit); no habits configured → prints the `["habit.meditation"]` config hint
- **Query Builder** — "Habits" tab (mirrors Boards tab): name, filters (space-separated `field=value` text input), weeks; round-trips through `save_queries_full(raw_habits=...)` which validates a non-empty `filters` list and writes `["habit.NAME"]` keys
- **Schema** — `type=habit` in `[types].allowed` + `[type.habit]` (`required = ["name"]`, `name` field options in `[type.habit.fields.name]`). Without the schema entry, `validate_record` rejects `type=habit`
- **Tests**: `tests/test_habits.py` (streak consecutive/gap/today-missing, double-log single present, cache invalidation on append, no-rescan on repeat call, unconfigured raises; `TestHabitWindow` covers Monday-aligned grid, `is_today`, month-label columns, `time="tm"`, from/to range, past window no-today, all-time column cap; `TestHabitMonths` covers per-month block shape/alignment/padding; `TestHabitCli` covers `--habits` output, name filtering, missing-name exit, no-habits hint)

## Calendar module (`/calendar` month grid)

- **Data model** — purely a read-side view of existing records (same category as Board/Habits); no write path. **Hybrid**: `/calendar` defaults to an implicit global "All records" view (reserved name `__all__`, no config needed, `filters = []` = every record); `[calendar.NAME]` entries = named filtered calendars, listed via a switcher dropdown
- **Config** — `[calendar.NAME]` in `queries.toml` (quoted dotted key `["calendar.NAME"]`, same as boards/habits): `filters` (list of `field=value` strings, same syntax `find_records_with_location` takes — not restricted to a single `type=`), `time_window` (default `this-month`) which only sets the **initial** month loaded (prev/next arrows navigate freely afterwards)
- **Service** (`ptos_service.py`): `get_calendar_names()` lists configured calendars (`__all__` is never listed); `get_calendar_data(name, year=None, month=None)` — `name == "__all__"` skips the config lookup and uses empty filters (matches everything), any other name raises `PTOSError` if unconfigured/no filters; resolves the initial month via `_resolve_time(time_window)` when no explicit year/month given, calls `find_records_with_location(filters, start, end)` over the named month, buckets records by day (`by_day`), and returns `{calendar_name, filters, year, month, weeks, total_records, prev, next}`. `weeks` is a list of 7-cell rows (`None` = blank) with leading/trailing blanks so day 1 lands on the correct weekday (Python `monthrange` Monday=0). Each day record carries `{line, title, note}` — `title` is the first of `name`/`client`/`intent`/`title`/`subject` present, else `(type)`; dates bucketed via `ptos.parse_line` (NOT `_parse_record`'s display-formatted date)
- **Caching** — `get_calendar_data` cached under `calendar:{name}:{year}:{month}`; `_invalidate_history_cache()` pops `calendar:` keys alongside `history:`/`condsug:`/`habit:` so all record-write paths invalidate calendars for free
- **Route** — `GET /calendar` (global "All records") + `GET /calendar/<name>` (named view) renders `calendar.html` (7-column month grid, `?year=&month=` prev/next nav, switcher with "All records" first, today highlighted); clicking a day with records expands it inline listing that day's records with an "Open day in Browse →" link (`/browse?time=range&from_date=...&to_date=...` — browse restores date range from URL but not `where` filters). With zero named calendars a hint card shows the config snippet; the global view still renders. Nav link in `base.html` next to Board/Habits (`icons/calendar.html`)
- **Query Builder** — "Calendars" tab (mirrors Habits tab): name, filters (space-separated `field=value` text input), initial-month time window select; round-trips through `save_queries_full(raw_calendars=...)` which validates a non-empty `filters` list and writes `["calendar.NAME"]` keys (named calendars require ≥1 filter; the global view is implicit, not stored); deletion goes through the delete-from-state-then-SaveAll path (same as due/boards/habits)
- **Tests**: `tests/test_calendar.py` (day-cell placement, outside-month exclusion, leading/trailing blanks + multiple-of-7 grid, day-1 weekday column, prev/next year-boundary rollover, time_window initial month, unconfigured raises, `__all__` includes all types with no config + defaults to current month + excluded from names, global-vs-named route filtering, cache invalidation on append, no-rescan on repeat call, `save_queries_full` round-trip + empty-filters rejection + leaked-config-key guard)

## Thresholds module (`/thresholds` budget warnings)

- **Data model** — a threshold compares a computed value against a target with min/max direction; configured as `[threshold.NAME]` in `queries.toml`. Keys: `metric` (query/metric name to measure), `agg` (`sum`/`count`, default `sum`), `sum_field` (field to sum when `agg=sum`), `value` (literal number or another metric/query name to resolve at eval time), `direction` (`min`/`max`), `time` (default `this-month`), `target` (literal value for backward compat, ignored when `value` is set). Derived values: `pct` = actual/target × 100; `status` = `ok`/`warning`/`over`/`met`
- **Resolution** — `_resolve_value(ref, cfg, time)` in `ptos_service.py` resolves a ref to a float: checks `metrics` dict first (calls `get_metric`), then top-level queries/`queries` dict (calls `get_records` with `sum_field`). The `value` field can reference another metric/query for dynamic targets
- **Status logic** — `get_threshold_status(name)` evaluates one threshold: direction `max` → over ≥100%, warning ≥80%, ok; direction `min` → met ≥100%, warning <50%, ok. Returns `{name, raw, target, direction, pct, unit, status}`
- **Matching** — `get_matching_thresholds(record)` checks each threshold's query `where` clause against a record dict; returns matching thresholds with live status
- **Config** — stored in `queries.toml` as `["threshold.NAME"]` (quoted dotted key, same pattern as boards/habits/calendar). `save_queries_full(raw_thresholds=...)` persists thresholds alongside queries/metrics/dashboards
- **Engine** — `get_thresholds()` in `ptos.py` reads `get_queries()` and filters for `threshold.*` keys
- **CLI** — `--thresholds` flag prints a formatted table of all thresholds with values/targets/status
- **Service** — `get_all_threshold_status()` evaluates all thresholds; `get_matching_thresholds(record)` for add-form integration
- **Web routes** — `GET /thresholds` (progress bars page with time picker), `GET /thresholds/<time>` (time override), `POST /api/thresholds/match` (matches a record against thresholds), `GET /api/thresholds/status` (all threshold statuses)
- **Add-form integration** — debounced POST to `/api/thresholds/match` on field change; shows threshold match bars above the form; post-save preview computes client-side using `agg`/`sum_field` from API response to show what the bar will look like after saving
- **Edit-form threshold preview** — ported from Add form; replacement math (`previewRaw = m.raw - oldAmount + newAmount`) for sum-type; count-type conservative (shows `m.raw`); embeds `_originalFields` JSON from `field_values`; binds on `#edit-form` change/input events
- **Home widget** — compact threshold card on home page; uses the dashboard's selected time window (via `time_code`/`from_date`/`to_date`); `[home] thresholds` in `config.toml` filters which thresholds show (empty = show all); Settings page checkbox list to configure
- **Thresholds page time picker** — full time window dropdown using shared `_time_picker.html` partial with `thr-` prefix; supports specific year/month/date and date range; `get_all_threshold_status()` receives resolved `time`, `from_date`, `to_date`
- **Query Builder** — "Thresholds" tab with editor for metric/agg/sum_field/value/direction/time; saves via `save_queries_full(raw_thresholds=...)`, deletes via threshold-specific path
- **Nav** — links in desktop sidebar and mobile more menu (keyboard shortcut `g T`), icon in `web_templates/icons/thresholds.html`
- **Tests**: `tests/test_thresholds.py` (config load, metric/query resolution, status logic for all direction/pct combos, matching, save round-trip, preserves queries/metrics)

## Dashboard highlights

- **Config** — `[dashboard.highlights.DASHBOARD]` in `config.toml` maps metric names to colors; stored in config (UI concern), not queries.toml. Colors: `accent` (blue), `warn` (orange), `success` (green), `error` (red), `purple`, `teal`, `rose`, `slate` — 8 total
- **Service** — `get_dashboard()` in `ptos_service.py` reads highlights from `cfg["dashboard"]["highlights"][name]` and attaches `highlight` key to each item dict
- **Web route** — `home()` passes `highlight` through stat dict to template; `settings_page()` passes `dashboard_highlights` and `dashboard_metrics_map` to template; `settings_save()` persists highlights to `config.toml`
- **Template** — `home.html` applies `c-{color}` CSS class to `.stat-card`; `settings.html` renders a drag-and-drop color palette (8 labeled swatches + a clear ⊗ swatch) with metric chips as drop targets (`dragStartColor`/`dragOverColor`/`dropColor` handlers); chip clicks still cycle colors as mobile fallback
- **CSS** — `.c-accent` (blue), `.c-warn` (orange), `.c-success` (green), `.c-error` (red), `.c-purple`, `.c-teal`, `.c-rose`, `.c-slate` modifier classes in `base.html`
- **CLI** — `run_dashboard()` reads highlights from config, applies bold ANSI colors; `run_metric()` accepts `color`/`reset` params; `--add-dashboard` supports `--highlight METRIC:COLOR` flag
- **Settings page** — per-dashboard metric chips with color dot; drag a color onto a chip or click to cycle: none → blue → orange → green → red → purple → teal → rose → slate → none; same color can be assigned to multiple metrics

## Dashboard grouping

- **Config** — optional `groups` dict in `[dashboards.NAME]` (`queries.toml`): `groups = { "Revenue" = ["income_this_month"], "Assessment" = ["assessment", "assessment_pct"] }`. `metrics` remains the flat ordered union and is required for backward compat with old entries, but may be empty/absent — the highlight picker reads `metrics` then falls back to flattening `groups`. Order is TOML insertion order.
- **Service** — `get_dashboard()` returns a new `groups` key: an ordered list of `{name, items}` chunks with the **ungrouped leftovers (name `""`) first**, then groups in definition order. Falls back to `groups=None` when no `groups` configured (exact old behavior). String group values are normalized to lists; items present only in `groups` (hand-written configs) are still rendered.
- **Home page** — `home()` builds `stat_groups` alongside flat `stats`; `home.html` renders each group under a `.stat-group-label` header (uppercase small text) followed by its own `.stat-grid`. Highlights (`c-{color}`) still work per metric. Flat dashboards render exactly as before via the `stat_card` Jinja macro.
- **Query Builder** — dashboard editor renders **group boxes**: a `General (ungrouped)` box plus one box per group. Chips drag **between** boxes (native HTML5 DnD); each grouped box has `✎` rename and `×` remove (items return to ungrouped). `+ New group` creates an empty box. `db.groups` state round-trips load/save through `save_queries_full`, which strips blank group names and empty item lists.
- **CLI** — `--add-dashboard NAME --dash-group GROUP:M1,M2 GROUP:M2,M3` seeds groups (note: `--dash-group`, not `--group` — that long option is already taken by `-G/--group` analysis grouping). Group members are auto-merged into `metrics` (union). `run_dashboard()` (ptos.py) prints bold group headers in CLI output.
- **Share Schema** — `export_schema_bundle()` preserves `groups`, filtering both `metrics` and each group list to included queries/metrics.
- **Tests**: `tests/test_dashboards.py` (order + ungrouped-first, full partition, string-value normalization, groups-only config, highlights on grouped items, save round-trip, blank/empty stripping, no-groups metrics-only, home grouped/flat render via web client). `test_export.py` covers group preservation + member filtering in shares.

### Quick-add preset count

- Home and Add Record show the top N most-used single presets (default **10**), the rest collapse under "Show all"; configure via `[home] quick_presets` in `config.toml`. All web call sites read this config key (`ptos_web.py` home + add routes) and pass it to `get_frequent_presets(n)`. Read: the `[home]` section of `config.toml`; tests in `tests/test_presets.py` (`TestQuickPresetCount`).

## Stock tracking

- **Schema** — two record types: `stock_unit` (serialized items: hearing aids with category, model, serial, status, date_sold) and `stock_txn` (movements: batteries, domes, receivers with category, model, qty, serial)
- **Battery thresholds** — queries/metrics/thresholds per battery size (10, 13, 312, 675) using `min` direction, `time = "all"`, reorder point 5 units; battery queries filter by `type=stock_txn AND category=battery AND model=SIZE`
- **Metric pattern** — each battery size has a `_moves` query (all transactions), a `_stock` metric (sum of qty), and a `_stock` threshold (min 5, all-time)

## Suggestions caching (history + conditional)

- **`get_history_suggestions(rtype, context_record=None)`** (`ptos_service.py`) splits into a cached scan-and-aggregate step `_build_history_suggestions(rtype)` (key `history:{rtype}`) and a cheap per-call filter `_apply_context_filter(tags_by_field_value, rtype, context_record)`. `context_record` is intentionally **excluded** from the cache key — the full-file scan is the expensive part; `filtered_tags` is recomputed from the cached aggregates on every call since it varies per request. Only the first call per rtype after invalidation triggers `scan_records(date.min, date.max, [f"type={rtype}"], None)`
- **`get_conditional_suggestions(rtype, field, value)`** (`/api/field_suggest`) is fully cached under `condsug:{rtype}:{field}:{value}` — the whole return dict, since there's no per-call variable part. This removes the per-selection full scan that made cascade fill feel slow
- **Invalidation** — `_invalidate_history_cache()` (`ptos_service.py`) pops every `history:`/`condsug:`/`habit:`/`calendar:` key and is called after **any** record write: `append_record`, `edit_record`, `delete_record`, `advance_record`, `bulk_delete`, `bulk_set`, `save_schema`. Correctness over precision — all types invalidated on any write (writes are rare vs cascade reads; selectively invalidating individual `condsug` keys risks serving stale suggestions)
- Scan window stays unbounded (`date.min`→`date.max`) — deliberate zero-behavior-change choice; the lookback bound from the spec was **not** applied
- Tests: `tests/test_history_cache.py` (no-rescan call counter, per-mutator invalidation, cache-hit identity, context-filter variance, bulk invalidate-all)

## Cross-record links (`type:id`)

### Overview
Records, todos, and notes can carry **engine-reserved** `id`/`links` tokens for explicit one-to-one/one-to-many cross-references (e.g. an expense linked to the income that refunds it, or a todo linked to an expense). `id=<id>` (records, in `.log` lines) and `id:<id>` (todo.txt lines) identify a single line; `links=type:id,type:id` (records) / `links:type:id,type:id` (todos) point at other entries. Notes use `<!-- ptos-id: XXXXX -->` on line 1 as their id. Link targets are **strict `type:id`** — no field-value targets like `project:hearing_aid` (grouping stays on `project=` / `+Project`; `[[brackets]]` remain the free-text cross-ref mechanism). `id`/`links` are schema-free: `validate_record`'s always-allowed field set is `{"type", "tag", "id", "links"}` (ptos.py `validate_record`). **No auto-id generation** — ids appear only via hand-typing, `--add --link`, or `--retro-id`. Forward direction (`links=`) is stored; reverse (who links to me) is always computed via backlinks.

### Engine (`ptos.py`, section "Cross-record links (type:id)" after `scan_records`)
- `generate_id(length=6)` — `secrets`-based, alphabet `abcdefghjkmnpqrstuvwxyz23456789` (no 0/O/1/l)
- `generate_unique_id(length=6, max_attempts=5)` — `generate_id()` wrapped with a collision check against `list_link_ids()`; retries up to `max_attempts`, then `sys.exit`. **Every tool-chosen id goes through this** (`append_record_id`, `append_todo_id`, `_handle_retro_id`, `--add --link`), so a tool-generated collision "can't happen" — hand-typed ids are untouched
- `backlink_refs(target)` — reverse lookup for `type:id`: scans records (`links=`) and todos (`links:`) for tokens equal to `target`, returns `{kind, filepath, lineno, line}` dicts; powers the delete/complete warnings
- `split_link_target(target)` — `(type, id)` tuple or `None`; journal targets are `journal:YYYY-MM-DD`
- `resolve_link(target)` — returns `{kind, type, id, filepath, lineno, line}` or `None`; records via `find_records_with_location([f"type={t}", f"id={i}"])`, todos scan `TODO_PATH`/`DONE_PATH` for `\bid:<id>` (whole token), notes walk `NOTES_DIR` checking first-line `<!-- ptos-id: X -->` comments, journal resolves if the date file exists. **Record `lineno` is 0-based** (engine convention); todo `lineno` is 1-based
- `list_link_ids()` — all `type:id` targets (records + todos + notes), deduped, sorted
- `check_dangling_links()` — returns `{kind, target, error, filepath, lineno, line}` for **dangling links** (target unresolvable) and **duplicate ids** (records + todos + notes); wired into `lint_records` (prints + adds to `error_files`) and `lint_all_records` (adds to `errors_list`)
- `append_links_to_line(raw, new_links)` / `append_links_to_todo_line(line, new_links)` — merge links (dedupe, keep one token)
- `append_record_id(filepath, lineno, old_line, new_id=None)` — appends `id=` in place via `rewrite_line_in_file` (0-based lineno), raises `ValueError` if already present; `append_todo_id(line, new_id=None)` — returns `(new_line, new_id)`

### Todo module (`ptos_todo.py`)
- `Todo` dataclass gains `id: Optional[str]` and `links: List[str]`; `parse_todo_line` handles `id:`/`links:` tokens (else they'd be absorbed into description); `format_line` round-trips them; `edit_todo`/`batch_edit_todos` accept `id`/`links` updates; `filter_todos(..., linked_to=...)` matches todos whose `links` contains a target
- `rewrite_line_by_number(todo_path, line_no, new_line)` — replaces one todo line (1-based), round-trips via `save_todos` (atomic), returns True if changed

### CLI (`ptos_cli.py`)
- `--add ... --link TARGET` — creates a record with generated `id=` + `links=TARGET` (exactly 1 target required); warns (saves anyway) if the target doesn't resolve, same as standalone `--link`
- `--add ... id=X` — explicit ids are checked against `list_link_ids()` before `append_record()`; `sys.exit` "id already in use" on collision (hand-typed ids in `.log` files remain unchecked by design)
- `--link SRC_TARGET TARGET` (standalone) — adds TARGET to an existing entry's links; journal source rejected; warns (saves anyway) if target is dangling; todo source rewrites via `rewrite_line_by_number`
- `--retro-id TYPE` — assigns an id to an existing entry: records via `--where` filters (`find_records_with_location` must match exactly one; `date=` is NOT a kv filter — use `amount=...` style), todo via `--search TEXT` (must match one open todo), note via `--search TEXT` (must match one note file by name)
- `--linked-to TARGET [TARGET ...]` (Query group) — appends `links~TARGET` to query filters; works standalone or with `--query`/`--type`/`--tag`
- **Destructive-action warnings** — record delete (`run_set` `do_delete`, including `--delete --all`), `--todo-done`, `--todo-delete`, and `--todo-done-delete` print "N entrY/ies link to type:id — they will become dangling" via `backlink_refs()` when the target has incoming links; non-blocking (proceeds after confirm)
- **`--set` validation** — `apply_set()` routes `id=` through the same uniqueness check (duplicate → `sys.exit`) and `links=` through the same resolve-warning as `--add`; re-setting a record's own id is a no-op, not an error
- Handlers: `_handle_link`, `_handle_retro_id` (defined before `main()`); `--linked-to` merged into `final_filters` next to `--type`/`--tag`
- `remove_type()` prints an awareness message when existing records use the removed type ("N existing records use type 'X' (id set on M of them); they are not modified but will fail schema validation from now on")

### Web (`ptos_web.py` + templates)
- `GET /api/link-ids` — all `type:id` targets for autocomplete/datalists
- `POST /api/retro-id` — `{kind: "record", filepath, lineno}` (0-based) or `{kind: "todo", line_no}` (1-based) or `{kind: "note", path}` → assigns an id
- `POST /api/link` — `{source, target}` → `svc.link_entries()` adds the link, returns `{ok, source, target, resolves, updated, links}`
- Service (`ptos_service.py`): `get_link_ids()`, `retro_id_record(filepath, lineno)` (0-based), `retro_id_todo(line_no)`, `retro_id_note(rel_path)`, `link_entries(src, dst)` (raises `PTOSError` for unresolvable source or journal source); all call `_invalidate_history_cache()` after writes
- `_iter_link_matches` (backlinks scanner) additionally yields `links=`/`links:` tokens split on commas, so `get_backlinks("type:id")` = the **Linked-from** list (records + todo groups)
- **Todo page** (`todo.html`): quick-add + modal support `links:` (autocomplete prefix via `/api/link-ids`); edit modal has Id field + Generate button + Links field with autocomplete; each row shows `id:` badge and clickable `type:id` link badges (`/todo?linked_to=...`); 🔗 row button assigns an id if missing (`/api/retro-id`) then prompts for a target (`/api/link`); `/todo?linked_to=X` filters via `ptos_web.todo_page` (`selected_linked_to`)
- **Records**: `add.html` and `edit.html` have Id (Generate button) + Links fields (datalist autocomplete); `add_post`/`edit_post` persist `id`/`links` into the record line; `edit.html` shows a **Linked from** panel for `rtype:id` via `initBacklinksPanel` (which now restores `display` when matches exist)
- **Backlinks UI**: `_blRenderGroups` sets `container.style.display = ""` when items exist (was hide-only), enabling the Linked-from panel on `edit.html`

### Tests
`tests/test_links.py` — generate_id format/alphabet/uniqueness; generate_unique_id collision-avoid/retry/sys-exit; split_link_target; resolve_link (record 0-based lineno, todo open/done, journal, whole-token match, missing); list_link_ids dedupe/sort; check_dangling_links (dangling record/todo, duplicate record/todo, clean); append_links merge/dedupe; append ids rewrite/raise/custom; todo parse-format-semantic round-trip, edit/batch id+links, filter linked_to, rewrite_line_by_number; validate_record accepts id/links; backlinks include `links=`/`links:`; backlink_refs find/empty/unrelated; `--add --link` resolve-warning via CLI main; `--add id=` duplicate rejection; `apply_set` id/links validation; `run_set` delete warning; todo done/delete/done-delete warnings; remove_type awareness message; service retro-id/link-entries (record + todo source, missing source, unknown target resolves=False); lint flags dangling links; `tests/test_notes.py` covers note id, resolve_link note, list_link_ids note, check_dangling_links note duplicate, delete backlinks

## Bracket cross-linking (`[[Target]]`)

### Overview
Wiki-style `[[links]]` sit on top of existing project conventions — not a replacement for `project=value` (Records) or `+project` (Todo). A `[[link]]` in a note or journal entry is a real cross-reference; if it matches an existing project name, that's a bonus.

### Backend — `/api/link-candidates`
- `GET /api/link-candidates?q=...` — returns up to 20 sorted candidates
- Scans `[[Target]]` brackets from journal, notes, and todo files — any text inside `[[ ]]` becomes a candidate (multi-word phrases like `[[buy house]]` work)
- Field matches are **schema-driven**: any field flagged `linkable = true` in schema (in `[fields.*]`, `[global_fields.*]`, or `[type.*.fields.*]`) is scanned for `field=value` in record `.log` files, plus `+Project`/`@Context` tokens in todo files. No hardcoded field-name regex.
- Shared scan logic lives in `ptos_service.py`: `_iter_link_matches(linkable_fields)` walks notes/journal/todo/records and yields `{source, value, loc}` matches; `get_link_candidates(q)` aggregates unique candidates; `get_backlinks(subject)` aggregates locations for one subject. Both callers use the same helper so they can't drift apart.

### Backend — backlinks panel
- `GET /api/backlinks?q=...` — returns `{"notes": [...], "journal": [...], "todo": [...], "records": [...]}` where each list holds `{...loc}` dicts for every reference to `subject` (case-insensitive exact match):
  - notes: `{rel_path, title, path, snippet}` from `[[subject]]` in note files
  - journal: `{date, path, snippet}` from `[[subject]]` in journal files
  - todo: `{line, lineno, done, path}` from `[[subject]]`, `+subject`, `@subject` (field tokens only when `project`/`context` are linkable)
  - records: `{date, type, field, path, lineno, snippet}` from `linkable`-flagged `field=subject`
- Each match includes a ~60-char `snippet` around the hit.
- Empty `q` returns all-empty groups.

### Frontend — shared JS in `base.html`
- `_getBracketToken(inputEl)` — scans backward for unclosed `[[`, returns `{query, start, fullToken}` or null
- `attachBracketAutocomplete(inputEl)` — fetches from `/api/link-candidates`, renders dropdown, handles Arrow/Enter/Escape; used on all input fields that support bracket linking
- `preprocessLinks(src)` — converts `[[Target]]` → `[Target](/search?q=Target)` markdown links for preview rendering
- `initBacklinksPanel(container, subject)` — fetches `/api/backlinks?q=`, renders four collapsible groups (Notes/Journal/Todo/Records); hides container when nothing references the subject. Used by `notes.html`, keyed on the note's title.
- `initJournalBacklinks(container, content)` — journal mode: extracts unique `[[...]]` links from the journal text, renders one expandable section per link showing that link's backlinks. Used by `journal.html` (loads once on page load, no live updates).
- Item link targets: note → `/notes/edit/<rel_path>`, journal → `/journal?date=...`, record → `/editor?file=<path>&goto=<lineno>`, todo → `/todo?search=<line>`.

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
| Notes | `ptos.py` (file explorer CRUD + template resolution), `ptos_service.py`, `ptos_web.py`, `web_templates/notes.html` (browse), `web_templates/notes_edit.html` (editor) |
| Board/Kanban | `ptos_service.py` (get_board_data, board_field_overlap, board_advance), `ptos_web.py` (routes), `web_templates/query_builder.html` (board editor), `web_templates/board.html` (Kanban view) |
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
- **Do not commit unless the user has tested the change.** The user tests first, then explicitly asks to commit. Don't pre-emptively commit just because tests pass or the change looks done. Exception: pure docs/infra commits the user explicitly asked to commit.
- Only commit when explicitly asked
- Stage only intended files, never commit secrets
- Run `python -m pytest tests/ -v` before committing

### Changelog (mandatory, enforced)

- Every commit that changes **product files** (ptos modules, `desktop_app.py`, `web_templates/`, `web_static/`, `starters/`, root `schema.toml`/`config.toml`) must include its **CHANGELOG.md entry in the same commit** — each entry correlates 1:1 with a commit.
- **Exempt**: pure docs (README/AGENTS/meta) and test-only refactors (tests/ files are outside the product pattern, no entry needed).
- Keep the existing format: `## YYYY-MM-DD` section (append to today's if present), `### Heading` per logical change, bullets with **bold lead-ins**.
- The pre-commit hook enforces this: staging product files without a staged `CHANGELOG.md` change blocks the commit.

## Pre-commit hook

A git pre-commit hook runs the test suite, blocks commits on failure, and blocks commits that change product files without a staged CHANGELOG.md change.

```bash
cp scripts/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

Use `git commit --no-verify` to bypass (only for genuinely unrelated
pre-existing failures).
