# PTOS Spec: Migrating Built-in Pages to Full-Size Widgets, and Leftover Fixes

Audit basis: `main` at `48461a6` (Add markdown widget add flow and gallery). 3,764 pytest tests pass in my sandbox (two Node-wrapper tests need the repo's `npm ci` for jsdom; with jsdom, 221 related tests pass) and 60 Node tests pass. Measurements were taken on Linux, in-process, on a synthetic 12-year dataset with 300 todos; nothing was run on a phone.

**Revision (tiers and the todo toolbar):** pages and widgets are now sorted into three tiers by how much interaction they need; threshold no longer needs an interactive mount; the todo page becomes a *toolbar plus body* widget in stages (section 3a); board, entity and routines stay pages until a prototype passes the gates (section 3b); the waves, effort and risks are updated to match.

**Relationship to earlier specs.** This follows `docs/specs/ptos-add-flow-and-gallery-spec.md` (implemented) and the live-widget and home-note specs (mostly implemented). It covers the next two things: (A) leftover fixes, one of which is a blocking bug found while preparing this spec, and (B) rebuilding the built-in pages as thin shells around full-size widgets, one page at a time, behind parity gates.

---

## 0. Decisions

1. **Direction:** widgets are the shared building block. A built-in page becomes a *shell* (route, page chrome, controls bar) around one full-size widget **only where that removes duplication without losing features**. Pages sort into three tiers:

   | Tier | Meaning | Examples | Plan |
   |---|---|---|---|
   | **1. View plus link** | shows data, links to details | `threshold`, `due`, `calendar`, `project`, `dashboard`, `metric`, `query` | convert the pages to shells (Wave 1) |
   | **2. Light interaction** | small actions inside the widget | `habit` (toggle days), `records` (sort, bulk, delete, export), `todo` card (complete, undo, add) | the widgets exist; pages share their code (Waves 1 and 2) |
   | **3. App-like** | a toolbar plus complex editing | full `todo`, `board`, `entity`, `routines` | `todo`: staged conversion as a toolbar-plus-body widget (Wave 3); the others stay pages until a prototype passes the gates (Wave 4, optional) |

2. **Not wholesale.** Migrate page by page, smallest first. A page's old code is deleted only after it passes the parity gates in section 4. If a migration does not shrink or simplify the code, stop and reassess. Tier 3 pages face the strictest version of that gate.
3. **Order:** fix the blocking bug and the leftovers first (Part A), finish the user-visible product steps (Part C), then migrate (Part B waves). Migration is invisible to users, so it does not come first.
4. **Out of scope:** forms (add and edit record), settings, the schema and query builders, doctor, backup, the notes editor, and an interactive kanban *card*.

---

## 1. Current state (verified)

**Page code (14 pages measured):** about 5,200 template lines, 2,600 lines of inline JS and 770 lines of inline CSS, of 16,300 template lines in total.

| Page | Template lines | Inline JS | Route lines | Widget kind today |
|---|---|---|---|---|
| todo | 1,566 | 946 | 61 | `todo` (interactive: complete, undo, add, expect guard) |
| board | 654 | 295 | 45 | `board` (view-only; **broken**, see A1) |
| routines | 504 | 118 | 123 | none |
| entity | 454 | 227 | 45 | none |
| browse | 430 | 327 | 20 | `records` (interactive via `RecordTable`) |
| queries | 276 | 207 | 21 | `query`, `records` |
| projects | 261 | 0 | 11 | `project` (static) |
| habits | 199 | 79 | 32 | `habit` (interactive) |
| calendar | 124 | 12 | 23 | `calendar` (static) |
| thresholds | 87 | 44 | 24 | `threshold` (static) |
| due | 75 | 9 | 38 | `due` (static) |

- Only `todo`, `records` and `habit` register interactive mounts in `widget_host.js`. `threshold`, `due`, `calendar`, `project` and `board` are static.
- **thresholds, due, calendar and projects use no `fetch` endpoints at all**: they are server-rendered pages whose routes (11 to 38 lines) call the same service functions the widgets already use (`get_all_threshold_status`, `get_due`, `get_calendar_data`, `get_projects_overview`, `get_habit_data`).
- The **todo page** has 47 JS functions: quick add with autocomplete, popups to edit date, priority, recurrence and threshold, bulk edit with select mode, linking tasks to notes and records (`/api/link*`), collapsible and sortable sections, search with autocomplete, delete-done, undo, filter chips. The todo widget supports complete, undo, add, chips and the `expect` guard only.
- **Payload baselines** (300 todos; Linux, in-process; thin datasets make the small widgets look empty): the `/todo` page is **612 KB of HTML** (116 ms cold, 12 ms warm); the equivalent widget result is **82 KB of JSON** (about 2 ms). Other pages are 35 to 63 KB of HTML (1 to 85 ms).
- **Tests that lock in pages today:** `/todo` has a golden snapshot (`test_todo_page_snapshot`) and 13 request calls; `/board` 21; `/projects` 24; `/routines` 51; `/calendar` 9; `/thresholds` 7; `/due` 6; `/entity` 9; `/habits` 3. **`/browse` and `/queries` have none** (by a search for GET calls in `tests/`).

**Verified widget capabilities** (tested over HTTP and in jsdom):
- **`habit`:** the widget already sets and unsets days. Clicking a day cell calls `/api/habit/toggle`; I tested a day 5 days ago, today, and a day 40 days ago, and each set and then unset correctly. **Future days are rejected** ("Cannot toggle a future date"). The grid covers the configured window (this month 28 days, last month 31, this week 7). The card has **no month arrows**, so reaching an older month means choosing another time window.
- **`records` (`RecordTable`):** header-click sort, column picker, paging, bulk edit, delete and CSV export. **Row edit opens the edit form**; there is no inline or dialog editing.
- **`threshold`:** the result carries per-threshold progress and a `query_url`; the render is a progress bar with a link. It is already complete for this tier and needs no interactive mount.
- **`board`:** `get_board_data` returns about 20 keys (lanes, field info, grid rows and matching fields, rollups, stamp fields, card title fields). The page supports HTML5 **mouse** drag-and-drop only (the mobile touch attempt `fb1f264` was reverted by `ee8d1fc`), move and advance endpoints, create-in-lane, kanban and grid views, delete and card-field configuration.
- **`todo`:** the widget supports complete, undo, add, filter chips and the `expect` guard. The page adds quick add with autocomplete, popups for date, priority, recurrence and threshold, bulk edit with select mode, linking, collapsible and sortable sections, search with autocomplete and delete-done.

---

# Part A: Leftover fixes (do first)

## A1. The board widget cannot be serialized, and it breaks the whole batch (blocking, verified)

**Problem:** `get_board_data` returns `field_info.<column>` as Python `set`s. Over HTTP:
- `POST /api/embed/resolve` with `view = "board"` returns `{"ok": false, "error": "Object of type set is not JSON serializable"}` (the raw exception text leaks to the client).
- **`POST /api/widgets/resolve` returns HTTP 500 for the entire batch** when any item is a board, so every other widget in the same request fails. A home page or any page containing one board block would show nothing. The batch contract promised per-item errors.
- The existing test calls `svc.resolve_embed` directly, so Python-level success hides the HTTP failure. A sweep of all 17 kinds over HTTP shows only `board` failing.

**Change:**
1. Return sorted lists instead of sets in `get_board_data` (`field_info`), and add a general `json_safe(value)` helper used on every resolver result before `jsonify` (sets and tuples become lists, unknown objects become strings).
2. In `api_widgets_resolve`, serialize each result inside its own `try`: an item that fails becomes `{ok: false, error: "This widget could not be rendered"}`; the HTTP status stays 200. The same wrapper protects `/api/embed/resolve`. Log the real exception server-side; never return exception text.
3. **Tests (HTTP level, not service level):** every registered kind resolves over both endpoints with the starter data; a monkeypatched resolver that returns an unserializable object fails only its own item; error text contains no exception class names.

## A2. `\{{name}}` escape does not work (verified)

`marked` consumes the backslash (`marked.parse("\\{{name}}")` gives `{{name}}`), so the token pass cannot tell it was escaped. **Fix:** in `renderMarkdown`, before `marked.parse`, replace `\{{` (outside code spans and fences) with a private sentinel; after the token pass, restore the sentinel as a literal `{{`. **Tests:** `\{{name}}` renders the literal text; `\\{{name}}` and escapes inside code spans behave as documented; a normal `{{name}}` still substitutes.

## A3. Catalog and picker polish

1. **Hide `Max rows` (`limit`)** for kinds with no rows: `capture`, `journal`, `quick_add`, `quick_add_multi`, `todo_summary`, `time_picker`. The key stays accepted. Test the field lists.
2. **Skip pointless steps:** a named-optional kind whose only choice is its default (Task list with no saved views shows one row, "Default task list") goes straight to the configure step. Test with zero and with several saved items.
3. **Validation parity** is already fixed; keep the tests.

## A4. Repo hygiene and test ergonomics

1. Move `ptos-add-flow-and-gallery-spec.md` from the repo root into `docs/specs/` (the root has 6 `.md` files again).
2. The Node wrapper tests now **fail** with `Cannot find module 'jsdom'` when `npm ci` has not been run. Locally, skip with a clear message ("run `npm ci` to enable JS tests"); in CI (`CI` environment variable set), keep them failing. Add `npm ci` to the README's contributing steps.
3. `get_home_page()` returns an invalid `[home] page` value (for example `../../etc/passwd`) unchanged. It is rejected safely when read, but logs a full traceback on every home load. Validate in `get_home_page()`: an invalid value is treated as unset and logged once as a one-line warning.

---

# Part C: Product steps that precede migration (summary; details are in the earlier specs)

1. **Pages vocabulary.** UI labels only: "Notes" becomes "Pages" (nav, page title, search hint); "New file" becomes **New page**, opening a dialog with name, folder and a template (Blank, Dashboard, Project). Keep "New folder". Internals stay (`notes/` folder, `/notes/...` URLs, `NOTES_DIR`, the `notes` scope, `note:ID` links). Add a README glossary line. Call built-in screens by name (Todos, Habits) so "page" means the user's own.
2. **Page actions:** "Pin to menu" (Favorites with friendlier wording) and "Make this my home" in the page menu.
3. **Home edit mode:** cards with a ⋮ menu (Configure, Duplicate, Move up and down, Remove), phone and desktop preview, Undo toast.
4. **Interactive `due` widget:** complete a record or open it. **`threshold` needs no interactive mount**; verify its `query_url` link works when the widget is rendered inside home and notes pages.
5. **Habit month navigation** (small): previous and next month arrows in the full-page controls bar, so older days can be set without changing the configured window. The card is unchanged.
6. **Records quick-edit dialog** (optional): edit a record from the table in a dialog, reusing the edit form's fields, without leaving the page. Today a row opens the edit form page.

---

# Part B: Page migration

## 2. Architecture

**2.1 Page shell.** One shared template, `page_shell.html`, provides the app layout, a header, a controls bar and a single mount point. A small module, `page_host.js`, reads an inlined `PAGE_SPEC` (widget kind, name, initial parameters from the URL) and mounts the widget with `host: "page"`, `size: "full"`, `interactive: true`. It keeps the URL query parameters in sync (`history.replaceState`), so deep links and Favorites keep working.

**2.2 Full mode lives in the widget.** The widget's `mount(el, data, ctx)` already receives a context; add `ctx.size` (`"card"` or `"full"`). Full-mode features (filters bar, grouping, bulk actions, shortcuts, popups) are implemented once in the widget's module and gated on `ctx.size`; the card is a subset. No second implementation in the page, and no feature exists only in a page.

**2.3 Controls bar.** A reusable `PtosPageControls` renders the shared controls (time-window picker, database or dashboard selector, month navigation, search with autocomplete) and calls the widget's `refresh(context)` on change.

**2.4 Server.** Each page route shrinks to: parse the same query parameters it accepts today, build `PAGE_SPEC`, **resolve the widget server-side and inline the result** (`PAGE_DATA`), and render the shell. First paint then needs no extra request. The widget renders client-side from the inlined data.

**2.5 Compatibility.** Keep every existing URL and query parameter. Keep the write endpoints (`/todo/add`, `/board/move`, ...) and their `expect` guards. Keep the old template reachable at `?legacy=1` during a wave; delete it when the gates pass.

**2.6 Widget anatomy: toolbar and body.** A widget renders into up to two regions: an optional **toolbar** and a **body**. `ctx.size` decides: `"full"` shows the toolbar and the full body; `"card"` shows only the body, and may opt in to one small action (for example `toolbar = "add"` on a todo card). Shared code is split into three parts so card and page never diverge:
- a **controller** (state, parameters, selection, actions, data refresh through the existing endpoints, URL sync supplied by the host),
- a **toolbar view** (inputs and chips that only change controller parameters),
- a **body view** (the list, table, grid or bars that render controller data).

A toolbar never fetches data itself: it edits parameters on the controller, and the controller refreshes the body. This is what makes a page-shaped screen (add box, filters, grouped list) a widget.

## 3. Writes and identity

Widget actions keep using the existing JSON endpoints. Todo actions send `line_no` plus the task's raw text (`expect`); the server rejects a mismatch. Extend the same guard to every write the full-mode todo and board widgets use (edit, delete, bulk edit, link, move).

## 3a. The todo widget: toolbar plus body (Wave 3)

The todo page is not a widget today, but its logic is already shared: `query_todos` handles project (with `-` exclusion), context, priority, due, search, `linked_to`, `groupby` (timeline, priority, project, context, none), sort and limit. The widget calls it with parameters, so the toolbar only edits parameters.

**Parts** (`todo_controller.js`, `todo_toolbar.js`, `todo_list.js`, registered through `widget_host.js`):

| Part | Responsibility |
|---|---|
| Controller | parameters `{project, context, priority, due, search, groupby, sort, include_done}`; selection set; collapsed sections; resolves data; actions (add, complete, undo, delete, edit field, bulk) through the existing endpoints, every one carrying `line_no` plus `expect` |
| Toolbar (full only) | add box with autocomplete, project filter with exclusion, active-filter chips, search box, group-by switch (Timeline, Priority, Project, Context, None), sort, a Select toggle for bulk mode |
| List (body) | grouped sections with counts, collapsible (state kept per widget in `localStorage`), rows with checkbox, text, project and context chips, due badge and priority |

**Card versus page:** the card shows the list only, `limit` rows, and may opt in to a compact add field; chips open `/todo` with that filter. The page is the same widget at `size: "full"` with the toolbar, and keeps its URL parameters (`?project=&context=&priority=&due=&search=&groupby=`) in sync.

**Stages** (each ships behind `?legacy=1` and passes G0 to G7 for the features it covers):

| Stage | Adds | Estimate |
|---|---|---|
| T1 Read-only parity | toolbar filters, search, group-by, chips, collapsible sections and counts; `/todo` renders the shell with inlined data; golden parity with `test_todo_page_snapshot` | 2 to 3 days |
| T2 Everyday actions | add with autocomplete, complete, undo, delete-done, `expect` guards on every write, refresh on `data-changed` without losing typed text or selection | 2 to 3 days |
| T3 Popups | date, priority, recurrence and threshold editors (reuse the page's popups as shared components) | 3 to 4 days |
| T4 Bulk and links | select mode with bulk edit, linking to notes and records (`/api/link*`, retro-id), keyboard shortcuts | 3 to 4 days |

**G2 feature checklist for todo:** quick add and autocomplete, date popup, priority popup, recurrence popup, threshold popup, bulk edit and select mode, linking, collapsible sections, section sort, search with autocomplete, delete-done, undo, filter chips, group-by (four modes plus none), keyboard shortcuts. Each item names the stage that delivers it and the test that covers it.

**Performance:** 300 tasks arrive as about 82 KB of JSON against a 612 KB HTML page today. Render client-side; lazy-render collapsed sections; no list virtualization until a phone measurement says it is needed.

**Code gate:** after T1 and T2, compare lines deleted from `todo.html`, its route and inline JS against lines added to the three modules. If the totals do not favor deletion, stop and keep the page, sharing only row renderers and popups with the card.

**Tests (jsdom):** toolbar edits trigger exactly one resolve; every group-by mode; add, complete and undo; section collapse persists; chip add and remove; keyboard behavior; a stale `expect` produces the "Task changed on disk" message and a refresh; a `data-changed` refresh keeps selection and typed text.

## 3b. Board, entity and routines stay pages for now (Wave 4, optional)

- **Why:** the board's data and interactions are the most complex in the app (about 20 data keys; lanes, grid view, rollups, stamp fields; drag between lanes; create in a lane; advance), and its touch drag-and-drop attempt was reverted. A card-size interactive kanban is out of scope.
- **Card version (after A1):** keep the static render and make it a compact summary: lane names with counts, the top few cards per lane, and an "Open board" link.
- **Page:** unchanged. Share small helpers (card markup) only where that removes duplication.
- **Preconditions to revisit conversion:** (a) a touch-safe move design (a long-press handle plus a "Move to lane" menu) proven on a real phone; (b) create-in-lane through a dialog using the add form's fields; (c) the grid view as its own component; (d) a prototype that passes the G6 code gate.
- **`entity` and `routines`** follow the same rule. `routines` may reuse the todo components after Wave 3.

## 4. Parity gates (every page, every wave)

| Gate | Requirement |
|---|---|
| **G0 Characterization** | Before touching a page, add tests that lock its current output. `/browse` and `/queries` have none, so write them first; `/todo` already has a golden snapshot; add one for each page in the wave. |
| **G1 Data parity** | The same parameters give the same rows and counts in the page and in the widget (compare ids, not markup). |
| **G2 Feature checklist** | Every feature the old page had is listed with a test or an explicit manual check. Anything dropped is dropped on purpose and noted in the CHANGELOG. |
| **G3 Performance** | HTML plus JSON bytes and server time are at or below the baselines in section 1; first paint on the phone is not slower; client render time for 300 todos is measured on the phone (target: under 200 ms after data arrives; unknown until measured). |
| **G4 URLs** | Existing query parameters and Favorites URLs still work; `?legacy=1` still works until deletion. |
| **G5 Behavior on devices** | Keyboard shortcuts, tap targets, scroll position and focus behave as before on a 360 px phone and on desktop. |
| **G6 Code gate** | Lines deleted from templates, inline JS and routes exceed lines added to widgets and shell (tests excluded). Record both numbers per wave in the CHANGELOG. Tier 1 and 2 pages must pass; for tier 3 the gate is checked after the first two stages and the migration stops if it fails. |
| **G7 Rollback** | The old template stays in the repo, reachable by `?legacy=1`, until the wave has run on your phone for a week. |

## 5. Waves

**Wave 0:** Part A and Part C (items 3 and 6 can run in parallel with Wave 1).

**Wave 1: tier 1 pages plus habits.** `thresholds` (87 lines), `due` (75), `calendar` (124), `projects` (261), `habits` (199): about 750 template lines and 140 lines of inline JS today, no endpoints except habit toggle. Needs the `due` mount (complete or open a record), a `calendar` mount (month navigation, click a day), `project` links, the habit month arrows (Part C item 5), and `PtosPageControls` (time picker, month navigation). `threshold` needs no mount. **Purpose:** prove the shell, inlined data and gates before touching anything large.

**Wave 2: records family.** `browse` (430) and `queries` (276): about 700 template lines and 530 lines of inline JS. `RecordTable` is already shared, so most of this is page chrome: the filter builder, saved-query run and save, and export. Full-mode `records` widget plus a `FilterBuilder` panel. **First write the missing G0 tests for `/browse` and `/queries`.** The optional records quick-edit dialog fits here.

**Wave 3: todo** in stages T1 to T4 (section 3a). Do not start it until Wave 1 has produced real G6 numbers.

**Wave 4 (optional, gated): board, entity, routines** (section 3b). Only if a prototype passes the preconditions and G6.

**Not migrated:** forms, settings, schema builder, query builder, doctor, backup, favorites page, notes editor.

## 6. Effort

All numbers are my estimates, to be replaced by measured values after Wave 1.

| Item | Estimate |
|---|---|
| Part A | 1 to 2 days |
| Part C (items 1 to 4) | 5 to 8 days; habit arrows 0.5 day; quick-edit dialog 1 to 2 days |
| Wave 1 (including shell and controls) | 3 to 5 days |
| Wave 2 | 4 to 6 days |
| Wave 3 (T1 2 to 3, T2 2 to 3, T3 3 to 4, T4 3 to 4) | 10 to 14 days |
| Wave 4 | not estimated until a prototype exists |

Re-estimate after Wave 1, using its real G6 numbers (lines deleted and added) and phone measurements.

## 7. Risks

- **Feature loss:** pages have behaviors no one remembers (popups, shortcuts). The G2 checklist and `?legacy=1` guard against this.
- **Slower first paint on the phone:** inlined data and a small client render should be faster than a 612 KB HTML page, but measure.
- **Two code paths during a wave:** keep waves short and delete old code promptly.
- **Todo wave size:** it is the largest and riskiest; split it into sub-waves by risk.
- **Drift between card and full modes:** the single module with `ctx.size` is the guard; a test forbids page-only logic in the shell.
- **Savings may be smaller than hoped:** the small pages save little; real savings are in todo, browse and entity, and they depend on porting features into the widgets, not deleting them.

- **Toolbars growing cards:** keep cards body-only by default; a card may opt in to at most one small action.
- **Todo conversion may not shrink code:** the G6 check after T1 and T2 decides; the fallback is to keep the page and share components.
- **Touch drag on the board:** unresolved; that is why the board stays a page.

## 8. Definition of done

- The HTTP-level sweep passes for all kinds, and a failing item never fails the batch.
- Every migrated page passes G0 to G7, and its old template and inline JS are deleted.
- The CHANGELOG records, per wave, lines deleted and added.
- Shell, widgets and controls are the only places a view is rendered; forms and builders are untouched.

## 9. Not verified

Real-device behavior and client render times; the full feature inventory of `routines`, `entity` and `board` (I measured sizes, routes and endpoints, not every behavior); whether `/browse` and `/queries` are covered by tests that use other request patterns; the real payload sizes of the small widgets on a populated dataset; whether the todo widget can reach the page's features without growing larger than the page it replaces.

Also not verified: the exact list of `get_board_data` keys and the board page's every behavior (I report what I inspected); the entity and routines pages' behavior; whether the todo page's autocomplete needs server endpoints the widget does not call today; and that the habit card, which has no month arrows, is acceptable on a home page.
