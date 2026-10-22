# PTOS Spec: Live Widgets and a Customizable Home Page

Audit basis: `main` at `5f208d2`. Findings come from reading the code; nothing was run in a browser.

> **Superseded in part.** The home-page and editor sections — and Phase 4 (group/pivot/trend drill-down, calendar embed navigation, live embeds, README) — moved to `ptos-home-note-and-widget-editor-spec.md` (as E2, E3 and Part G, with `live = true` as the only opt-in and no global settings switch). The `[home].widgets` layout, `save_home_widgets`, `base_hash`, the `note` widget and that switch are dropped. This file remains for what stays: registry, batch resolve, saved todo views, `data-changed`, live `RecordTable`.

**Revision:** saved todos live in `queries.toml` as `["todo.NAME"]`; the home layout lives in `config.toml` under `[home].widgets` (no new `home.toml`, so the four-file rule holds); a `note` widget replaces the inline `markdown` text widget.

## 0. Decisions in one place

1. **Build the widget once, as a shared interactive component.** The home page, the pages, and markdown embeds all mount the same widget. Whether a markdown embed is interactive is then a switch, not a second implementation.
2. **Markdown previews stay read-only by default.** Interactive embeds are an opt-in (`live = true`).
3. **The home page is a saved layout of widgets**, stored in `config.toml` under `[home].widgets` (one inline entry per line, like `[favorites]`). There is **no new config file**: PTOS keeps its four TOML files (config, presets, queries, schema). The layout is edited visually and as text. It is **not** a markdown file, but each entry reuses the embed block keys so blocks stay interchangeable between notes and home. A `note` widget places an existing markdown note inside the layout for free-form text.
4. **Add a todo widget** with inline filters (project, context, priority, due or timeline), plus **saved todo views** as `["todo.NAME"]` sections in `queries.toml`, and move the todo filtering out of the web route into the service layer to make both possible.

### Where things live (four-file rule)

| Thing | File | Why |
|---|---|---|
| Saved todo views | `queries.toml`, `["todo.NAME"]` | same convention as `["board.NAME"]`, `["habit.NAME"]`, `["calendar.NAME"]`, `["due.NAME"]`, `["project.NAME"]`; embeds already resolve `name` through this file |
| Home layout (widget order, spans, `hide_on`) | `config.toml`, `[home].widgets` | a display preference, beside the existing `[home] quick_presets` and `thresholds`, `[favorites]` and `[dashboard]`; the favorites-style text writer preserves comments |
| Todo behavior settings | `config.toml`, `[todo]` | unchanged |
| Quick-add templates | `presets.toml` | unchanged |
| Record types and fields | `schema.toml` | unchanged |

Why not a separate `home.toml`: config writers are infrequent and user-initiated (user name, favorites, date format, currency, cycles, auth, settings page, CLI `--set-config`, migration), so a layout editor adds one more rare writer; the layout is the same kind of setting as the other `[home]` keys; and per-widget `hide_on` covers the phone-versus-desktop difference. A device-local layout would need a separate unsynced file, which is out of scope. If several customizable pages are ever wanted, generalize with `["page.NAME"]` sections in `queries.toml` (home as `page.home`).

---

## 1. Current state (verified)

