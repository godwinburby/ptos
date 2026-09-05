# CHANGELOG

All notable changes to PTOS are recorded here.
Format: `[version or date] — description`

---

## 2026-09-05

### RecordTable: client-side CSV export on the shared component

- New `RecordTable._export()` in `web_static/js/record_table.js`: downloads the currently-displayed records as a CSV blob (header from `_cols`, values via the same case-insensitive key lookup `_buildRows` uses, `""` escaping for quotes, all fields quoted) — no page navigation, honors the on-screen sort order
- A **↓ CSV** button appears in the table's summary bar whenever `RecordTable` renders (count/total/avg/time-label row is now a flex row with the button); it only renders for the flat records view — group/trend/threshold result kinds still bypass `RecordTable` and get no button
- Re-exposed on all **four** `RecordTable` consumer pages (browse.html, home.html, query_builder.html, queries.html), each passing a per-page `exportName`: `browse_results.csv`, `recent_records.csv`, `query_results.csv`
- **Cache-busting**: `record_table.js` is now included as `...?v=2` on all four pages (service worker `ptos-v3` is cache-first keyed on full URL, so the `?v=` query busts the stale cached copy — same pattern as `filter_builder.js?v=2`, no SW version bump)
- **Existing server-side `/browse/export` is untouched**: browse keeps its sidebar **↓ CSV** button (full fresh re-query, dynamic `{type}_{time_label}.csv` filename) alongside the new table-level one (exports what's on screen) — redundant when browse always loads the full uncapped result set, both are harmless today; revisit retiring the server route only if browse ever paginates

### AGENTS.md: record_table export coverage
- Documented the `RecordTable._export` button + `exportName` option + the four consumer pages

---

## 2026-09-04

### Ratio metric: sum-metric operands (Query Builder + fix revenue_percent)

- **Bug fix**: a `ratio` metric whose operands are **sum metrics** (e.g. `ratio = ["total_revenue", "target_revenue"]`) now correctly uses the summed values. Previously the UI could only pick base queries for ratio operands (each resolved as a **record count**), so a "revenue ÷ revenue-target" ratio silently became `count(fitting) ÷ count(target)` — e.g. `revenue_percent` showed **500% (5/1)** instead of the intended **98.2% (₹3,18,200/₹3,24,000)** for July 2026. The engine/service already resolved sum-metric operands to their total (ptos.py `_resolve_ratio_operand`, ptos_service.py `get_metric` `_resolve`); only the editor prevented setting them
- **Query Builder metric editor**: the two ratio operand dropdowns now offer **base queries *and* resolvable (non-derived) metrics**, each labeled with its kind (e.g. `total_revenue (sum)`), so sum-vs-sum ratios like revenue ÷ target are expressible from the UI; the "Metric type" ratio description and operand help text now note that plain queries count records while sum metrics use their summed value
- The workspace `revenue_percent` config was updated to `ratio = ["total_revenue", "target_revenue"]`, verified as `98.2% (318200/324000)` on both web (`get_metric`) and CLI (`run_metric`)
- Tests: `test_metrics.py::TestRunMetric::test_ratio_sum_metrics` locks in sum-metric ratio resolution (318200/324000 → 98.2%)

### Board page uses the shared time-window picker (URL-driven)

- The board page's flat inline `<select>` (which previously wrote `time_window` straight into `queries.toml` via `POST /api/board/time-window`) is replaced with the **shared `_time_picker.html` component** (prefix `brd-`), matching Habits/Thresholds: fixed named windows plus Year/Month/Date/Range picker sub-widgets
- The board's window is now a **URL round-trip view override** (`time`/`custom_time`/`from_date`/`to_date` params, e.g. `/board?board=NAME&time=range&from_date=...`), preserved alongside the existing `?board=` selection; when no params are present it falls back to the board's config `time_window` (set in the Query Builder board editor), which is no longer mutated by the page dropdown
- Removed the legacy `_board_time_options()` (web), the `POST /api/board/time-window` route (web), and `update_board_time_window()` (service, now orphaned); `get_board_data()` gains optional `time`/`from_date`/`to_date` params with precedence `from_date → time → config time_window` and returns the effective window label
- **Bug fix**: the board page's `<select>` id is `brd-time-select` (not `board-time-window`) so it matches the `brd-` prefix that `_time_picker.html`/`time_picker.js` expect — otherwise `getTime()`/`setTime()` return null and the picker silently resets to "Default (per board)" after choosing a month/date
- Tests: `TestGetBoardData` gains `time`-param and `from_date`/`to_date`-range cases plus precedence checks; new `TestBoardRouteTimeWindow` exercises `/board` rendering range/year/month params via the Flask client (including the `brd-time-select` id to lock the prefix convention); the removed `TestUpdateBoardTimeWindow` is deleted

### Board: cross-column match highlight (generic / schema-agnostic)

- New optional `match_field` board config key (e.g. `match_field = "client_code"` on `["board.client_sale_journey"]`) enables **cross-column color highlighting**: records across the board's columns that share the same `match_field` value get the **same color**, provided that value appears in **≥2 distinct columns** (a lone record with no sibling in another column stays uncolored — so a prescription with no fitting shows uncolored)
- **Fully generic**: the engine/service contain zero field/type/schema assumptions — the only field name is whatever a board's `match_field` config supplies; no `match_field` (or a blank one) → feature inactive (`match_field=None`, no colors)
- Implementation: `get_board_data()` computes a `value → color` map over the FULL per-column record set (before `limit` truncation, same as rollups) into the **16-color board palette** (`accent`/`purple`/`teal`/`rose`/`slate`/`warn`/`success`/`error`/`indigo`/`cyan`/`lime`/`amber`/`pink`/`brown`/`navy`/`olive`); each matching record gets `_link_color` + `_link_group` (the matched value); `match_field` returned in board data. **No color overlap** for up to 16 distinct matched codes in one view: colors are assigned by **sorted order over the visible matched set** (`index % 16`), so different codes never share a color (previously the palette widened to 16 but used `hash(value) % 16`, which still collided — e.g. 2 codes `test`/`sb.i56` both mapped to `pink` in the current-month view); colors are deterministic for the same code set; past 16 distinct codes reuse is fundamental
- `board.html`: `hl-{color}` classes (colored left border + light background tint) applied to cards, plus a colored dot + matched-value badge on the card so the grouping reason is visible
- `save_queries_full()` persists `match_field` (like `rollup_field`); Query Builder board editor gains a free-form **Match Field** text input
- CLI parity (`run_board`): prints `match_field: <field>` header and a colored token per matched record so matching is exercised headlessly
- Tests: `TestBoardMatchHighlight` (same-color across columns, lone value uncolored, empty/absent skipped, stable color, matching over full set before limit, distinct groups differ), `match_field` persistence round-trip in `TestSaveQueriesFullBoard`, and CLI output tests in `TestCliBoard`

### Board drag-and-drop: date follows the browsed window

- Dragging a card to another column now stamps the new record with a date that follows the board's **effective display window** instead of always using today: if the effective window (URL `time`/`custom_time`/`from_date`/`to_date` params overriding the board's config `time_window`, same resolution as `get_board_data`) **is the current calendar month** — or no window context is passed (direct callers/tests) — the card is dated **today**; otherwise it keeps the **source record's original `YYYY-MM-DD`**, so an advanced card stays in the period being browsed (e.g. dragging within a `last-quarter` view stamps the source date, not today)
- `advance_record()` gains `board_name`/`win_time`/`win_from`/`win_to` params resolved by a new `_advance_target_date()` helper (URL param precedence, `last-3-months` config special case, default `this-month`); `ptos_web.py::board_advance` passes them from the drag payload; `web_templates/board.html::onDrop` sends the board name + current URL window via a new `_currentWindowParams()` helper — the auto-append path only, the `missing_required` redirect-to-add path is unchanged
- Default behavior unchanged (no window context → today), so existing direct calls keep working
- Tests: `TestAdvanceRecord` gains date-aware cases (no-context→today, current-month→today, past `win_time`/range/config-window→source date)

