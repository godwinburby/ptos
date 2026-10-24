# PTOS Spec: Home as a Note, and the Widget Gallery and Form Editor

Audit basis: `main` after commit `ba38815` (home quick-add fix, inline calculator, Id & links collapse), 3,438 tests passing. Findings come from reading the code and running it on Linux; no browser was used.

**Revision (text and tokens):** adds a Text category to the gallery, a formatting toolbar for text blocks (C5, C6), and inline `{{tokens}}` in markdown for the dynamic greeting, name and date (Part F). There is no greeting widget.

**Revision (folded Phase 4):** the old spec's Phase-4 leftovers — group/pivot/trend drill-down, calendar embed navigation, opt-in live embeds, and the README update — are folded in here (E2, E3, Part G) with a simpler rule: live embeds are controlled by the block's `live = true` only; there is **no global settings switch** (the old `ptos-live-widgets-and-home-spec.md` §7 switch, and its phone special case, are dropped — explicit `live = true` is the only opt-in on every device).

**Relationship to the earlier spec.** This replaces the home-page and editor parts of `ptos-live-widgets-and-home-spec.md` (its `[home].widgets` layout, `save_home_widgets`, `base_hash` and `note` widget are dropped). Everything else there stays: the widget registry, batch resolve, the todo widget, saved todo views (`["todo.NAME"]`), `data-changed`, and live `RecordTable`. Its Phase 4 leftovers (group/pivot/trend drill-down, calendar embed navigation, live embeds, README) are folded into this spec as E2, E3 and Part G; its global interactivity switch stays dropped.

---

## 0. Decisions

1. **The home page is a normal markdown note** (`Home.md`) rendered at `/` with live widgets. Storage, sync, backups, conflict handling and the block-list editing already exist for notes.
2. **Widget configuration is form-based, never hand-written TOML.** One catalog drives one picker (a gallery) and one form, used by home edit mode, Blocks mode and the `/` slash menu. "Edit as text" remains as an advanced toggle only.
3. **Home has an explicit edit mode.** The normal home view is interactive and never edits the layout.
4. **Before any of this, fix three prerequisites** (Part A): note saves do not emit `data-changed`, todo filters accept bad values silently, and markdown rendering depends on a CDN and has no sanitizer.
5. **Text is edited with the same UI, not raw markdown only.** The gallery gets a **Text** category (headings, lists, checklist, quote, callout, divider, table) and text blocks get a **formatting toolbar**. Markdown source stays the storage format; there is no WYSIWYG editor.
6. **Dynamic text uses inline tokens, not a widget.** `{{greeting}}`, `{{name}}`, `{{date}}` and a few more are substituted when markdown is rendered (Part F). The home page's "Good morning, {name}" becomes the first line of the default `Home.md`.
7. **Live embeds are block-flag only.** `live = true` in a ```` ```ptos ```` block opts that block into interactive mounting in the note preview; there is **no** global "Interactive embeds in preview" setting (supersedes the old spec §7). With no switch, the old phone special case disappears too: explicit `live = true` is the only opt-in on every device.
8. **Drill-down navigates to Browse.** A group/pivot/trend row or chart element links to `/browse` carrying the query's `where_expr` combined with the clicked value (or the period's date range), via a new `?expr=` deep-link that seeds the expression box and runs on load.

---

## 1. Current state (verified)

- **Widget kinds:** 16 registered (`dashboard`, `metric`, `threshold`, `board`, `habit`, `calendar`, `due`, `project`, `todo`, `query`, `capture`, `journal`, `quick_add`, `quick_add_multi`, `records`, `todo_summary`). Nine point at a saved named item (`needs_name`). The rest take parameters or none: `todo` (11 keys), `records` (`where`, `chart`), and `query` (`chart`). Dashboard widgets take a saved dashboard name; the page time picker supplies the shared time window.
- **Picker today:** `GET /api/embed/candidates` returns named items only, in nine groups (with the starter data: 17 queries, 6 metrics, 2 dashboards, 1 threshold, 1 board, 3 habits, 1 calendar, 1 due, 1 project, plus an empty "Todo views"). `todo`, `records`, `capture`, `journal`, `quick_add`, `quick_add_multi` and `todo_summary` cannot be picked at all.
- **Blocks mode** (`md_blocks.js`, 536 lines): the note as a vertical list of top-level blocks (markdown element or one ```` ```ptos ```` widget). Controls: `+` add (slash picker), `?` change, ✎ edit, delete, drag reorder. The textarea stays the source of truth; serialization joins blocks with a blank line. **The ✎ edit for a widget opens a raw textarea of its TOML**, with a one-line hint (`view · name · time · from_date · to_date · limit · title`).
- **Slash picker core** (`slash_embed.js`, 546 lines) is shared by the `/` menu, the "Insert view" button and Blocks mode; it adds a time-window step after picking an item.
- **Home today:** `home()` serializes eight specs into `#home-widget-specs` as `[{section, kind, body}]`, in four fixed sections (`overview`, `attention`, `quickadd`, `today`), and `home_widgets.js` resolves them in one batch POST. Default bodies:

  | Section | Kind | Body |
  |---|---|---|
  | overview | dashboard | `name = "default"` |
  | overview | threshold | `title = "Thresholds"`, `time = "tm"` |
  | attention | due | `name = "default"`, `title = "Overdue Records"`, `limit = 5` |
  | attention | todo_summary | `title = "Todos"` |
  | attention | journal | `title = "Journal"` |
  | quickadd | capture | `title = "Capture"` |
  | quickadd | quick_add | `title = "Quick Add"` |
  | today | records | `limit = 8`, `where = []`, `time = "td"`, `title = "Today's Records"` |

  `home()` reads `custom_time`, `dashboard`, `due`, `from_date`, `time`, `to_date`; a `time-select` and a date-time picker drive the page. Measured on a 12-year dataset: page plus batch about 83 ms cold, 15 ms warm.