- **Embeds:** a ```` ```ptos ```` block's TOML is posted to `POST /api/embed/resolve`; `svc.resolve_embed(spec)` (140 lines of if/elif per view) returns data; `widgets.js` paints it as static HTML (`renderResult`, `renderRecordsStatic`, `renderHabit`, `renderBoard`, `renderCalendar`, `renderDue`, `renderThresholdResult`, and the group/pivot/trend/chart renderers). `embeds.js` states the preview is intentionally read-only; all editing is in Blocks mode (`md_blocks.js`).
- **Embeds reference named items.** `name` must exist in `queries.toml` (query, metric, dashboard, threshold, board, habit, calendar, due, project). Recognized keys today: `view`, `name`, `time`, `from_date`, `to_date`, `limit`, `title`, `chart`. There is no inline-filter embed and no `todo` view.
- **Pages have richer, separate code.** `RecordTable` (514 lines; sort, bulk actions, delete, paging, export) is a drop-in component used by browse, home, queries, query builder and entity, but it locates its container by element id (`containerId`) and the embeds do not use it. Habit cells are toggled on the Habits page through `/api/habit/toggle`; thresholds on home are links to `/queries` via `query_url`; the Board page has its own drag-and-drop.
- **Todo:** `/todo` is a server-rendered page. Filtering (project with `-` exclusion, context, priority, search, `linked_to`, due bucket, `groupby=timeline`) is implemented **inside the `todo_page` route** (146 lines, nested `_filter_list`), not in the service (`get_todos(include_done)` has no filters; `get_todos_bucketed()` returns overdue, today, tomorrow, upcoming, someday). Actions are JSON endpoints (`/todo/complete`, `/todo/undo`, `/todo/edit`, `/todo/delete`, `/todo/bulk-edit`) that identify a task by `line_no`.
- **Home:** `home()` computes schema, presets, due data, dashboards, today's records, thresholds and frequent presets, and renders a fixed 507-line template of cards (Thresholds, Overdue Records, Todos, Journal, Capture, Quick Add, Quick Add multi, Today's Records) with page-specific scripts (`/api/capture`, `/api/preset_*`).
- **Live updates:** the SSE stream carries only `todo-due`, `todo-reminder` and `shutdown`. There is no "data changed" event.

## 2. Goals and non-goals

**Goals**
- One widget component per view type, usable on home, pages and in notes.
- Home widgets are live and configurable: sortable, editable records table; clickable thresholds; toggleable habits; actionable todo list.
- Home layout is customizable by the user, with a safe default and fallback.
- Widgets refresh when the underlying data changes.

**Non-goals (v1):** a new TOML file for home, drag-and-drop layout editing on phones, per-device layouts, user-written widget plugins, rebuilding the existing pages on top of widgets (do that later, after parity), interactive Board widget (see section 5).

---

## 3. The widget contract

### 3.1 Config format

A widget's config is the existing embed TOML body, extended:

| Key | Meaning |
|---|---|
| `view` | widget kind (existing kinds plus `todo`, `note`, `capture`, `quick_add`, `quick_add_multi`, `journal`) |
| `name` | named item in `queries.toml` (kinds that use one) |
| `title`, `time`, `from_date`, `to_date`, `limit`, `chart` | unchanged |
| `path` | `note` widget: relative path of the note to show |
| `live` | markdown embeds only: `true` mounts the interactive version |
| `span`, `hide_on` | home layout only: column span (1 or 2), `hide_on = ["phone"]` |

Each kind whitelists its own keys; unknown keys return a clear error (today they are ignored).

### 3.2 Server

- Replace the `resolve_embed` if/elif chain with a registry in a new `ptos_widgets.py`: `register(kind, resolve=fn, keys=[...], actions=[...])`. `resolve_embed(spec)` becomes a dispatcher; behavior for existing kinds is unchanged.
- Each resolver returns `{kind, title, link, ...data}` as today.
- Add `POST /api/widgets/resolve` taking `[{id, body}, ...]` and returning `[{id, ok, data|error}, ...]`. Errors are per widget. Resolve in one request so a home page with many widgets makes one call, not one per widget. Keep `/api/embed/resolve` unchanged.
- Row limits: default `limit` 100 and maximum 500 for list kinds.

### 3.3 Client

New `web_static/js/widget_host.js`, loaded after `widgets.js`:

```js
PtosWidgets.register("todo", {
  render(el, data, ctx) { /* static markup */ },
  mount(el, data, ctx)  { /* wire events; return {refresh(), destroy()} */ }
});
PtosWidgets.mount(el, spec, {host: "home" | "note" | "page", interactive: true});
```

- `ctx` provides `refresh()`, `notifyChange(scope)`, `host`, `interactive`, and the home time scope.
- Static `render` stays the path for preview-only (no behavior change). `mount` is used when `interactive` is true.
- **Instance-scoped DOM:** widgets use their own element, not global ids. `RecordTable` needs a small change so it can take an element (`container: el`) and generate unique internal ids; its current `containerId` option keeps working.
- Each widget shows loading, empty and error states, an "Open →" link to the owning page, and a refresh control.

### 3.4 Refresh events

- Add an SSE event `data-changed` with `{scope: "records"|"todo"|"notes"|"config", types?: [...]}`. Emit it from the write paths (record add, edit and delete, todo operations, note saves, config saves) and from the existing external-change watcher (so Syncthing updates refresh widgets).
- Widgets subscribe by scope, debounce 500 ms, and refresh only the affected widgets. Also refresh on `visibilitychange` (tab becomes visible) and on `pageshow` from the back/forward cache. No polling.
- Prerequisite: the SSE stream must not leak threads (see section 8, Phase 0). The client already closes the stream on `pagehide`; confirm the server heartbeat and cap landed.

### 3.5 Safety

- Widgets perform writes only through existing JSON endpoints (Origin guard and JSON-only already apply). A widget never writes a note.
- Interacting with a widget in a note must not mark the note dirty or trigger autosave.
- The `note` widget validates `path` with the same `_safe_path` as the notes routes, renders with the same sanitizing renderer as notes (confirm it escapes raw HTML before shipping), and is **home-only**: a `note` widget inside a note is rejected, so a note can never embed itself or loop.

---

## 4. Todo widget

### 4.1 Service refactor (first step)

Move the filtering and bucketing out of `todo_page` into `svc.query_todos(filters)` returning the five buckets plus counts. Filters:

| Filter | Behavior |
|---|---|
| `project` | one or more; a leading `-` excludes (existing behavior) |
| `context` | one or more |
| `priority` | letter(s), case-insensitive |
| `due` | `overdue`, `today`, `tomorrow`, `upcoming`, `someday`, `none`, plus `week` (next 7 days) |
| `search`, `linked_to` | as today |
| `include_done`, `hide_routines` | as today (`hide_routines` default from config) |
| `groupby` | `timeline` (default), `priority`, `project`, `context`, `none` |
| `sort`, `limit` | defaults: timeline order, 20 |

`todo_page` calls `query_todos` and renders exactly what it renders now. **A golden test** records the current `/todo` output for a fixed set of filter combinations before the refactor and asserts it is unchanged afterwards.

### 4.2 Config

Inline, in an embed block or a home widget entry:

```ptos
view = "todo"
title = "Work, this week"
project = "work"
context = "office"
priority = "A"
due = "week"
groupby = "timeline"
limit = 10
```

**Saved todo views** live in `queries.toml` as `["todo.NAME"]`, matching the other named views, and are referenced by `name`:

```toml
["todo.work_week"]
title = "Work, this week"
project = "work"
context = "office"
priority = "A"
due = "week"
groupby = "timeline"
limit = 10
```

```ptos
view = "todo"
name = "work_week"
limit = 5          # inline keys override the saved view
```

Rules:
- Allowed keys are exactly the filters in 4.1 plus `title`; unknown keys are an error.
- If a todo view shares a name with another named item, the resolver's existing ambiguity rule applies: set `view` explicitly (inline).
- `config.toml`'s `[todo]` section keeps behavior settings only (notify intervals, `hide_routines`, archive months); filters never go there.
- The UI writes `queries.toml` through `_write_queries`, which rewrites the file with `tomli_w`, so comments in `queries.toml` do not survive UI saves (same as every other saved view today). v1 supports hand-editing `["todo.NAME"]`; the Query Builder gets a Todo tab later.
- Add `["todo.NAME"]` to lint, `--doctor`, `get_*_names` helpers, and the Query Builder's name list so the new sections appear everywhere the others do.

### 4.3 Interactions

- Checkbox completes a task (`/todo/complete`), with an undo toast (`/todo/undo`).
- Tapping a project or context chip opens `/todo` with that filter.
- Optional `add = true` shows a one-line add field that pre-fills the widget's project, context and priority.
- Inline due and priority edits reuse the popups later; not in v1.

### 4.4 Task identity

The endpoints use `line_no`, which can shift when another view, the todo page or a Syncthing update changes the file. A widget sends `line_no` plus the task's raw text (`expect`), and the server verifies the line matches before acting, returning a "changed, refresh" error otherwise. First check what `complete_todo_by_line` already verifies (I did not); apply the same check to undo, edit and delete.

---

## 5. Widget catalog

| Kind | Static (today) | Interactive in v1 | Later |
|---|---|---|---|
| `records` | `renderRecordsStatic` | `RecordTable`: sort, paging, bulk, edit, delete, export | inline edit |
| `threshold` | `renderThresholdResult` | clickable: opens the query or a browse filter (as home does now); progress and direction shown | quick-add record that moves the threshold |
| `habit` | `renderHabit` | cells toggle via `/api/habit/toggle`; month navigation | streak details |
| `todo` | new | complete, undo, filter chips, optional add | inline edit |
| `due` | `renderDue` | complete or open the record; follows the config-driven window | snooze |
| `group`, `pivot`, `trend`, `metric`, `dashboard` | existing renderers and charts | chart/table toggle; click a bar or row to open matching records | |
| `calendar` | `renderCalendar` | month navigation; click a day to open its records | add on a day |
| `project` | existing | links to project page, notes, tasks | |
| `journal` | none | today's entry preview with Open/Edit | |
| `capture`, `quick_add`, `quick_add_multi` | page scripts on home | same behavior, moved into widget partials | |
| `note` | none | renders a note (read-only) with an Open/Edit link; embeds inside that note render as they do in the note preview | live embeds inside it, once Phase 4 ships |
| `board` | `renderBoard` | **view-only in v1**; the mobile drag-and-drop attempt was reverted, so interactive boards wait for a touch-safe design | |

---

## 6. Home page

### 6.1 Storage and format

The layout is the `widgets` key of the existing `[home]` table in `config.toml`: an array of inline tables, **one entry per line**, exactly like `[favorites] items`. It uses the section 3.1 keys:

```toml
[home]
quick_presets = 10
thresholds = ["default"]        # existing key, kept
widgets = [
  { view = "capture", span = 2 },
  { view = "todo", name = "work_week" },
  { view = "todo", title = "Today", due = "today", priority = "A" },
  { view = "threshold", name = "default" },
  { view = "note", path = "Home/welcome.md" },
]
```

- TOML inline tables must stay on one line, so each entry is a short single-line table; long text belongs in a note, shown by a `note` widget, not in `config.toml`.
- Every entry is also valid as a ```` ```ptos ```` embed body (minus `span`, `hide_on`, `path`), so a block can be copied between a note and the home layout.
- `time = "@home"` means "follow the home page's time picker", so the existing database selector and time picker keep working as header controls.
- The existing `[home] quick_presets` and `thresholds` keys keep their meaning. The default layout's threshold widget reads `thresholds`, so existing setups do not change.