### Board: Client grid view (row-per-matched-value alignment)

- `/board` gains a **view toggle** (`Kanban` / `Client grid`), shown only when the board sets `match_field`; `?view=kanban` (default) renders the classic drag-and-drop kanban unchanged, `?view=grid` renders a **row-per-client grid** where records sharing a `match_field` value align horizontally across columns so the whole client journey reads left-to-right
- The grid reuses the existing card markup + `hl-{color}` highlight (each row label is the matched value with its color dot, and only matched records are colored the same); one cell per board column holds that client's stacked cards (dashed placeholder when the client has no record there)
- `get_board_data()` returns three **additive** keys that leave the kanban shape untouched: `grid_rows` (ordered `[{value, color, cells:{col_type:[records]}}]` built from the displayed records, sorted by value matching the color order), `unmatched` (`{col_type:[records]}` — lone/missing-value records, rendered as per-column groups below the grid), and `has_matching` (bool)
- `ptos_web.py` `/board` reads/validates `view`; `board.html` `switchView()`/`updateUrl()` preserve `view` alongside `board` + time params; new CSS classes `.bg-grid`/`.bg-table`/`.bg-row`/`.bg-label`/`.bg-cell`/`.bg-placeholder`/`.bg-unmatched*`
- Tests: `TestBoardGrid` (cells stacked preserving per-column order, blank cell when a matched value has no record in a column, lone/missing values into unmatched, no-match_field disables the grid, row sort order), `TestBoardGridView` route checks (`?view=grid` renders grid markup, `?view=kanban` renders kanban, toggle shown only when `match_field` set, view/board params preserved)