- **Notes are rendered client-side** with `marked` 9.1.6 loaded from `cdnjs.cloudflare.com` in `_markdown_editor.html`. I found no sanitizer (no DOMPurify, no HTML escaping option). There is no server-rendered read view; the only note route is `/notes/edit/<path>`.
- **`[home]` in `config.toml`** already holds `quick_presets` and `thresholds`.
- **Greeting today:** `home.html` shows a fixed title `Good {{ greeting }}, {{ username }}` outside the widgets. `_greeting()` picks morning (before 12), afternoon (before 17) or evening using the **server's** clock, so a server in another timezone shows the wrong greeting. The name is `[user] name` (default `User`). A note is static text, so this title has no equivalent in the note model yet.
- **Text editing today:** a text block's ✎ opens a raw markdown textarea. The only formatting help is the `/` Format group in `slash_embed.js` (Heading 1, Heading 2, Bulleted list, Numbered list, Quote, Divider, Table, each with a `seed`). There is no toolbar in Blocks mode or in the full note editor.
- **Reusable functions:** `embedRegions(src)`, `embedFetch`, `embedRenderBody` (`embeds.js`), `mountBatch(items, opts)` (`widget_host.js`), `blockParse` / `blockSerialize` (`md_blocks.js`).
- **Interactivity gap:** `widget_host.js` registers interactive mounts for `todo`, `records` and `habit`; `threshold` and `due` are not yet interactive.
- **Drill-down data is display-only today:** `where_expr` is attached to group, pivot, trend and records payloads (`ptos_service.py` `_run_query_spec`) and rendered as a badge in `exprBadge` (`widgets.js`); no row, cell or chart element is a link. Two payload gaps: group rows carry only a joined `key` label (multi-field groups are two-space-joined — ambiguous to split client-side), and trend rows drop the per-period `start`/`end` bounds that a range drill needs.
- **Browse has no expression deep-link:** `browse_get` reads only `time`/`custom_time`/`from_date`/`to_date`; the expression reaches `/browse/run` as a POST body, so a drill-down URL cannot seed the page today.
- **Calendar embeds have no navigation:** `renderCalendar` renders one fixed month, no prev/next controls.
- **The note preview cannot mount interactive widgets:** `_markdown_editor.html` loads `widgets.js` + `embeds.js` but not `widget_host.js`, and `mountEmbeds` paints every embed statically.

---

## 2. Goals and non-goals

**Goals**
- A user can build and rearrange their home page entirely through the UI, including every widget's options.
- A task-based gallery with search, descriptions, starter widgets and recents replaces the flat list.
- Home works offline (no CDN) and renders user text safely.
- Home never renders blank and survives renaming or deleting the note.
- Text can be created and formatted with taps (gallery and toolbar), without knowing markdown symbols.
- The page can greet the user dynamically ("Good morning, Godwin") from plain markdown, using the device's own clock.

**Non-goals (v1):** a WYSIWYG editor, data-driven tokens such as task counts (see Part F), per-device layouts (use `hide_on`), resizable drag grids, tabs or multiple home screens, widget plugins, public sharing, and a global interactive-embeds switch (block-level `live = true` only).

---

# Part A: Prerequisites (do first)

## A1. Note saves must emit `data-changed`

**Problem (reproduced):** `svc_save_file` emits `scope_for_data_path(rel_path)`, but that function looks for a `records`, `todo`, `notes` or `config` folder in the path, and note saves pass notes-relative paths (`a.md`, `Clients/x.md`). Result: a normal note save emits nothing; a note in a folder named `config` would map to the wrong scope. Rename, delete and create already emit `notes` directly. Home is now a note, so refresh on save matters.