**Writer:** `save_home_widgets(entries)` reuses the favorites approach:
- Edit `config.toml` as text, replacing only the `widgets = [...]` value inside `[home]` (create the key or the `[home]` table if missing); leave every other byte, including comments and the multi-line `thresholds`, untouched.
- Match the `[home]` header the way the hardened favorites writer does (trailing comment, inner spaces, quoted, CRLF).
- Parse the result with `tomllib` before writing and confirm `home.widgets` equals the saved list; on any mismatch raise and leave the file untouched.
- Hold the config lock for the whole read-modify-write and write atomically; invalidate caches once.
- Maximum 50 entries.

**Loader:** `get_home_layout()` reads `[home].widgets` and validates **each entry on its own**:
- must be a table with a known `view`; only the keys allowed for that kind; `span` 1 or 2; `hide_on` values from `phone`, `desktop`; `path` passes `_safe_path`.
- Invalid entries are skipped and returned in a `warnings` list that the page shows as a banner; `--doctor` reports the same list. A bad entry can never stop `config.toml` from loading (a wrong value is not a TOML error, and a TOML error already shows the default layout, see 6.2).

### 6.2 Default and fallback

- If `[home].widgets` is absent or empty, use a **built-in default layout that reproduces today's home** (Thresholds, Overdue Records, Todos, Journal, Capture, Quick Add, Quick Add multi, Today's Records). "Reset to default" removes the `widgets` key (nothing else in `config.toml` changes).
- A widget that fails to resolve shows an error card and does not affect the others.
- If `config.toml` itself fails to parse, the app already reports the config error; home shows the built-in default layout with that banner. Home never renders blank.

