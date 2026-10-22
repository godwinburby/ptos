# Phase 2b — Gallery Text category + text-block toolbar

Per user request (spec C5/C6, trimmed): gallery gets a **Text** category reusing `_FORMAT_GROUP` (no duplicate list), and a small markdown-source toolbar appears when editing text (Blocks text-block edit **and** the full note/journal editor — user's answer). Heading button = **popup menu H1/H2/H3** (user's answer).

## 1. Shared definitions — extend `_FORMAT_GROUP`, don't extract (deviation from spec C5)

Spec C5 proposed a new `text_blocks.js`; user said reuse `_FORMAT_GROUP`. One source either way; reuse = far less churn (test_blocks pins `seed:`/`xform:` strings in slash_embed).

`web_static/js/slash_embed.js`:
- Add two entries to `_FORMAT_GROUP` (slash menu gains them too — spec C227 wants Callout there anyway):
  - `Paragraph`: `seed: ""`, `run: _prefix("")` (strips the typed `/` token, caret at line start), `xform: {t:"prefix", pre:"", all:true}` (strips leading `#`/`-`/`>`/`1.`/`- [ ]` markers → plain paragraph; `_convert` already handles `pre:""`), `text: true`, icon `pilcrow`, description.
  - `Callout`: `seed: "> **Note**\n> "`, `run: _block("> **Note**\n> ", …)` (mirror existing `_block` usage; caret after the trailing `> `), `xform: {t:"prefix", pre:"> ", all:true}` (carries existing text as quoted lines), `text: true`, icon `message-square`, description.
