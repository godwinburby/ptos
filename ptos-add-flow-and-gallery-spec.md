# PTOS Spec: Add Flow and Gallery Navigation

Audit basis: `main` after `f9b1d3a` (widget gallery and markdown toolbar), 3,681 pytest tests and 30 Node tests passing. Findings come from reading the code and running the gallery and form in jsdom against a live server (desktop mode); nothing was tried in a real browser or on a phone.

**Relationship to earlier specs.** This finishes Part C3 (integration) of `ptos-home-note-and-widget-editor-spec.md`: the gallery and form exist, but the Blocks `+` button and the `/` menu still show the old flat list. Part D (home as a note), Part E and Part F (tokens) are unchanged unless stated here.

---

## 0. Decisions

Confirmed by the product owner:
1. **Text stays a category tile** in the gallery. There are no Widgets/Text tabs.
2. **`+` opens the gallery directly.** It no longer goes through the slash list.
3. **Navigation stays a drill-down list** (category, then kind, then saved item), in the gallery and in the `/` menu. No flat dump, no hover flyouts.

Assumed (adopted from my recommendation; say so if wrong):
4. After choosing, the **configuration form opens before the block is inserted** (same form as ✎ edit), except for widgets with no options.
5. **Saved-item rows get descriptions**, which needs a small server addition.

---

## 1. Current state (verified)

**Entry points**

| Entry | Code | Opens |
|---|---|---|
| `+` bar between blocks, and the add row at the end | `md_blocks.js` `_pickerAt` | `openSlashPicker` (flat list) |
| `?` change on a widget | `md_blocks.js` | gallery, `mode: "change"` |
| ✎ edit on a widget | `md_blocks.js` | `PtosWidgetForm` |
| `/` typed in a note | `slash_embed.js` `attachSlashEmbed` | flat list |
| "Insert view" button | `slash_embed.js` `openSlashMenu` | flat list |

**The flat list:** `_buildMenu("")` concatenates the Format group, a one-item "Widgets" group whose only entry is "All widgets…", and every saved-item group (queries, metrics, dashboards, thresholds, and so on). With an empty query it shows everything. "All widgets…" opens the gallery.

**The gallery** (`widget_picker.js`, 601 lines): the home screen is **12 starter cards followed by 7 category tiles (19 cards)**, then Recent. Category, then kind drill-down works with a back button; search works across starters, kinds, aliases and text blocks. Problems found:
- The saved-items step lists **bare names** (`food_ratio`, `avg_spend`) with **no description and no search box** (`search.style.display = "none"` on the items step), up to 300 rows.
- Picking a kind, item or starter calls `onPick` **immediately**; there is no form step, and the time-window step that the slash path had (`_TIME_CAPABLE`) is gone.
- Starters: `Overdue tasks` appears twice (one is overdue *records*); Journal and Todo summary starters are missing.
- Catalog and form: `Max rows` still appears for capture, journal, quick add and todo summary; `/api/widgets/validate` accepts `priority = "zz"`, which the resolver rejects.
- The Text category's token entries (Greeting line, Today's date, Your name, and the toolbar's token menu) insert `{{greeting}}` and similar, but **nothing substitutes them yet** (Part F is not built); `renderMarkdown("# {{greeting}}")` returns the raw braces.

**Data:** `/api/embed/candidates` and `/api/widgets/options?source=saved.<kind>` return only name strings.

---

## 2. Goals and non-goals

**Goals**
- One hierarchy, used by the gallery and the `/` menu: Text and six widget categories, then kind, then saved item, then configure.
- The first screen is short and fits a 360 by 640 phone without scrolling.
- Every level is searchable; search at the top level spans everything.
- Adding a widget ends in the same form used for editing, with a live preview.
- Saved items are recognizable (type and one-line description).

**Non-goals:** per-device menus, user-defined categories, drag-to-reorder inside the gallery, changing the registry's kinds.

---

## 3. Design

### 3.1 One tree for both surfaces

A single module builds the hierarchy so the gallery and the slash menu cannot drift:

```
Level 1  Quick starts (strip) + category tiles + Recent
Level 2  Category → items: kinds, or text blocks for Text
Level 3  Kind → saved items (named kinds only)
Level 4  Configure (form) → Add
```

- Categories, in order: **Text**, Tasks, Tables and records, Numbers and charts, Goals and habits, Capture, Projects. (Text first: it is the most frequent add.)
- Implementation: `PtosWidgetNav` (in `widget_picker.js` or a small `widget_nav.js`) exposes `tree(catalog, textBlocks)`, `children(path)`, `search(query)`, and `describe(path)`. Both `widget_picker.js` and `slash_embed.js` call it; neither keeps its own list.
- The slash menu's Format group is removed as a top-level list; its items live under the Text tile.

### 3.2 Gallery home screen