### 6.3 Editing

- An **Edit home** screen (settings, also reachable from the home header): list of widgets with add (kind picker with defaults), up/down reorder, span, hide-on-phone toggle, remove, and a per-widget edit form (the same form Blocks mode uses for ✎). Up/down buttons first; drag later.
- An **Edit as text** view showing the `widgets` entries (one per line) with validation before saving.
- **Conflict check:** the editor sends `base_hash`, a hash of the layout it loaded (canonical JSON of the validated entries). Under the config lock the server compares it with the current layout and returns 409 with the current hash on mismatch (same banner pattern as notes: reload, save mine as text, overwrite), so two devices do not overwrite each other silently.

### 6.4 Performance

- One batch resolve call for the whole layout; the server computes widgets in one request.
- Widgets below the fold load lazily (`IntersectionObserver`).
- Measure first paint and total requests on the phone before and after; the target is not slower than today's home on the same data.
- `home()` currently runs many service calls itself; the batch path replaces that work, so the route shrinks.

### 6.5 Home-only widgets (actions, not queries)

`capture`, `quick_add` and `quick_add_multi` wrap the existing `/api/capture` and `/api/preset_*` flows. Move their markup and script from `home.html` into partials and a small module so they mount the same way as the others.

---

## 7. Markdown embeds: opt-in live mode