- Flag the nine **gallery** entries with `text: true`: Heading 1/2/3, Paragraph, Bulleted list, Numbered list, Task list (Checklist), Quote, Divider, Table. NOT flagged (slash-only): Code block, Bold, Italic, Strikethrough, Inline code, Link (user's enumeration omits Code block from the gallery; all wrappers are inline actions, not blocks).
- Add `icon` + `description` keys to those entries (labels unchanged — slash renders labels only, so extra keys are harmless).
- Export the group for the picker (picker loads **before** slash_embed; it reads at render time, which is always after both loaded): `window.PtosSlashFormat = _FORMAT_GROUP;` near the existing `window.openSlashPicker` export.

## 2. Gallery Text category — `web_static/js/widget_picker.js`

- **Add mode only**: home Categories section prepends a synthetic `Text` card (`data-cat="text"`, icon `type`) when `_S.mode === "change"` — no (change mode keeps the "Markdown & text…" Convert card as the single text path; widget⇄ stays on slash Format picker). So: show Text card only in `mode === "add"`; `_renderCat` special-cases `_S.cat === "text"` → render the `text: true` entries from `window.PtosSlashFormat` as `data-text="<label>"` cards (icon/description from the item).
- Search: text entries join the home `q` results (haystack = label + description + aliases) and filter inside the Text step.
- `_catIcon` gains `text: "type"`; `_ICONS` gains the new SVGs (`type`, `pilcrow`, `list`, `list-ordered`, `quote`, `minus`, `message-square` — `table`/`check-square` exist).
- Pick path `_pickText(label)` → find item → **bypass `_finish`**: no `merge` (TOML-only), no `_pushRecent` (a markdown seed must never enter widget Recent) → `close()` then `_S.onPick({kind:"md", seed, xform, label})`.
- `_wire` gains a `dataset.text` branch.

## 3. Consumers of md picks from the gallery

- `slash_embed.js` `_commitPick` gallery branch (Blocks ＋/⇄ → "All widgets…"): `onPick: function(p){ _closePicker(); if (onPick) onPick(p && p.kind === "md" ? p : {kind:"widget", source: p}); }`.
- `slash_embed.js` `_openGallerySlash` (keystroke `/` → "All widgets…"): if pick is `{kind:"md", …}`, replace the typed `/` token with the seed (caret at seed end — matches how `_prefix` leaves the caret) instead of building a ```ptos fence.
- `md_blocks.js` `_change` widget branch: **untouched** — Text category is add-mode-only, so its `onPick(source: string)` contract is safe. Widget→text remains Convert card → `_formatChange` (which now also offers Paragraph/Callout via `_FORMAT_GROUP`).

## 4. Toolbar — new `web_static/js/md_toolbar.js`

`window.PtosToolbar = { attach, wrapSelection, togglePrefix, heading, linkMarkup }`.

- **Pure core** (no DOM, node-testable, per spec C6 `(value, selectionStart, selectionEnd)` style):
  - `wrapSelection(text, s, e, open, close)` → `{text, start, end}`: toggle (already-wrapped selection unwraps), empty selection inserts markers with caret between.
  - `togglePrefix(text, s, e, pre)` → multi-line add/strip; switching list types (`- ` ↔ `- [ ] `) replaces the old prefix (strip recognized markers on affected lines first); same-prefix again strips.
  - `heading(text, s, e, level)` → `# `/`## `/`### ` on the selected lines (replaces any existing heading level); same level strips.
  - `linkMarkup(selText, url)` → `null` for schemes other than `http/https/mailto` or internal paths (leading `/`, `#`, `?`); rejects `javascript:`/`data:`.
- **`attach(textarea)`**: idempotent (marker `data-md-tool`), inserts `<div class="md-tool">` before the textarea, returns `{destroy}` (DOM removal on card rebuild is enough; destroy used on explicit detach). Buttons: **B**, *I*, 🔗 Link (prompt() for URL; prompts for text only when nothing selected), **H** → small popup menu H1/H2/H3 (same-level click strips; popup `.md-tool-menu` anchored under the button), Bulleted list, Checklist. All `type="button"` with `aria-label` + `title`.
- **Shortcuts** on the attached textarea: Ctrl/Cmd+B, I, K (spec; cheap).
- **Attach points**: (a) `md_blocks.js` `_edit` text branch — call `PtosToolbar.attach(ta)` after inserting the textarea (widget branch untouched: the form is its own editor); (b) `_markdown_editor.html` boot IIFE — attach to `#md-editor`, guarded `if (window.PtosToolbar && ta)`.
- **CSS**: `.md-tool`, `.md-tool-btn`, `.md-tool-menu` in `_markdown_editor.html`'s inline `<style>` (editor-only; template edit → no asset-version concern). Single row, `overflow-x:auto`, 44 px min targets.
- Load order in `_markdown_editor.html`: widget_toml → widget_form → widget_picker → **md_toolbar** → slash_embed → md_blocks.

### Explicitly deferred (spec C6 remainder, not in this pass)
Numbered-list toolbar button, Quote/Code buttons, token menu (Part F), Help cheat-sheet, Enter list-continuation, Tab indent/outdent, visualViewport keyboard pinning, under-textarea token preview, home edit mode (D5). Undo/redo = native textarea history (nothing to build).

## 5. Tests

- **New** `tests/js/md_toolbar.test.js` (`node --test`, skipif node absent): wrap/unwrap with/without selection, already-wrapped, unicode/emoji, CRLF; heading switch/strip across lines; bullet↔checklist switching; link scheme accept/reject; caret positions.
- **New** `tests/test_text_blocks.py`:
  - node wrapper for `md_toolbar.test.js` (copy the `test_widget_form.py` subprocess pattern).
  - Single-source pins: `widget_picker.js` has **0** `seed:` occurrences and reads `window.PtosSlashFormat`; `slash_embed.js` exports it; only one file defines `Paragraph`/`Callout` seeds.
  - `_FORMAT_GROUP`: the nine `text: true` flags; Paragraph/Callout entries with xform.
  - Picker: Text card add-mode-only, `_renderCat` text branch, `data-text` wiring, md pick skips `merge`/`_pushRecent`.
  - slash: `_commitPick` and `_openGallerySlash` pass `{kind:"md"}` through.
  - Toolbar: script order in the partial, `PtosToolbar.attach` in md_blocks text `_edit` + boot attach to `#md-editor`, aria-labels present, no `eval`.
- **Update** `tests/test_widget_form.py::TestScriptOrder` — extend to include `av('/static/js/md_toolbar.js')` between picker and slash_embed.
- **Re-check** `tests/test_blocks.py` pins (`seed:` ≥15, listed seeds, `xform:` ≥15) — we only add entries, so they should hold; fix if a count assertion was exact elsewhere.
- Full suite `python -m pytest tests/ -q`.

## 6. Docs

- `CHANGELOG.md`: new `### Phase 2b (home-note spec): gallery Text category, text-block toolbar` under existing `## 2026-10-22`.
- `AGENTS.md`: amend the slash-Format bullet (Paragraph/Callout + `text: true` flags + `window.PtosSlashFormat` export) and the Phase-2 gallery bullet (Text category, add-mode-only, md-pick contract); new short bullet for `md_toolbar.js` (pure-function core, two attach points, deferred list).
- Spec files stay untracked.

## 7. Manual test checklist (after implementation)

1. `/` in full editor → Format group shows Paragraph + Callout; picking Callout inserts the seed at caret.
2. `/` → "All widgets…" → gallery home shows **Text** card first under Categories → Heading inserts `# ` replacing the token.
3. Blocks ＋ → All widgets… → Text → Table inserts a table block in edit state with caret placed.
4. Blocks text-block ⇄ → still slash Format picker (includes new entries); converting a heading → Paragraph strips the marker.
5. ✎ on text block → toolbar above textarea: B/I toggle (incl. unwrap), H popup (H1→H2→H3→none), bullet↔checklist switch, link prompt rejects `javascript:`. Save/Cancel clean.
6. Full note/journal editor: toolbar above textarea, Ctrl+B/I/K work, other toolbar-less pages unaffected.
7. Gallery Recent never shows text picks; change mode never shows the Text card.