### Board: drag-and-drop in the Client grid (same-client-row rule)

- The grid now supports **drag-and-drop** (previously read/edit-only) by reusing the kanban handlers, generalized to also work on the grid's `.bg-cell` (matched) and `.bg-unmatched-lane` (unmatched) drop targets via `_sourceType`/`_dropType`/`_dropEl` helpers
- **Matched cards** (inside a `.bg-row`) can only be dropped into another stage cell **on the same client row** — including the row's empty placeholder cells — so a client's journey advances within itself; dropping on a different client's row is rejected (rows are keyed uniquely by the `match_field` value, so "same row" == "any row with the same matching field"). `_dragData.srcRow` enforces this in `onDragOver`/`onDrop`
- **Unmatched cards** (single-record clients, no row) can be dropped into **any** board column (kanban-style), filling the gap so a lone record can gain a sibling and become a matched client
- Grid cards render `draggable="true"` with the standard drag handlers; `.bg-cell`s and `.bg-unmatched-lane`s render `ondrop`/`ondragover`/`ondragleave` + a `data-col-type`; new `.bg-cell.drag-over`/`.bg-unmatched-lane.drag-over` drop highlights
- Tests: `TestBoardGridView` asserts grid cards are draggable with the standard handlers, cells/lanes are drop targets with `data-col-type`, rows carry the client identity (`data-row`), and the same-row guard JS is present

### Board: advance always keeps the source record's date

- `advance_record()` now **always stamps the new record with the source record's original `YYYY-MM-DD`** — the single simple rule that an advanced card always stays in the period it was dragged from. The window-aware `_advance_target_date()` helper and the `board_name`/`win_time`/`win_from`/`win_to` params were removed from `advance_record`, `board_advance` (web) no longer passes them, and `board.html::onDrop` no longer sends them (along with the now-unused `_currentWindowParams()`)
- This replaces the previous behavior where the new card was dated **today** when the effective display window was the current calendar month (or no window was given) and kept the source date otherwise — a more nuanced but heavier rule
- Tests: `TestAdvanceRecord` collapses the five date-aware cases into one `test_advance_keeps_source_date`; everything else unchanged

## 2026-09-02

### CLI parity: search, links, config, calendar, board (`--backlinks`/`--find`/`--link-ids`/`--config`/`--calendars`/`--board`)

- `--backlinks SUBJECT` — prints every reference to a subject (note base name, `[[bracket]]` target, or `type:id`) grouped by notes/journal/todo/records, via `svc.get_backlinks()`; `--link-ids` lists all `type:id` targets from records/todos/notes; `--find TEXT` mirrors the web universal search (records, journal, todos incl. `done.*.txt`, notes, `template.md` excluded, glob `*`/`?` wildcards + ~160-char snippets)
- `--get-config KEY` / `--set-config KEY VALUE` — dotted config paths (e.g. `todo.priority_labels.A`, `sync.remote_name`, `home.quick_presets`); `true`/`false` read as bool, pure numbers as int/float, missing sections auto-created; reads/writes `ptos.CONFIG_PATH` at call time so the tests' monkeypatching works, and `_invalidate_all()` runs after writes
- `--calendars [NAME]` — ASCII month grid (`.` empty, `1-9` count, `#` 10+) for the global All-records view or a named `[calendar.*]`; `--board [NAME]` prints per-column counts + date/card-title/note lines (capped at 15 per lane) honoring the board's time window and limit
- `--habits` now honors `-t/--time` (incl. `--time weeks` → per-habit weeks)
- 25 new CLI tests (`tests/test_search_cli.py`, `tests/test_config_cli.py`, `tests/test_views_cli.py`); all thin wrappers in `ptos_cli.py`, zero `ptos.py` changes