- Default stays read-only; nothing about existing notes changes.
- `live = true` in a block mounts the interactive widget in the preview. A global setting "Interactive embeds in preview" (off by default) enables it for all blocks.
- On phones, live embeds should require the explicit `live = true` so accidental taps in a document do not change data.
- Blocks mode keeps the ✎ editor; extend its form for the `todo` kind and the new keys. Update the README embed section.

---

## 8. Phases, tests and acceptance

### Phase 0: prerequisites (about 2 days)
- Confirm SSE heartbeat and stream cap are in (the client `pagehide` close already exists); if not, do them (see the pre-modularization spec, item A4).
- `ptos_widgets.py` registry and refactor of `resolve_embed`; all existing embed tests pass unchanged.
- `POST /api/widgets/resolve` batch endpoint.
- `RecordTable` accepts an element and uses instance-scoped ids; two instances on one page work.
- Extract `svc.query_todos` with the golden test for `/todo`.

### Phase 1: widget layer and first interactive kinds (4 to 6 days)
- `widget_host.js` plus `records`, `threshold`, `habit`, `todo`, `due` interactive widgets.
- **Parity tests:** a widget with a given config returns the same data as the corresponding page for the same filters; actions go through the existing endpoints.
- Todo widget with stale-`line_no` protection (section 4.4) and saved views via `["todo.NAME"]` in `queries.toml` (section 4.2), including lint, `--doctor` and Query Builder name-list support.
- Acceptance: each widget works on a throwaway test page with two instances at once, on a 360 px viewport.