- Header "Add to page", the search box, and a close button.
- **Quick starts:** a horizontal strip of at most 6 chips (icon plus label), then "See all (12)" which opens the full starter list as a drill-down page. Starters are **no longer a 12-card grid above the categories**.
- **Category tiles:** 2 columns on phones, 3 to 4 on desktop; each tile shows icon, name, item count and a one-line hint. The tile list is the main content of the first screen.
- **Recent:** one row, shown only when there is history (per device, widgets only, capped at 8, as now).
- Acceptance: on 360 by 640 the first screen shows the search box, the starter strip and all 7 tiles without scrolling.

### 3.3 Drill-down behavior

- A back arrow and a breadcrumb ("Add to page › Tasks › Task list") on every level below home. Esc and the Android back button go up one level; at the home level they close the sheet.
- Search is local to the current level, except at the home level where it searches the whole tree and shows a **flat, grouped result list** (group label = category), capped at 30 with "show more".
- Level 2 rows: icon, label, one-line description, chevron when the item has a child level.
- Text items insert immediately (no form) with the seed and caret as the existing text block definition says.

### 3.4 Saved-item step (Level 3)

- Rows show: icon for the item type, name, **one-line description**, and a right-aligned tag (for example `chart`, `table`).
- **Search box is shown** whenever there are more than 6 items.
- Sort: Recent first, then alphabetical. Queries may be grouped under small headers ("Tables", "Charts") when both kinds exist.
- Row count in the header ("17 queries"); an empty state with a link to the matching builder ("No saved metrics yet — create one").
- Keep the 300-row cap and show a note when it is hit.

### 3.5 Configure step (Level 4)

- After a pick (kind, saved item, or starter), the same sheet switches to `PtosWidgetForm.mount(container, {body, onSave, onCancel})` with the pick as the initial body, the live preview on top, advanced fields under "More options", and "Edit as text".
- Buttons: **Add widget** (calls `onPick`) and **Back** (returns to the previous level without inserting). Closing the sheet inserts nothing.
- **Skip the form** for kinds flagged `quick_add: true` in the catalog: `capture`, `quick_add`, `quick_add_multi`, `journal`, `todo_summary` (they have nothing worth configuring beyond a title).
- The old slash time-window step is replaced by the form's time-window field (labelled choices), defaulting to the kind's usual window.
- Starters also open the form (so the user can tweak them); the form's primary button is already "Add widget", so adding a starter unchanged is one tap.
- `mode: "change"` keeps its current behavior (merge and replace).

### 3.6 The `+` flow

- Both `+` buttons call `PtosWidgetPicker.open({mode: "add", anchor, onPick})` directly. `_pickerAt` stops calling `openSlashPicker`; `onPick` receives either `{kind: "widget", source}` or `{kind: "md", seed, caret, xform}` as `_commitPick` produces today.
- After insertion: scroll to the new block, highlight it for about a second, and show an **Undo** toast (removes the block). Insert position is unchanged (the `at` index).

### 3.7 The `/` menu (inline drill-down)

- Typing `/` shows the **top level only**: the 7 category rows (with chevrons), then up to 3 Recent items. At most 10 rows are ever visible at once.
- Keyboard: ↑ and ↓ move, → or Enter on a category drills in, ← or Backspace on an empty query goes up, Esc closes.
- Typing text after `/` filters across the whole tree into a flat list (cap 12) with a final row "More in gallery…" that opens the gallery with the same query.
- Text items insert inline as today. For widgets the popover is too small for the form: picking a widget opens the **gallery sheet at the configure step** (the slash token is removed, the block inserts where it was typed).
- "Insert view" opens the same drill-down. The "All widgets…" entry and the candidate dump are removed.

### 3.8 Server changes

1. **Saved-item descriptions.** `GET /api/widgets/options?source=saved.<kind>&detail=1` returns `items: [{name, description, tag}]` in addition to the existing `values: [...]` (unchanged for current callers). A helper `describe_saved(kind, name, cfg)` builds the text from the saved definition, for example:

   | Kind | Example description | Tag |
   |---|---|---|
   | query | `Spending by category · this month` | `chart` or `table` |
   | metric | `Average of amount · expense` | |
   | dashboard | `6 metrics` | |
   | threshold | `3 limits · this month` | |
   | board | `Columns: todo, doing, done` | |
   | habit | `Daily · 30-day view` | |
   | calendar, due, project, todo view | one-line summary from its keys | |

   Wording is defined with tests; a missing or odd definition falls back to the kind name.
2. **Catalog flags and metadata:** add `quick_add` to the kinds listed in 3.5; hide `limit` ("Max rows") for kinds with no rows; add item counts per category to the catalog.
3. **Starters:** rename the `due` starter to "Overdue records"; add Journal and Todo summary starters; keep hiding starters that need a missing named item; a test asserts labels are unique.
4. **Validation parity:** `/api/widgets/validate` calls the same validators as the resolver (`priority` single letter A to Z, `limit` at least 1, enums), so form and render never disagree.

### 3.9 Accessibility and mobile