### Notes CLI (`--notes`) for 1:1 CLI/web parity

- New `--notes ACTION...` entry point in `ptos_cli.py` (`_handle_notes`), a thin wrapper over existing engine/service functions (no new logic in `ptos.py`): `list [PATH]` (browse folders + `.md` files), `template PATH` (resolved new-note template), `new PATH --name N [--content C]` (templates applied, parent template prompts, non-TTY blanks), `read PATH` (content + backlinks summary), `edit PATH` (opens in configured editor, covers `template.md`), `delete PATH [--force]` (warns + confirms when the note has backlinks, refuses on non-TTY without `--force`), `id PATH` (print/generate `ptos-id`)
- Backlink subject is the **file base name** (same key the web backlinks panel uses via breadcrumb label), stable across `--notes id` prepending a ptos-id comment
- Folder create/rename/delete are deliberately **not** CLI actions (`mkdir`/`mv`/`rm` suffice); the path argument must follow the action directly
- 24 new tests in `tests/test_notes_cli.py`; AGENTS.md Notes section documents the CLI and corrects the stale "template.md excluded from listings" claim (`list_dir`/web/CLI all show it — it's only skipped by bracket-scan)

### Habits: default window follows the app-wide "this month"

- The default view is now the **app-wide `this-month` window** (same as every other page), so `/habits` no longer surprises by defaulting to ~12 weeks back; the streak badge is **decoupled from the display window** and always counts over the habit's configured `weeks` (default 12) ending today, so a long streak shows fully even under a one-month view
- Dropdown: "This month (default)" (empty value) + new **"Per-habit weeks"** option (`?time=weeks`) that restores the old per-habit `weeks` window; cache key for the default is now `habit:{name}:tm:` (shared with explicit `tm`), `weeks` config repurposed as streak-history span
- 3 new tests (`test_default_window_is_this_month`, `test_streak_independent_of_display_window`, `test_weeks_code_uses_per_habit_window`); weeks-window assertions moved to explicit `time="weeks"` calls

### Habits: calendar-style month blocks + time-window dropdown

- Heatmap is now rendered as **per-month calendar blocks** — each month is its own bordered block with a "July 2026" name header, an M–T–W–T–F–S–S weekday row, and weeks as rows; leading blanks align the 1st under its weekday, trailing blanks pad each month to full weeks, today is outlined (`.habit-cell.today`), and a `range_label` caption ("Aug 11 – Sep 2, 2026") replaces the generic "last N weeks" text; legend gains a Today swatch
- Grid presence per day is boolean; future days past today are never rendered; giant windows (e.g. "All time") are capped at 260 columns by trimming whole weeks from the front
- **Time-window dropdown** (`_habit_time_options()`): This/Last month, quarter, year, All time, custom `[cycles]`, and Month/Date-range pickers — reused from the shared `_time_picker.html` component (prefix `hab-`), round-tripping `time`/`custom_time`/`from_date`/`to_date` URL params like `/thresholds`; tiny windows (today/yesterday/this,last week) excluded since they don't fit a week grid
- `get_habit_data()` accepts `time`/`from_date`/`to_date` (resolved via `_resolve_time`/`parse_from_to`; `time="weeks"` for the per-habit window), returns per-month `months` blocks, and its cache key is per habit + window (`habit:{name}:{time}:{from}:{to}`), still invalidated on any record write
- **`--habits [NAME]` CLI command** — `run_habits()` in `ptos_cli.py` prints the same per-month calendar blocks in text (`#` present, `.` miss, `^` today) with a streak/days-done/range header per habit; `--habits NAME` filters to one habit, unknown names exit with a friendly message, no habits configured prints the config hint
- 12 new tests (`TestHabitWindow`, `TestHabitMonths`, `TestHabitCli`); habit test dates made year-robust (`_write_records` no longer hardcodes 2026)

## 2026-09-01

### Browse: group-by / sort-by dimension fields

- Group by / Sort by dropdowns on `/browse` are populated with **dimension fields only** (fields flagged `dimension = false` and int fields excluded; `date`/`day`/`month`/`year` always included), the same rule `api_type_fields` uses
- Cross-type (no type selected) view uses a server-side global dimension union; selecting a single type immediately narrows the dropdowns to that type's dimensions so fields from other types never appear
- Cache-busted `filter_builder.js?v=2` + service worker cache bump to `ptos-v3` so stale cached JS can't silently revert the behavior

### Record dates & Todo Overdue

- Record forms (add/edit) accept past, present, and future dates — the HTML `max` cap that blocked future dates was removed (the backend never restricted dates)
- Todo Overdue section in the timeline grouping is **collapsed by default** (still toggleable via the section header)

### Filter expressions: spaced operators + missing-field semantics

- `_tok_where` now collapses spaced `field op value` token triples, so `tag != snacks` parses identically to `tag!=snacks` and `NOT (tag=snacks)` (previously the spaced form was silently dropped)
- `!=` / `!~` now match records **missing the field entirely** (NaN-like, equal to `NOT (field=x)`); `=` and ordered comparisons remain `False` for missing fields
- 14 regression tests added (`TestSpacedOperators`, `TestNotEqualsMissingKey` in `tests/test_filters.py`); AGENTS.md documents the filter expression syntax

## 2026-08-31

### Kernel boundary: promote internal helpers to public (Phase 1)

- Promoted `_filters_to_expr` → `filters_to_expr`, `_journal_path` → `journal_path`, `_note_id_of` → `note_id_of` in `ptos.py`; old underscore names kept as thin internal aliases for one release
- Updated external call sites: `ptos_cli.py` (filters/note-id), `ptos_web.py` (journal path — the one direct web→ptos call), `ptos_service.py` (filters/note-id wrappers)
- This is step one of the kernel-boundary containment (see `ptos-kernel-boundary-audit.md`): pure, side-effect-free helpers may be called directly; side-effecting operations will route through `ptos_service.py` in later phases
- No behavior change — full suite green retained

## 2026-08-28

### Dashboard grouping UX + rename/order

- Rename the **ungrouped** section: dashboard editor gets a ✎ on the ungrouped box → sets `ungrouped_label = "..."` in `[dashboards.NAME]`; Home and CLI render it as that section's header. Works on flat (no named groups) and grouped dashboards
- **Reorder groups** by dragging a group's ⠿ grip onto another group box; the saved TOML order drives Home and CLI section order
- Quick-add preset count is configurable: `[home] quick_presets` in `config.toml` (default **10**) controls how many most-used presets show on Home and Add Record (rest under "Show all")

### Dashboard metric grouping

- Dashboards can now organize metrics into labeled groups on Home via an optional `groups = { "Name" = ["metric1", "metric2"] }` key in `[dashboards.NAME]` (`queries.toml`); `metrics` stays the flat union, so old dashboards are untouched
- `get_dashboard()` returns an ordered `groups` list — ungrouped leftovers first (headerless), then each group in definition order; falls back to `None` when no groups configured (exact old behavior)
- Home page renders each group under a small uppercase `.stat-group-label` header with its own stat-card grid; highlights (`c-{color}`) still apply per metric
- Query Builder dashboard editor: drag chips **between** group boxes (`General (ungrouped)` + one box per group), with `+ New group`, per-group rename (✎) and remove (×)
- CLI: `--add-dashboard NAME --dash-group GROUP:M1,M2 GROUP:M2,M3` seeds groups (members auto-merged into `metrics`); `run_dashboard()` prints bold group headers
- Highlight picker falls back to flattening `groups` when `metrics` is empty; Share Schema preserves `groups` (filtering members to included queries/metrics)
- Tests: 13 in `tests/test_dashboards.py` + 2 in `test_export.py` + 3 CLI group tests

### Drag-and-drop highlight colors

- Settings page Highlights card now has a **color palette row** — 8 labeled swatches filled with their actual color + a dashed "⊗ clear" swatch
- **Drag a swatch onto a metric chip** to assign its color (chips show a dashed outline on drag-over); drag "⊗ clear" to remove
- Click-to-cycle kept as a mobile/touch fallback (native HTML5 DnD doesn't work on touch)
- `saveSettings()` unchanged — still reads `data-color` per chip

### Dashboard highlight colors expanded

- **8 colors** — added `purple`, `teal`, `rose`, `slate` to the existing `accent`/`warn`/`success`/`error`
- Settings page chip picker and home page stat cards support all 8
- CLI `--highlight` flag validates the full 8-color set; ANSI mappings updated
- Threshold colors unchanged (they remain semantic: ok/warning/over/met)

### Settings save button at top

- Save Settings button moved to the top of the page below the title (no more scrolling)

### Notes as link targets

- Notes can now be link targets via `<!-- ptos-id: XXXXX -->` on line 1 (opt-in, never auto-generated)
- `ensure_note_id(rel_path)` — generates and persists an id when a note is deliberately made a link target
- `resolve_link("note:X")` — walks `NOTES_DIR`, matches first-line `ptos-id` comment, returns note location
- `list_link_ids()` — third loop over notes, collects `note:XXXXX` targets for autocomplete/dedup
- `check_dangling_links()` — duplicate id detection for notes alongside records/todos
- `delete_note_entry()` — service layer checks for backlinks before deleting; returns `needs_confirm` with warning details
- Web: **"Link to this note"** button on edit view — calls `ensure_note_id()`, copies `note:X` to clipboard
- Web: **delete confirmation flow** — two-step: check backlinks → confirm → force delete
- CLI: `--retro-id note` — assigns an id to an existing note via `--search TEXT`
- 15 new tests covering all engine functions

### Notes File Explorer

- **Replaced fixed two-level notes** (`category/slug.md`) with arbitrary filesystem browsing — folders can nest to any depth, files are user-named
- **File explorer UI** (`/notes`) — folder/file listing with breadcrumbs, New Folder/New File buttons, inline rename, delete with confirmation; `template.md` shown in folder listings (editable)
- **Template resolution** — each folder may contain a `template.md`; new files inherit the nearest ancestor's template via `find_parent_template()` / `resolve_new_file_template()`
- **Concept tags** (`[[Target]]`) — existing bracket-linking infrastructure (`_iter_link_matches`, `get_link_candidates`, `get_backlinks`, `attachBracketAutocomplete`) now scans notes via `os.walk` (no separate concept-tag API needed)
- **Engine** — 9 new functions: `_safe_path`, `_validate_name`, `list_dir`, `create_folder`, `create_file`, `rename_note`, `delete_note_entry`, `find_parent_template`, `resolve_new_file_template`
- **PTOSError** moved from `ptos_service.py` to `ptos.py` (engine defines its own exceptions)
- **Old CRUD functions removed** — `list_note_categories`, `list_notes`, `read_note`, `create_note`, `save_note`, `delete_note`, `get_note_path` removed from engine and service layer
- **Search** — universal search scans notes via `os.walk` + `_glob_match`; results link to edit view with `rel_path`
- **Old templates deleted** — `notes_list.html`, `notes_category.html` replaced by `notes.html` (browse) + `notes_edit.html` (editor)
- **Backlinks panel** — `_blItemHref`/`_blItemText` updated to handle `rel_path` (with `category`/`slug` fallback)
- **42 new tests** for engine functions (safe path, validate name, list dir, create folder/file, rename, delete, template resolution)

---

## 2026-08-27

### Dashboard highlights

- **Color-coded dashboard entries** — highlight specific metrics on the home page dashboard and CLI dashboard with colored stat cards
- **Config** — `[dashboard.highlights.DASHBOARD]` in `config.toml`, maps metric names to colors (`accent`=blue, `warn`=orange, `success`=green, `error`=red); stored in config (UI concern), not queries.toml
- **Settings page** — compact clickable chips per dashboard; click to cycle colors (none → blue → orange → green → red → none); each metric independently colored
- **Home page** — stat cards render with colored background and white text via `.c-accent`/`.c-warn`/`.c-success`/`.c-error` CSS classes
- **CLI** — `run_dashboard()` reads highlights from config, applies bold ANSI colors; `run_metric()` accepts `color`/`reset` params
- **CLI flag** — `--add-dashboard NAME --metrics M1 M2 --highlight M1:accent M2:warn` saves highlights to config.toml
- **CSS** — added `.c-success` (green) and `.c-error` (red) modifier classes alongside existing `.c-accent`/`.c-warn`

### Stock tracking (schema change)

- **Replaced `stock` type** with `stock_unit` (serialized hearing aids: category, model, serial, status, date_sold) and `stock_txn` (movements: category, model, qty, serial)
- **Battery thresholds** — queries/metrics/thresholds for battery sizes 10, 13, 312, 675 (min direction, all-time, reorder point 5 units)

---

## 2026-08-15

### Thresholds — budget warnings

- **New `/thresholds` page** — progress bars comparing a computed metric against a target, with color-coded status (ok / warning / over / met)
- **Config** — `[threshold.NAME]` in `queries.toml`: `metric` (query or metric name), `agg` (`sum`/`count`), `sum_field`, `value` (literal or another metric/query name for dynamic targets), `direction` (`min`/`max`), `time`
- **Status logic** — `max`: warning ≥80%, over ≥100%; `min`: warning <50%, met ≥100%
- **Engine** — `get_thresholds()` reads config; `_resolve_value()` resolves metric/query refs; `get_threshold_status()` evaluates one threshold; `get_all_threshold_status()` evaluates all; `get_matching_thresholds(record)` checks a record against thresholds
- **CLI** — `--thresholds` flag prints a formatted table with values, targets, and status
- **Add-form integration** — debounced POST to `/api/thresholds/match` shows live threshold match bars above the form
- **Post-save preview** — add-form threshold bars show what the bar will look like after saving (client-side computation using `agg`/`sum_field` from the API response)
- **Home dashboard widget** — compact threshold card on home page; uses the dashboard's selected time window for threshold evaluation
- **Thresholds page time picker** — full time window dropdown (today, this week, this month, specific year/month/date, date range) using the shared `_time_picker.html` partial
- **Query Builder** — Thresholds tab with full editor (metric, agg, sum_field, value, direction, time); round-trips through `save_queries_full(raw_thresholds=...)`
- **Home threshold selection** — `[home] thresholds` list in `config.toml` to pick which thresholds show on the home page; Settings page checkbox list to configure; empty = show all
- **Edit-form threshold preview** — ported from Add form to Edit form; uses replacement math (`previewRaw = m.raw - oldAmount + newAmount`) for sum-type thresholds; count-type shows conservative `m.raw` (known limitation: no before/after match comparison)
- **Query Builder bugfix** — "Custom number…" input now shows on first paint for new thresholds
- **Nav** — links in desktop sidebar and mobile more menu, keyboard shortcut `G T`, icon in `web_templates/icons/thresholds.html`
- **Tests** — `tests/test_thresholds.py`: config load, metric/query resolution, status logic for all direction/pct combos, matching, save round-trip, preserves queries/metrics

### Bug fixes

- **Query Builder delete** — fixed `NameError: _normalise_query_for_write` on query/metric/dashboard delete
- **Query Builder threshold filtering** — threshold entries no longer appear in the queries list
- **Search autocomplete** — `+project` and `@context` tokens now correctly filter to project/context (not text search)
- **Project rail scroll** — added fade gradient hint on horizontal project list when content overflows

---

## 2026-08-10

### Links hardening

- **`generate_unique_id()`** — collision-safe ID generator (checks `list_link_ids()`, retries up to 5 attempts, `sys.exit` on failure). Every tool-chosen ID now goes through this (append_record_id, append_todo_id, `--retro-id`, `--add --link`)
- **`--add id=X` duplicate check** — hand-typed IDs validated against `list_link_ids()` before save; `sys.exit` on collision
- **`apply_set` validation** — `--set id=X` routes through uniqueness check; `--set links=X` routes through resolve+dangling-warning
- **`backlink_refs()` warnings** — record delete, `--todo-done`, `--todo-delete`, `--todo-done-delete` all print "N entries link to type:id — they will become dangling" when the target has incoming links
- **`--add ... --link TARGET`** — creates record with generated `id=` + `links=TARGET`; warns (saves anyway) if target doesn't resolve
- **`remove_type()` awareness** — prints a message when removing a type that existing records use ("N existing records use type 'X'; they are not modified but will fail schema validation")
- **Tests** — `tests/test_links.py` expanded: generate_unique_id collision/retry, `--add id=` duplicate rejection, `apply_set` id/links validation, `run_set` delete warning, todo done/delete/done-delete warnings, remove_type awareness message

### Bug fixes

- **Preset note** — `_strip_and_validate_record` returns `(record, note, err)` tuple; `_resolve_multi_preset`/`_resolve_preset_records` pass note through; `api_preset_add` applies per-record notes from presets with `multi` flag
- **Schema Builder shared fields** — `addField()` prompts "Add to shared definitions?" when adding a field to a type; creates `{use:"shared.NAME"}` for shared fields; preserves existing shared fields when editing type fields that reference them

---

## 2026-08-10

### Habit tracker (`/habits` heatmap + streak)

- **New `type=habit`** — added to `[types].allowed` + `[type.habit]` in starter schema (and live user schema), `required = ["name"]` with `name` options. A habit is just a record: `2026-08-10 type=habit name=meditation` — no new write path, logging reuses `append_record`/presets
- **`/habits` page** — one card per configured habit: current streak badge, GitHub-style contribution grid (weeks as columns, 7 day-rows, filled = present), and "X of Y days" summary. Grid presence is boolean — logging twice in a day still counts as one present cell. Empty state shows the config snippet. Nav link in sidebar next to Board (`icons/habits.html`)
- **Config** — `["habit.NAME"]` tables in `queries.toml` (quoted dotted key form, same as boards — the bare `[habit.NAME]` nested-table form does NOT load): `filters` (any valid `field=value` list, same syntax `find_records_with_location` takes), `weeks` (default 12). Existing types work too: `filters = ["type=exercise"]` tracks "did I exercise today"
- **Streak rule** — walks back from today, or yesterday if today isn't logged yet ("today isn't over yet" — a missed morning doesn't zero your streak until the day actually passes)
- **Caching** — `get_habit_data` cached per habit under `habit:{name}`; `_invalidate_history_cache()` now also pops `habit:` keys, so all 7 existing record-write invalidation paths cover habits with zero new call sites
- **Query Builder** — new "Habits" tab (name, space-separated `field=value` filters, weeks), round-tripping through `save_queries_full(raw_habits=...)` which validates a non-empty filters list
- **Tests** — `test_habits.py`: consecutive/gap/today-missing streak rules, double-log single present, days-done totals, cache invalidation on `append_record`, no-rescan on repeat call, unconfigured name raises `PTOSError`

---

## 2026-08-07

### Cache history/conditional suggestions

- **`get_history_suggestions(rtype, context_record)`** now splits into a cached scan-and-aggregate step (`_build_history_suggestions`, key `history:{rtype}`) and a cheap per-call context filter (`_apply_context_filter`). The full-file `scan_records(date.min, date.max)` no longer runs on every add/edit page load or cascade parent-field change — only on the first call after any invalidation. `context_record` is deliberately excluded from the cache key so `filtered_tags` still varies per request
- **`get_conditional_suggestions(rtype, field, value)`** (behind `/api/field_suggest/<rtype>/<field>/<value>`) is now fully cached per `(rtype, field, value)` under key `condsug:{rtype}:{field}:{value}` — the live AJAX cascade fill no longer does a fresh full scan per selection
- **Invalidation** — new `_invalidate_history_cache()` pops every `history:`/`condsug:` key after any record write: `append_record`, `edit_record`, `delete_record`, `advance_record`, `bulk_delete`, `bulk_set`, and `save_schema`. Correctness over precision: all types invalidated on any write, avoiding the "missed one condsug key" stale-suggestion bug class
- **Zero behavior change** — no scan-window lookback bound (scan stays unbounded); suggestions returned are identical, this is purely a performance fix
- **Tests** — `test_history_cache.py`: no-rescan on repeat call (scan call-counter), per-mutator invalidation for all seven write paths, condsug cache-hit identical dict, context-filter variance across context records, bulk invalidate-all

---

## 2026-08-07

### Time-proximity reminders for `due_time`

- **Independent `_reminder_loop`** — a new background thread fires a "Todo due soon" notification once when a todo's `due_time` is within `remind_before_minutes` of arriving. Runs on its own timer, decoupled from the due-today `notify_interval`, so a tight window can't slip past between two slow polls
- **Config** — `[todo] remind_before_minutes` (0 = disabled, the default; no thread started) and `[todo] reminder_check_interval` (default 2 min, clamped server-side to ≤ `remind_before_minutes`). Both editable in Settings → Todo; restart required, same as `notify_interval`
- **Scans all open todos with a `due_time`**, not just today's — a task due tomorrow at 00:10 is caught once inside the window. Already-past `due_time` and done tasks are skipped; fires once per `(line_no, due, due_time)` (in-memory dedup, same caveat as the due-today set), so editing `due_time` re-arms it
- **Web notification via SSE** — `_reminder_loop` now also broadcasts a `todo-reminder` SSE event (task dict `{line_no, description, priority, due, due_time, mins_until}`) so the browser shows a toast + "Todo due soon" Notification, alongside the OS toast and a `[reminder]` console trace. Live-only, deliberately not added to the `_pending_notifications` replay cache (avoids the hardcoded `todo-due` replay type and the housekeeping `clear()` race)
- **Startup note** — `_start_reminder_thread()` prints a note when `remind_before_minutes < notify_interval`, flagging the missed-window scenario that the independent loop is designed to fix
- **`_housekeeping_loop` untouched** — due-today behavior is exactly as before
- **Tests** — `test_reminder.py`: window firing, too-early/past/done/no-time skipped, tomorrow-caught, dedup-key on edited time, config clamping, thread-start gating, SSE `todo-reminder` payload shape

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
