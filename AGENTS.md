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
config/          → User config (created by --init, gitignored)
records/         → Log files (YYYY.log)
journal/         → Markdown journal entries
todo/            → Todo files (todo.txt, done.txt, done.YYYY.txt)
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

**Known pre-existing failures (7):** `tests/test_config.py` and `tests/test_dates.py` fail during full suite runs because `ptos_service.py` patches `sys.exit` globally. These tests expect `SystemExit` but get `PTOSError`. Not related to any feature work — ignore them.

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

### Error handling
- Engine functions raise `sys.exit()` on errors
- `ptos_service.py` patches `sys.exit` to raise `PTOSError` instead (so web routes can handle errors gracefully)
- Web routes catch `PTOSError` and return JSON error responses
- CLI catches `PTOSError` and prints user-friendly messages

### File safety
- All writes use `.bak` + `.tmp` + atomic rename pattern
- `save_todos()` in `ptos_todo.py` follows this pattern
- Never write directly to data files without backup

### Web patterns
- Routes in `ptos_web.py` call `svc.*` functions (service layer)
- Service functions call `ptos_*` module functions (engine)
- Templates use `{{ variable }}` and `{% if %}` / `{% for %}`
- Forms POST JSON, routes return JSON (`jsonify(ok=True/False, ...)`)
- SSE: daemon thread polls data, broadcasts events, browser handles notifications

### Testing patterns
- Tests in `tests/` mirror module names (`test_todo.py` → `ptos_todo.py`)
- Use `tmpdir` pytest fixture for file-based tests
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
`raw_line`, `done`, `priority`, `completed_date`, `created_date`, `description`, `projects`, `contexts`, `due`, `due_time`, `sched`, `sched_time`, `line_no`

### Key functions
- `parse_todo_line(line)` — parses one line into Todo object
- `format_line(todo)` — formats Todo back to todo.txt line
- `preprocess_todo_text(text)` — converts `pri:a`, resolves NL dates, handles two-token time patterns
- `resolve_todo_date(s)` — returns `(date, time_str|None)` tuple; supports `today`, `tomorrow`, `yesterday`, weekdays, `this_week`, `next_week`, `this_month`, `next_month`, `+Nd`, `+Nw`, `+Nm`, `YYYY-MM-DD`
- `archive_done_todos(path, months)` — moves old done items to `done.YYYY.txt`

### Web UI features
- **Quick add bar** with autocomplete dropdown (prefix-aware: `+`, `@`, `due:`, `sched:`, `(`)
- **Quick pick chips** (collapsible) — Priority (A-D), Due shortcuts (today/tomorrow/this_week/next_week/this_month/next_month), Scheduled shortcuts, Projects, Contexts as toggle chips
- **Filter chips** (collapsible) — Context, Priority (A-D), Due Range (overdue/today/upcoming/someday/none) — all toggle on click
- **Form modal** (shared add+edit) — Priority as dropdown (None/A/B/C/D), Projects and Contexts as clickable toggle chips with "+ New" for adding new ones
- **Clickable todo chips** — project, context, and priority chips on each todo row link to filtered view; clicking an active filter chip removes that filter
- **Project rail** — horizontal scroll filter with toggle behavior
- **Overdue/Today/Upcoming/Someday** bucket view with collapsible Done section
- **Today progress** counter (done/total)
- **Help card** — todo.txt format reference
- **System notifications** — native OS notifications via `_system_notify()` in background thread; detects platform (Linux: `notify-send`, macOS: `osascript`, Windows: PowerShell toast, Android: `termux-notification`); runs alongside browser SSE notifications

### Autocomplete system
- `_acData` object holds suggestions per prefix (`+`, `@`, `due:`, `(`)
- `_getCurrentToken()` parses the word being typed and detects its prefix
- `onTodoInput()` filters `_acData` by typed text and shows dropdown
- `handleInputKey()` handles ArrowUp/Down/Enter/Escape navigation
- `pickAC()` inserts selected suggestion with trailing space
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
| Schema/validation | `ptos.py`, `schema.toml` |
| Web UI patterns | `web_templates/base.html`, neighboring templates |
| CLI flags | `ptos_cli.py`, `ptos.py` |
| Config | `config/config.toml`, `starters/starter_config.toml` |
| Tests | `tests/test_*.py` |

## Commits

- Write concise commit messages matching repo style
- Only commit when explicitly asked
- Stage only intended files, never commit secrets
- Run `python -m pytest tests/ -v` before committing (accept 7 pre-existing failures)