### Phase 2: `data-changed` and refresh (1 to 2 days)
- Emit from write paths and the external-change watcher; widgets refresh by scope with a debounce.
- Acceptance: completing a todo in one widget updates a second todo widget and the todo page; a Syncthing-style file change refreshes affected widgets.

### Phase 3: customizable home (3 to 4 days)
- Default layout parity, `get_home_layout()` with per-entry validation and warnings, `save_home_widgets()` text writer for `[home].widgets` (section 6.1), `base_hash` conflict check, editor UI, text editor, batch resolve and lazy loading, and the `note` widget.
- Acceptance: with no `[home].widgets` the page matches today's content; adding, reordering and removing widgets persists; a broken widget entry is skipped with a banner and a broken `config.toml` falls back to the default layout, so the page is never blank; editing the layout leaves comments and the other `[home]` keys byte-identical.

### Phase 4: remaining kinds and live embeds (3 days)
- `group`/`pivot`/`trend` drill-down, `calendar`, `journal`, `note`, `project`; `live = true` and the settings switch; README and CHANGELOG.

### Test list (across phases)
- Registry: every kind resolves; unknown keys rejected; per-kind whitelist.
- Batch endpoint: mixed good and bad widgets return per-item results; limit caps enforced.
- Todo: every filter combination, including `-project` exclusion and `due=week`, matches the golden `/todo` output; widget actions reject a stale `expect`.
- Home loader: missing or empty `widgets` uses the default; each invalid entry (unknown view, bad key, bad `span`, traversal `path`) is skipped with a warning while valid entries still render; more than 50 entries rejected; `hide_on`; `@home` time follows the picker; layout save with a stale `base_hash` returns 409; existing `quick_presets` and `thresholds` still work.
- Home writer: preserves comments and the multi-line `thresholds`; creates `widgets` or `[home]` when missing; handles `[home]` header variants and CRLF; output always parses and round-trips; failure leaves the file unchanged; no write when the layout is unchanged.
- Saved todos: `["todo.NAME"]` resolves by `name`; inline keys override; unknown keys error; a name shared with another section requires an explicit `view`; the sections appear in lint, `--doctor` and the Query Builder name list.
- `note` widget: `path` traversal rejected; a `note` widget inside a note is rejected; raw HTML in the note is escaped.
- Events: write paths emit `data-changed` with the right scope; debounced refresh.
- Notes: an interactive embed's action does not change the note's dirty state; read-only preview unchanged.
- Static guards: no widget script uses global element ids; the `note` widget escapes HTML.

---

## 9. Risks

- **Drift between pages and widgets** while both exist. Mitigate with parity tests, and plan to rebuild the Habits, Thresholds and Todo pages as hosts of these widgets after parity is proven (removes the duplicate code).
- **Phone performance** with many widgets: batch resolve, lazy loading, debounce, and the SSE fix. Measure before and after.
- **Stale `line_no`** in todo actions (section 4.4).
- **Accidental changes** from interactive embeds in notes: off by default, explicit `live = true`.
- **Scope creep** in the editor UI: ship up/down controls and a text editor before any drag-and-drop.

## 10. Not verified

Whether `complete_todo_by_line` already checks the task text; whether every `queries.toml` writer drops comments (I only read `_write_queries`, which uses `tomli_w`); how the Query Builder lists named sections (the new `["todo.NAME"]` kind must be added wherever the others are); whether the markdown renderer escapes raw HTML (needed for the `note` widget); whether `RecordTable`'s internal ids collide across instances (the container id is a parameter, but I did not read every inner id); the current server-side SSE heartbeat state; the exact page-side behavior of habits and thresholds beyond the toggle endpoint and the `query_url` links; any behavior on a real phone.