**Change:**
- Emit `notes` directly in `svc_save_file` (as rename and delete do).
- Also emit in `svc_ensure_note_id` (it writes a note) and `restore_config` (`config`). Journal silence stays deliberate (`scope_for_data_path` returns `None` for journal paths).
- Keep `scope_for_data_path` for data-folder paths only; document the contract.

**Tests:** top-level note save, nested note save, a note inside folders named `config` and `todo`, save with a stale revision (no event), `ensure_note_id`, `restore_config`.

## A2. Todo filter correctness

**Problems (reproduced):** `context = "office"` matches nothing (needs `@office`), while `project` accepts `work` and `+work`; `due = "nextcentury"` returns every todo (unfiltered); `priority = "zz"` returns none. The `/todo` page behaves the same way, since both share `query_todos`.

**Change (in `query_todos`, so widget and page agree):**
- Normalize `project` (`+` optional) and `context` (`@` optional), case-insensitive, on input.
- Validate `due` against `overdue`, `today`, `tomorrow`, `upcoming`, `someday`, `none`, `week` and `priority` as a single letter A–Z (or a list); invalid values raise a clear field error ("`due` must be one of …") instead of being ignored.
- `groupby` keeps its existing validation.

**Tests:** bare and prefixed forms return the same rows; every invalid value errors with the field name; the `/todo` golden output is unchanged for valid inputs.

## A3. Vendor and sanitize markdown rendering

**Problem:** `marked` loads from a CDN, so the notes and (soon) the home page break without internet access, which matters on a phone server reached over Tailscale or a LAN. Rendered note HTML is not sanitized, so script or event-handler HTML in a note would run.

**Change:**
- Vendor `marked` (pinned 9.1.6) and DOMPurify (pinned) under `web_static/vendor/` with a version file and license notes; load them locally.
- One shared `renderMarkdown(text)` helper (marked, then DOMPurify, then the token pass from Part F) used by the editor preview, Blocks mode and home. Allowed: standard markdown output plus `details`/`summary` and `br`; blocked: `script`, `style`, event-handler attributes, `javascript:` and `data:` URLs in links.
- Keep `breaks: true` and `gfm: true`.

**Tests:** static check that no template references a CDN URL; sanitizer cases (`<script>`, `<img onerror>`, `[x](javascript:…)`, `<iframe>`); normal markdown (tables, task lists, fenced code) unchanged.

---

# Part B: Widget catalog (server)

## B1. Registry metadata

Extend each `ptos_widgets.register(...)` entry with:

| Field | Meaning |
|---|---|
| `label`, `description`, `icon` | gallery card text (one line of what it shows) |
| `category` | one of the six categories in B2 |
| `named` | if true, the second step lists saved items of this kind (from the existing candidate lists) |
| `fields[]` | form fields (below) |
| `starters[]` | ready-made configurations (B4) |
| `interactive_default` | true on home for kinds with interactive mounts |

**Field schema:** `key`, `label`, `type`, `help`, `default`, `required`, `advanced`, `show_if`, and either static `options` or `options_from`. Types: `text`, `number`, `bool`, `select`, `multiselect`, `chips`, `time_window`, `saved_item` (a named item of a given kind), `record_type`, `field_filter` (the `where` builder over schema fields). Option sources: `todo.projects`, `todo.contexts`, `todo.priorities`, `schema.types`, `schema.fields:<type>`, `saved.<kind>`.

Every existing key of every kind gets metadata (for example `todo`: `project` chips, `context` chips, `priority` select, `due` select, `groupby` select, `limit` number, `search` text, and under advanced: `include_done`, `hide_routines`, `sort`, `linked_to`, `add`). The registry's key whitelist and the field list must agree; a test enforces it.

## B2. Categories

| Category | Kinds |
|---|---|
| Tasks and reminders | `todo`, `todo_summary`, `due` |
| Tables and records | `records`, `query` |
| Numbers and charts | `metric`, `dashboard`, `query` shown as chart |
| Goals and habits | `threshold`, `habit`, `calendar` |
| Capture | `capture`, `quick_add`, `quick_add_multi`, `journal` |
| Projects | `project`, `board` |
| Text | not widgets: block seeds from `text_blocks.js` (C5) |

The Text category lists **block seeds** (markdown), not registry kinds, so it needs no server endpoint; the gallery merges it with the catalog response.

