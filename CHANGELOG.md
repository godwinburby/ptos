# CHANGELOG

All notable changes to PTOS are recorded here.
Format: `[version or date] — description`

---

## 2026-08-05

### Schema-driven linkable fields + backlinks panel

- **`linkable` schema flag** — field metadata now supports `linkable = true` (same shape as `aggregatable`), marking a field as backlink-searchable. Scanned across `[fields.*]`, `[global_fields.*]`, and per-type `[type.*.fields.*]` via `ptos.get_linkable_fields()`. Starter + live schema ship `project` and `context` as linkable, preserving the previous behavior exactly
- **Hardcoded regex removed** — `/api/link-candidates` no longer hardcodes `project|context`; it derives the field list from `get_linkable_fields()` at request time. Marking any field `linkable = true` makes it link-candidate + backlink-searchable with zero code changes
- **Backlinks panel** — new read-only "Linked mentions" panel showing every reference to a subject (case-insensitive exact match) across notes, journal, todo, and records, each with a short snippet and click-through link:
  - Notes view (`notes.html`) — keyed on the note title
  - Journal view (`journal.html`) — one expandable section per `[[link]]` found inside the journal entry
- **Shared scan helper** — `ptos_service._iter_link_matches()` walks notes/journal/todo/records once; `get_link_candidates(q)` (unique candidates) and `get_backlinks(subject)` (locations) both build on it, so they can't drift out of sync
- **Schema Builder** — `linkable` checkbox added next to `aggregatable` in Field Metadata, Global Fields, and per-type field rows; persisted by `_build_schema_dict()`
- **Tests** — `test_backlinks.py` (case-insensitive match, linkable vs non-linkable field regression, starter upgrade-safety, todo `+project`/`@context`, no-references, snippet at file boundaries) and `test_link_candidates.py` (custom linkable field picked up, non-linkable excluded). Conftest now clears the engine cache after copying starter configs so tests never read stale schema

---

## 2026-07-31

### Board column rollups

- **Per-lane rollups** — board columns can now show `sum` / `avg` / `count` over an aggregatable field (e.g. `amount`). Config keys `rollup_field` + `rollup_op` (default `count`) in `[board.NAME]`; rollups computed over the full matched record set before the card limit truncates the display, skipping non-numeric values. Columns whose type lacks the field show count only
- **Rollup validation on save** — `save_queries_full()` persists `rollup_field`/`rollup_op` and rejects a field that isn't `aggregatable = true` in schema or applies to none of the board's column types
- **Mixed-type boards** — `/api/board/field-overlap` returns `aggregatable_all` (aggregatable fields on any column type), so the Query Builder Rollup Field dropdown works for boards mixing types with different fields
- **Query Builder round-trip** — `/query-builder` boards payload now includes `rollup_field`/`rollup_op`, so saved rollup settings survive page reloads and Save All
- **Template formatting** — board lane headers render `rollup_fmt(v)` / `avg {{ rollup_avg_fmt(v) }}` / `count N`; `/board` route passes formatters from `ptos.fmt`/`fmt_avg`
- **README** — documented rollup config and behavior in the Board (Kanban) section

---

## 2026-07-13

### Android — git migration, code/data split

- **`setup_ptos_android.sh`** — rewritten: code installs to `$HOME/ptos` (Termux native home) via `git clone`; data lives in `$HOME/storage/shared/ptos-data` (shared storage, Syncthing-visible). Auto-installs git via `pkg` if missing. Removed zip download and `.version` SHA tracking.
- **`start_ptos_android.sh`** — update block replaced: zip download + `PRESERVED` blocklist replaced with `git fetch; git pull --ff-only`. No data-clobber risk — code and data are now cleanly separated.
- **`.ptos_home` bootstrap** — Android setup writes `.ptos_home` to point code at data dir, reusing the existing mechanism already supported by `ptos.py`.
- **Sync scoping** — `ptos_sync.py`'s `run_sync()` now correctly syncs only data dir by construction (no code files in `BASE_DIR`), without any `ptos_sync.py` changes.

### Sync — rclone bisync for OneDrive

- **`ptos_sync.py`** — new module: `SyncResult` dataclass, platform detection (windows/linux/termux), rclone bisync command builder, concurrency guard with `threading.Lock`, first-run `--resync` safety (`resynced` config flag), conflict parsing from rclone output, mtime-based change detection via `.sync_state`
- **Sync auto-disable** — `get_sync_config()` returns `enabled: false` when rclone is not found (Linux) or platform is Windows (no-op, native OneDrive app)
- **Web UI** — new Sync card in Settings: enabled toggle, remote name/path, folder checkboxes, status dot (idle/running/ok/conflict/error), Sync Now and Force Resync buttons, conflict list
- **Sidebar sync badge** — colored dot with pulse animation during sync, updated via SSE `sync-status` events
- **`_housekeeping_loop`** — renamed from `_todo_notify_loop`; piggybacks sync every ~6th tick
- **Startup and manual sync** — one-shot async sync on launch; `POST /sync/run` and `GET /sync/status` endpoints
- **`starter_config.toml`** — added `[sync]` section (default off)
- **`.gitignore`** — added `.sync_state`, `.sync.log`
- **Auto-disable without rclone** — sync enabled in config is overridden to off when `_which("rclone")` returns None (non-Windows)
- **Back of house** — renamed `_todo_notify_loop` → `_housekeeping_loop` in `ptos_web.py`; added sync wrappers to `ptos_service.py`