- The sheet is a dialog with a focus trap; rows are a listbox with options; categories announce their item counts.
- Focus the search box automatically on desktop only (on phones it would open the keyboard before the user sees the tiles).
- 44 px tap targets; sheet height about 85% on phones; honor `prefers-reduced-motion`.
- Handle the Android back button with `history.pushState` / `popstate` so back closes one level rather than leaving the page.

---

## 4. Carry-over fixes bundled with this work

1. **Tokens:** hide the token entries (Greeting line, Today's date, Your name, Weekday, Time, and the toolbar's Insert token menu) behind a flag until Part F (`md_tokens.js`) ships, then turn them on. Raw `{{...}}` must never reach a user.
2. **Sanitizer hardening** (`md_render.js`): drop `style` from the allowed attributes (move the task-list inline style to a CSS class), allow `input` only as a disabled checkbox, and decide on remote images (keep and document, or restrict to same-origin). Confirmed by jsdom: a `<p style="position:fixed;inset:0;…">` and `<input type=password>` currently survive.
3. **CI:** add `jsdom` as a dev dependency (a `package.json` plus `npm ci` in the workflow) so the end-to-end sanitizer test and the new picker tests run in CI instead of skipping.
4. **Repo hygiene:** move the two spec files committed to the repo root into `docs/specs/`.

---

## 5. Tests

**Node with jsdom** (`tests/js/widget_picker.test.js`, `tests/js/slash_nav.test.js`; run by the existing pytest wrapper when Node is available):
- Home screen: at most 7 tiles and at most 6 starter chips; Recent hidden when empty; no duplicate starter labels.
- Drill-down: tile, then kind, then saved item, then form; back returns one level at each step; Esc at home closes; breadcrumb text.
- Search: home-level search is flat and grouped with category labels; level-local search; cap and "show more".
- Saved items: search box present above 6 items; descriptions and tags rendered; cap note at 300.
- Configure step: **Add widget** fires `onPick` with the merged body; **Back** and close insert nothing; `quick_add` kinds skip the form; Text items insert without a form.
- `+` flow: `_pickerAt` opens `PtosWidgetPicker` and never calls `openSlashPicker`; after insert the block is highlighted and Undo removes it.
- Slash menu: empty query shows at most 10 rows; keyboard drill-in and out; typed query yields a flat list with the "More in gallery…" row; picking a widget opens the sheet at the configure step; no Format or candidate dump at the top level.
- Tokens hidden while the flag is off.

**Python:**
- `describe_saved` per kind with fixtures; `?detail=1` returns both `items` and `values`.
- Catalog: `quick_add` flags, no `limit` field on the listed kinds, unique starter labels, Journal and Todo summary starters present, every starter resolves.
- Validate parity: `priority = "zz"`, `limit = -3` and bad enums error in `/api/widgets/validate` exactly as in the resolver.
- Sanitizer (jsdom): `style` attribute removed, non-checkbox inputs removed, task lists still render, existing payload cases unchanged.

**Manual (360 by 640 and 412 by 915):** the whole first screen without scrolling, back button behavior, keyboard overlap in search and the form, one-handed reach to the Add button.

---

## 6. Phases, effort and acceptance

| Phase | Content | Estimate |
|---|---|---|
| 1 | Server: `describe_saved`, options `detail`, catalog flags and starters, validate parity | 1 to 2 days |
| 2 | Shared tree, gallery home and drill-down redesign, saved-item step | 2 to 3 days |
| 3 | Configure step chaining, `+` rewiring, highlight and Undo | 1 to 2 days |
| 4 | `/` menu as a drill-down list | about 2 days |
| 5 | Carry-over fixes (section 4); Part F tokens is a separate 2 to 3 days | about 1 day |

**Acceptance**
- The gallery's first screen shows no more than 7 tiles, one starter strip and Recent, and needs no scrolling at 360 by 640.
- A no-name widget is added in at most 4 taps (`+`, category, kind, Add); a named widget in at most 5.
- The `/` menu never shows more than 10 rows at once, and the old flat list is gone.
- Saved-item rows show a description; every level has search where it has more than 6 rows.
- Back and close never insert anything; Undo removes the last insert.
- The sanitizer residuals and the validate and resolver mismatch are fixed; the full suite and the new Node tests pass in CI on Ubuntu and Windows.

---

## 7. Risks

- **Two surfaces drifting:** the shared tree module is the guard; a test forbids a second list in `slash_embed.js`.
- **A form inside a small popover:** avoided by routing slash widget picks to the sheet.
- **Descriptions going stale or odd:** generated from definitions at request time, with a fallback.
- **Android back button:** needs a real-device check.
- **Long saved-item lists:** the 300-row cap and search; virtualization only if it proves slow on the phone.

## 8. Not verified

Layout and behavior on a real phone or browser (jsdom was used, desktop mode); which kinds are in `_TIME_CAPABLE` and what default window each should use in the form; the final description wording for each saved kind; Part E (interactive `due` and `threshold`), which I did not re-check in this pass.