**Source then view (UI grouping, no engine change):** for data widgets the gallery asks *what* first (a saved query, records of a type, a metric, todos) and then *show as* (Table, or a chart type compatible with the source's kind: bar or horizontal bar for a group, line or bar for a trend, stacked or bar for a pivot). "Show as" maps to the existing `chart` key; users do not need to know `query`, `group`, `pivot` and `trend` are separate things.

## B3. Endpoints

- `GET /api/widgets/catalog` returns `{categories, kinds (label, description, icon, category, named, fields, interactive_default), starters}`. Option sources are resolved lazily:
- `GET /api/widgets/options?source=<source>` returns the values (for example the projects found in `todo.txt`, the record types in the schema, saved items of a kind).
- Existing `/api/embed/candidates` and `/api/embed/resolve` keep working unchanged.
- `POST /api/widgets/validate` (or reuse resolve with `validate_only`) returns field-level errors `[{field, message}]` so the form shows them inline. The same validation backs the resolver, so form and render cannot disagree.

## B4. Starter widgets

Defined next to each kind, each with a label, description and a full body. Initial set:

| Starter | Body (summary) |
|---|---|
| Today's tasks | `view = "todo"`, `due = "today"` |
| Overdue tasks | `view = "todo"`, `due = "overdue"` |
| Due this week | `view = "todo"`, `due = "week"`, `groupby = "timeline"` |
| Top priority | `view = "todo"`, `priority = "A"` |
| Tasks by project | `view = "todo"`, `groupby = "project"` |
| Today's records | `view = "records"`, `time = "td"`, `limit = 8` |
| This month's records | `view = "records"`, `time = "tm"`, `limit = 10` |
| Thresholds | `view = "threshold"`, `time = "tm"` |
| Overdue records | `view = "due"`, `name = "default"`, `limit = 5` (when a `default` due view exists) |
| Quick capture / Quick add / Journal / Todo summary | as the default home |

Starters that need a named item the user does not have are hidden. A test resolves every starter against the starter data.

---

# Part C: Gallery and form (client)

## C1. `widget_picker.js` (the gallery)

- A search-first sheet: a bottom sheet on phones (about 85% height, 44 px targets), a popover on desktop.
- Sections: **Starters** (top), then the six categories, then **Recent** (per device, `localStorage`, with try/catch). Each card shows an icon, the label and the one-line description.
- Typing filters across labels, descriptions and aliases (`todo`, `tasks`, `chart`, `habit`). Results are grouped by category; no flat scrolling list.
- Named kinds open a second searchable step listing saved items (reusing the candidate data).
- The Format group (headings, lists, tables) stays in the `/` slash menu only; the gallery is for widgets.

## C2. `widget_form.js` (the configuration sheet)

- Rendered from the catalog's field metadata. A **live preview** sits at the top and refreshes about 400 ms after each change (a single-item resolve).
- Basic fields first; the rest under "More options" (advanced). Short help line under each field; a one-line "what this shows" at the top.
- Controls use real data: chips for projects, contexts and priorities; a record-type dropdown from the schema; field filters built from that type's fields; saved items as a dropdown; **time windows as labelled choices** ("Today", "This month", "Last 30 days", "Custom range") using the existing period labels, plus "Follow the home time" on home (D4).
- Inline validation from `/api/widgets/validate`; Save is disabled while errors remain.
- **Edit as text** toggle shows the generated TOML; switching back re-parses it. Unknown keys and the order of existing keys are preserved on save (the form changes only the fields it knows), so hand-edited blocks survive.
- Output is the canonical TOML body (stable key order, readable defaults).

## C3. Integration points

1. `slash_embed.js` / `openSlashPicker`: widget picking delegates to the gallery (keeps the Format group and named items).
2. `md_blocks.js` `_edit(i)` for widget blocks opens the form instead of the raw textarea (with the text toggle); the `?` change flow opens the gallery in "change widget" mode and keeps compatible field values.
3. Home edit mode (D5).

## C4. Tests

- Catalog: every kind has metadata; field keys equal the registry whitelist; every `options_from` source resolves; starters resolve; the category map covers all 16 kinds.
- Form round trip: body → form → body preserves unknown keys and comments-free order; invalid values yield field errors; required fields enforced.
- Static checks: the picker and form modules exist and are loaded where `slash_embed.js` is; the Blocks ✎ handler for widgets opens the form.
- Mobile layout checks as a manual list (360 px and 412 px): sheet height, tap targets, keyboard, focus return.

## C5. Text category and shared text-block definitions

A single client-side definition list, `web_static/js/text_blocks.js`, is the source for both the gallery's **Text** category and the `/` slash menu's Format group (replacing the duplicate `_FORMAT_GROUP` in `slash_embed.js`). Each entry: `id`, `label`, `aliases`, `description`, `icon`, `seed` (markdown text), and a caret position inside the seed.

| Entry | Seed |
|---|---|
| Heading 1, 2, 3 | `# `, `## `, `### ` |
| Text | empty paragraph |
| Bulleted list | `- ` |
| Numbered list | `1. ` |
| Checklist | `- [ ] ` |
| Quote | `> ` |
| Callout | `> **Note**` plus a second `> ` line |
| Divider | `---` |
| Table | the existing table seed |
| Code block | a fenced block |
| Greeting line | `# {{greeting}}, {{name}}` (Part F) |
| Today's date | `{{date}}` |
| Your name | `{{name}}` |

- In the gallery these appear as cards with a one-line description, searchable like widgets ("heading", "todo list", "date").
- Picking one inserts the seed as a new text block in edit state with the caret in place.
- The slash menu keeps a compact version of the same list, now including Heading 3, Checklist, Callout, Code block and the token entries.

## C6. Text-block toolbar

A small component, `web_static/js/md_toolbar.js`, `PtosToolbar.attach(textarea, options)`, shown whenever a text block or the full note editor is being edited.

**Actions:** Bold, Italic, Link, Heading (H1, H2, H3 menu), Bulleted list, Numbered list, Checklist, Quote, Code, Insert token (menu: Greeting, Name, Date, Weekday, Time), and a Help link to a short markdown cheat sheet. Undo and redo use the textarea's native history.

**Behavior** (implemented as pure functions on `(value, selectionStart, selectionEnd)` so they can be tested without a browser):
- `wrapSelection` toggles `**`, `*` and `` ` `` around the selection; with no selection it inserts the markers and places the caret between them.
- `toggleLinePrefix` adds or removes `# `, `- `, `1. `, `- [ ] ` and `> ` on every selected line; switching between list types replaces the old prefix; numbered lists renumber.
- `insertLink` asks for the URL (and text when nothing is selected) and accepts only `http`, `https`, `mailto` and internal paths; it rejects `javascript:` and `data:`.
- `continueList` on Enter continues a bullet, number or checklist item and ends the list when the item is empty; Tab and Shift+Tab indent and outdent list lines.
- Shortcuts: Ctrl/Cmd+B, I and K.

**Placement and mobile:** a compact single-row bar above the textarea, horizontally scrollable with 44 px targets; on phones it is pinned above the on-screen keyboard (positioned with `visualViewport`). Used in: Blocks mode text blocks, home edit mode (D5), and the full note editor at `/notes/edit` (which has no formatting help today). Under the textarea, a rendered preview shows tokens substituted.

**Not included:** WYSIWYG editing, drag-selecting formatted text, image upload, or custom markdown extensions.

**Tests (C5 and C6)**
- `text_blocks.js` is the only definition list: static check that `slash_embed.js` and the picker read from it and no second list exists.
- Pure-function tests (run with `node --test` when Node is available, skipped otherwise): wrap and unwrap with and without selection; line-prefix toggling across several lines, mixed list types and renumbering; link rules (accept and reject schemes); list continuation, empty-item exit, indent and outdent; Unicode and emoji selections; CRLF input.
- Static checks: the toolbar module is loaded by the note editor and Blocks mode; buttons have labels and `aria-label`s.
- Manual list at 360 px and 412 px: keyboard overlap, pinned bar, targets, selection handles.

---

# Part D: Home as a note

## D1. Storage and setting

- The home page is a note, `Home.md`, at the notes root. If it does not exist the first visit creates it from the default template (D2) and shows a short banner "Your home page is now a note you can edit".
- One setting in `config.toml`: `[home] page = "Home.md"` (alongside the existing `quick_presets` and `thresholds`). No widget list, no new file.
- **"Make this my home"** in a note's menu sets `[home] page` to that note.
- **Rename or move** of the home note updates `[home] page` (extend the existing rename hook that already updates favorites and project `notes_path`). **Delete** clears the setting and home falls back to the built-in default with a banner.
- **"Reset home to default"** (settings and the edit-mode menu) keeps a backup copy (`Home (backup YYYY-MM-DD HHMM).md`) and rewrites the note from the template.
- Opening `Home.md` in the normal notes editor works and shows a banner "This note is your home page."

## D2. Default template

Generated once. The first line is the greeting, `# {{greeting}}, {{name}}` (Part F), which replaces the fixed page title; then section headings and the eight default widgets as ```` ```ptos ```` blocks (bodies as in section 1). Gating mirrors the old page **at generation time**: include the dashboard only if the selected dashboard exists, thresholds only if configured, quick-add-multi only if multi presets exist, the due widget only if a `default` due view exists. After generation the note is the user's; widgets whose named item is missing show an empty state with a "Configure" link. Because the template is not re-applied, new default widgets reach existing users only through the gallery's Starters.

## D3. Rendering at `/`

- The server renders a shell and embeds the note source and its `rev` as JSON (`#home-note-source`), so the first paint needs no extra request.
- The client splits the note into blocks (`blockParse` / `embedRegions`), renders text with `renderMarkdown` (A3), creates a host element per widget, and resolves **all widgets in one batch POST** (`mountBatch`). Widgets are **interactive by default on home** (`host: "home"`); in other notes they stay read-only unless `live = true`.
- **Layout rule:** consecutive widget blocks form a run that lays out as a responsive grid (`repeat(auto-fit, minmax(min(100%, 320px), 1fr))`, one column on phones). Headings, paragraphs and lists break a run and span the full width. Optional per-widget keys: `span = 2`, `hide_on = ["phone"]` or `["desktop"]` (form fields, "More options").
- Text is rendered with `renderMarkdown`, so tokens are substituted from the device's clock and the saved user name (Part F); the greeting and date update at the next boundary or when the tab becomes visible.
- A widget whose body is invalid or whose named item is missing renders an error or empty card for that block only. A note that fails to load falls back to the built-in default with a banner. Home never renders blank.
- Lazy-load widgets below the fold (`IntersectionObserver`) once a home has more than about eight widgets.

## D4. Home time and pickers

- The page keeps its existing controls and parameters (`time`, `custom_time`, `from_date`, `to_date`, `dashboard`, `due`).
- A widget body may say `time = "@home"` ("follow the home time"). The client sends `context: {time, from_date, to_date}` with the batch request and the server substitutes it; with no context it uses `tm`. Starters created on home default to `@home` where a time applies; widgets with an explicit `time` keep it.

## D5. Home edit mode

- An **Edit home** button (home header) enters edit mode; **Done** leaves it. The normal view never edits.
- Edit mode is the Blocks editor with a home presentation: widgets appear as cards with a ⋮ menu (**Configure** opens the form, **Duplicate**, **Move up**, **Move down**, **Remove**), a **drag handle** (kept from Blocks mode), a **+ Add widget** control between blocks (opens the gallery) and a **+ Add text** control (inserts an empty text block in edit state with the toolbar from C6, or any item from the gallery's Text category).
- A **phone / desktop preview** toggle applies `hide_on` and the grid so the user can see both.
- Saves go through the note save with `base_rev`; a conflict shows the existing banner (reload, save mine as a copy, overwrite). Autosave and dirty tracking are unchanged.
- Edits from another device (a `notes` event for the home path) show a "Home updated; reload" banner when not editing and reload silently when the page is clean.

## D6. Tests

- Home note: created from the template when missing; the default template has the eight widgets (or the gated subset); the setting follows rename and move; delete falls back with a banner; reset writes a backup first.
- Rendering: the page makes one batch request for all widgets; error isolation per widget; `@home` substitution (with and without context); `hide_on`; run grouping (a heading splits a run); text is sanitized (A3); no CDN references.
- Edit mode: entering and leaving; Configure opens the form; Duplicate, Move and Remove change the note source as expected; Add widget inserts a block; stale save returns 409 and shows the banner.
- Refresh: home widgets refresh on matching `data-changed` scopes; an external edit of the home note shows the banner.

---

# Part E: Finish widget interactivity

## E1. Remaining interactive mounts

Register interactive mounts for `due` (complete or open a record, honoring the existing record-identity check) and `threshold` (open the matching query or browse filter; show progress and direction). Add the same parity tests used for the other interactive kinds. These were planned for the live-widget phase and are not registered yet (`widget_host.js` registers only `todo`, `records`, `habit`).

## E2. Drill-down on group, pivot and trend

**Client (`widgets.js` — the shared renderers, so home widgets, embeds, the Queries page and the QB live preview all gain it; navigation only):**

```
group / pivot:  /browse?time=…&from_date=…&to_date=…&expr=(<where_expr>) AND (field=value [AND field2=value2 …])
trend:          /browse?time=range&from_date=<start>&to_date=<end>&expr=(<where_expr>)
```

- `where_expr` is wrapped in parentheses and ANDed with the clicked condition; a bare query with no `where_expr` contributes just the clicked condition. Values are quoted the way `ptos.quote_filter_value` does (quote when the value contains whitespace or parens; `"` unless it holds one) so spaced values survive `_tok_where`; multi-field groups AND every pair from the row's new `values` list — the joined `key` label is never re-split client-side.
- Link coverage: **table rows everywhere** (an aggregate/total row or a row without drill data stays plain); chart elements with a 1:1 mapping — group bar/hbar bars, trend points/period bars, pivot row/column labels and pivot cells; pivot's column-total bars link on `col_field=value` alone; the stacked "Other" slice never links.
- Rows open in the same tab; no new endpoint.

**Server (two small payload additions, nothing else — `where_expr` already ships on all four kinds):**

- `get_group` rows gain `values: [raw_value, …]`, built from the grouping key tuple/scalar **before** the label join.
- `get_trend` rows gain `start` and `end` (ISO), carried through from `ptos._prior_periods`.

**Browse deep-link (`/browse?expr=…`):** `browse_get` passes `request.args.get("expr", "")` to the template; `browse.html` seeds it into FilterBuilder when present (an explicit URL wins over any stored/default state) and **auto-runs**, so the click lands on results. Empty or absent param → Browse behaves exactly as today.

## E3. Calendar embed navigation

`renderCalendar` gains prev/next month arrows. The month is ephemeral client state: navigating re-fetches the same block through `embedFetch` with `from_date = YYYY-MM-01` of the target month (the embed's month resolution already prefers `from_date`'s month — `_calendar_embed_month`), keeping `name`/`time` untouched. No config, TOML or server change. Static pins: the arrows exist, the shifted body carries the new `from_date`, and the original block body is not mutated.

---

# Part F: Inline tokens in markdown

## F1. Purpose

Dynamic text without a widget: `# {{greeting}}, {{name}}` renders as "Good morning, Godwin". This replaces the old fixed home title and works in any note.

## F2. Token reference (v1)

| Token | Renders as |
|---|---|
| `{{greeting}}` | `Good morning`, `Good afternoon` or `Good evening` |
| `{{period}}` | `morning`, `afternoon` or `evening` |
| `{{name}}` | the saved user name (`[user] name`) |
| `{{date}}` | short date in the browser locale, for example `Mon 19 Oct` |
| `{{date:long}}` | for example `Monday, 19 October 2026` |
| `{{date:iso}}` | `2026-10-19` |
| `{{weekday}}` | `Monday` |
| `{{time}}` | local time, for example `09:30` |

- **Periods keep today's boundaries:** before 12:00 morning, before 17:00 afternoon, otherwise evening.
- Tokens are lowercase and case-sensitive; spaces inside the braces are allowed (`{{ name }}`).
- **Unknown tokens** are left exactly as typed. A token whose value is empty (no saved name) renders as nothing.
- **Escape:** `\{{name}}` shows the literal text `{{name}}`.
- **Never substituted:** inline code, fenced code blocks, link URLs and attributes.

## F3. Where values come from

- **Time and date:** the **device's** local clock and locale (`Date` and `Intl.DateTimeFormat`), so the greeting is correct on a phone regardless of where the server runs. This fixes the server-clock mismatch in today's `_greeting()`.
- **Name:** `base.html` adds `userName` (from `[user] name`) to `window.PTOS`; the server does not resolve tokens.

## F4. Rendering rules (safety)

- Substitution runs **after** markdown rendering and sanitizing (A3): a text-node walker (`TreeWalker`) replaces tokens in text nodes, skipping `code`, `pre`, `script` and `style` ancestors. Values are inserted as text nodes, so a name containing `<` or markdown characters can never become HTML or formatting.
- Each substituted value is wrapped in `<span class="md-token" data-token="greeting">` created with DOM methods, so it can be refreshed without re-rendering the note.
- **Refresh:** a timer fires at the next boundary (12:00, 17:00, midnight) and on `visibilitychange` to update `greeting`, `period`, `date`, `weekday` and `time` in place.
- `renderMarkdown` (A3) is the single entry point, so the editor preview, Blocks mode and home all behave the same.

## F5. Authoring

- Toolbar menu **Insert token** and slash-menu entries (Greeting, Your name, Today's date, Weekday, Time) insert tokens at the caret; the preview under the textarea shows the substituted values; the textarea shows the raw tokens.
- Search, backlinks, exports and the raw textarea show tokens as written. This is intentional and documented in the README.

## F6. Not in v1

Data tokens that need the server (for example `{{tasks_due_today}}`, `{{overdue_count}}`) would need a context in the batch request and caching rules. Leave them for later; the widgets already show those numbers.

## F7. Tests

- Pure function `tokenize(text, ctx)` (testable with `node --test`): every token; unknown tokens unchanged; spaces inside braces; escapes; adjacent tokens; empty name; period boundaries at 11:59, 12:00, 16:59 and 17:00; leap-day and month-end dates; locale formats.
- Safety: a name such as `<img onerror=x>` or `**bold**` appears as literal text; tokens inside inline code, fenced code and link URLs are untouched; a token inside a heading, list item and table cell works.
- Static checks: `renderMarkdown` is the only place that calls the token pass; `window.PTOS.userName` is injected and JSON-escaped; no template renders a greeting on the server any more.
- Refresh: a timer test with an injected clock updates the span without re-rendering the note.
- Default template: the first line of the generated `Home.md` is `# {{greeting}}, {{name}}`.

---

# Part G: Live embeds in notes (`live = true`)

## G1. Behavior

- Default stays read-only: nothing about existing note previews changes.
- A block whose body sets `live = true` mounts through `widget_host.js` (`PtosWidgets.mount`, interactive) inside the note preview; every other block keeps the static `embedRenderBody` path.
- **No global switch** (decision 7): `live = true` is the only opt-in, on every device — the old spec's settings toggle and its phone special case are both dropped.
- Kinds without an interactive mount render exactly as without the flag — `live` requests interactivity, it does not invent it.
- Blocks-mode widget cards stay static: they are edit surfaces (their controls are ✎/⇄), and the preview pane is the only live surface in the editor.
- Home is unaffected: D3 already mounts home widgets interactively by default.

## G2. Implementation

- Load `widget_host.js` in `_markdown_editor.html` via `av()`, after `embeds.js`.
- `mountEmbeds(pane)` gains the gate: parse each region's fence body for `live = true` (the client already parses `name`/`view` from it) and turn only those regions into `[data-ptos-widget][data-interactive]` shells mounted with `{host: "note"}`; results stay cached per body text.
- **Dirty-state rule:** an action inside a live embed (completing a todo, toggling a habit) must never touch the textarea, the dirty flag or autosave.

## G3. Tests and docs

- A `live = true` block mounts (widget-host element present, mount called); a block without it renders statically; two live blocks on one page work.
- Dirty-state: posting a todo completion from a live embed leaves the note clean — no save prompt, no `input` event on the textarea.
- Static pins: `widget_host.js` is loaded by `_markdown_editor.html`; no `settings.html` control references live embeds (the switch must not exist); no CDN references (A3).
- README: the Embeds section documents `live = true` with a one-line example, notes that drill-down links (E2) open Browse filtered, and states that tokens (Part F) stay raw in search/backlinks/exports. CHANGELOG entry with the phase.

---

# Phases, effort and acceptance

| Phase | Content | Estimate |
|---|---|---|
| 0 | Part A: A1 (emit), A2 (filters), A3 (vendor and sanitize) | 2–3 days |
| 1 | Part B: catalog metadata, validation, endpoints, starters | about 3 days |
| 2 | Part C (C1–C4): gallery, form, integration into slash and Blocks | 5–6 days |
| 2b | Text category and toolbar (C5, C6) and inline tokens (Part F) | 3–4 days |
| 3 | Part D1–D4, D6: home note, template, setting, rename hook, rendering, `@home` | 4–5 days |
| 4 | Part D5 (edit mode) and Part E (E1 `due`/`threshold` mounts, E2 drill-down, E3 calendar nav) | 7–8 days |
| 5 | Part G (live embeds) and the README/CHANGELOG updates | 1–1.5 days |

**Acceptance for the whole feature**
- A user can add, configure, duplicate, reorder and remove any widget on home using only taps and forms, on a 360 px phone.
- Every option of every widget is reachable in the form with help text; no TOML is required.
- A user can create headings, lists, checklists, links and bold text, and insert the greeting, name and date, using taps only (no typing of markdown symbols).
- The home greeting is right for the device's local time and updates when the period changes.
- With no internet access, home and notes render (no CDN requests).
- A malicious note cannot run script on the home page.
- Renaming, moving or deleting the home note never breaks the page.
- Clicking a group row, chart bar or trend period — in an embed, on home or on the Queries page — lands on Browse showing exactly those records.
- Calendar embeds navigate months in place, without a reload or config change.
- An action inside a `live = true` embed never marks the note as edited.
- Home is not slower than today on the same data (about 83 ms cold, 15 ms warm for the default eight widgets on the test dataset); measure on the phone.
- Full suite passes on Ubuntu and Windows CI.

---

# Risks

- **Phone performance** with many live widgets: one batch call, lazy loading, scoped refresh.
- **Form and text divergence:** hand-edited blocks must survive form saves (unknown keys preserved).
- **Blocks serialization** rewrites whitespace canonically; first save of an existing note may reformat it. Acceptable for `Home.md`; note it in the changelog.
- **Default template drift:** new default widgets do not reach existing homes automatically (Starters cover this).
- **Accidental deletion or rename** of the home note: setting update, fallback and backup on reset.
- **Sanitizer strictness:** over-aggressive sanitizing could break existing notes; run it against a sample of real notes before release.
- **Tokens outside the renderer:** search, backlinks and exports show raw `{{tokens}}`; users may be surprised. Document it, and keep the escape (`\\{{`).
- **Toolbar on phones:** a pinned bar must not be hidden by the on-screen keyboard; needs a check on real devices.
- **Text-node substitution** must not run inside code or link attributes; covered by the safety tests.
- **Drill-links change the Queries page and QB live preview too** (they share the renderers with embeds): accepted deliberately — the links are navigation only; if the extra chrome is unwanted there, gate them behind a renderer option instead (default on).
- **Multi-field group keys:** raw `values` must come from the server per row; never re-split the two-space-joined label client-side.
- **Browse deep-link precedence:** a seeded `?expr=` overrides whatever the page would otherwise open with — intended, but worth a test so a stale bookmarked expr doesn't surprise anyone.

# Not verified

How Blocks mode behaves with 20 or more blocks on a phone; marked 9.1.6's exact raw-HTML behavior (I found no sanitizer by search and have not run an injection test); the exact labels the existing time-window step offers; whether other write paths besides the three named in A1 miss their `data-changed` emission; behavior in a browser of any of the interactive widgets; whether the Blocks text-block editor and the full note editor can both host the same toolbar component; how a pinned toolbar behaves with the on-screen keyboard on the target phone.