### Path separation — `.ptos_home` bootstrap

- **`.ptos_home` bootstrap file** — new mechanism to persist `PTOS_HOME` without an env var. PTOS reads `{script_dir}/.ptos_home` on every launch; written automatically by `--init`. Priority: env var > `.ptos_home` > data next to code.
- **`SCRIPT_DIR` constant** — `ptos.py` now tracks the script directory separately from `BASE_DIR`. Starters, `.version`, and `.git` are resolved relative to `SCRIPT_DIR`; data directories (`records/`, `config/`, `journal/`, `todo/`) relative to `BASE_DIR`. This enables clean code/data separation.
- **`ptos_todo.py`** — no longer duplicates path resolution; imports `BASE_DIR`, `TODO_DIR`, `TODO_PATH`, `DONE_PATH` from `ptos.py`.
- **Backup defaults** — `BACKUP_FOLDERS` now includes `journal` and `todo`.
- **`.gitignore`** — cleaned up for code-only repo (removed data directory entries).
- **Deleted** `scripts/` and `tasks/` directories (unused).

## 2026-03-28

### Robustness — crash fixes

- **Safe parse in analysis** — added `safe_parse_line()` helper; all analysis functions (`group_results`, `pivot_results`, `show_fields`, `render_summary`, `_render_single_table`, `render_table`, `export_csv`) now skip malformed lines instead of crashing
- **`--add` bad argument** — `ptos --add typeexpense` (missing `=`) now shows a friendly error instead of a raw `ValueError`
- **TOML parse errors** — syntax errors in any config file now show a clear message with the file path instead of a raw Python traceback
- **Editor not found** — `--edit` and `--lint --fix` now catch `FileNotFoundError` and tell you how to fix it
- **Schema structure errors** — missing `[types] allowed` in schema.toml now exits with a clear message; invalid type now lists the valid types
- **Query field errors** — `where` not a string, or `trend` not an integer in queries.toml, both exit with a clear message naming the query and the problem

### Usability improvements

- **Save prompt** — `--add` interactive save changed from `(Y/n)` (Enter = save) to `(y/N)` (Enter = cancel) to prevent accidental saves
- **Empty preset list** — `ptos -p` with no presets defined now shows a helpful hint instead of a blank list
- **Invalid `--time` keyword** — error now prints the full valid keyword table inline instead of saying "run --help"
- **`--lint` summary** — output now starts with `Checked N record(s) across M type(s) [type:count ...]`
- **`--where` typo warning** — empty results now warn if a filter field name doesn't exist in any record
- **`--lint --fix`** — new flag: after linting, opens each log file containing errors in the configured editor
- **`--due` name display** — column header now reflects whether `name` or the key field is being shown
- **`--export` for grouped output** — `--group` + `--export` now exports a proper grouped CSV with count and total columns
- **`--export` for pivot output** — `--pivot` + `--export` now exports a proper pivot CSV with all columns and row totals
- **`--trend` with custom date range** — `--from`/`--to` + `--trend N` now divides the custom range into N equal slices

### Documentation

- **README** — added Short flag column to all CLI reference tables
- **README** — added `exports/` to folder structure diagram
- **README** — added `--sum-field` section with examples
- **README** — added Automatic backups section
- **README** — added preset aliases section
- **README** — added multi-record presets section
- **README** — updated `--export` section to cover grouped and pivot export
- **README** — updated `--trend` entry to mention `--from`/`--to` support
- **README** — added `--lint --fix` to Utilities table
- **CHANGELOG.md** — this file, created

---

## Earlier (pre-session baseline)

### Core engine
- Single-file Python CLI (`ptos.py`) with no dependencies beyond stdlib
- Append-only plain-text log format: `YYYY-MM-DD key=value ... | note`
- `--add` interactive and inline modes with schema-driven validation
- `--preset` quick-add with field overrides, alias, and multi-record support
- `--query` named queries, metrics (ratio/avg/sum/max/min), dashboards
- `--group`, `--pivot`, `--trend`, `--due`, `--table`, `--sort`, `--select`
- `--export` CSV to `exports/` with auto-naming
- `--sum-field` to target a specific numeric field
- `--lint` two-pass validation (anatomy + schema)
- `--fields` discovery report with suggested group/pivot commands
- `--journal` daily journal from template
- `--edit` shortcut to open any workspace file
- `--init` idempotent workspace setup
- `_backup_file()` before every write operation
- Indian number formatting for ₹ currency
- `PTOS_HOME` environment variable support
- Full short-flag aliases for all major flags
- Custom billing cycles in config.toml
- `--from`/`--to` for arbitrary date ranges
- `--save` to persist any CLI filter as a named query
- `--save-preset` to persist any add as a preset
