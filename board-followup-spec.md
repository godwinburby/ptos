# Spec — Board/Kanban follow-up fixes

Follow-up to commit `0638fc5` (board card title field picker, drag priority,
multi-preset `return_to`, editCard/onParentChange `return_to` fixes).
Six items, ordered by priority. Each is independent and can ship as its own
commit.

---

## 1. Remove or wire up the dead single-board API

**Problem:** `svc.save_board()`, `svc.delete_board()`, and the routes
`/api/board/save` / `/api/board/delete` in `ptos_web.py` are not called from
any template. All board create/edit/delete in the UI goes through the bulk
`saveAll()` → `/query-builder/save` → `save_queries_full(raw_boards=...)`
path. Two independent validation paths exist for the same data
(`save_board`'s regex check vs. `save_queries_full`'s `_clean_bare_name` +
regex check) and can silently drift apart.

**Decision needed (pick one):**

- **(a) Remove.** Delete `svc.save_board`, `svc.delete_board`, and the two
  routes. Simplest option — nothing in the UI depends on them today.
- **(b) Keep, and use it.** If a single-board save/delete API is wanted for a
  future non-Query-Builder entry point (e.g. a "New board" button directly on
  `/board`), wire the UI to call it instead of round-tripping the entire
  `queries.toml` through `saveAll()` for one board change.

**Recommendation:** (a) — nothing today needs a single-board endpoint, and
deleting is reversible via git if it's wanted later.

**Files:** `ptos_service.py` (`save_board`, `delete_board`), `ptos_web.py`
(`board_save`, `board_delete` routes).

**Acceptance:** `grep -rn "save_board\|delete_board\|api/board/save\|api/board/delete"`
returns nothing (option a), or returns a template `fetch` call plus the
existing backend (option b).

---

## 2. Test coverage for the board module

**Problem:** No `tests/test_board.py`. Every other module (`test_todo.py`,
`test_records.py`, etc.) has one.

**Add `tests/test_board.py` covering, at minimum:**

- `filter_fields_for_type` — returns `date`, `type`, global fields, and
  type-specific fields (including `required` and `conditions` keys) for a
  known type in a test schema.
- `get_column_field_overlap` — intersection across 2+ types is correct;
  empty list input returns `[]`; single-type input returns that type's full
  field list.
- `get_board_data`:
  - unknown board name raises `PTOSError`
  - board with no `columns` raises `PTOSError`
  - a column type not in `schema.types.allowed` raises `PTOSError`
  - each of the six `time_window` branches (`all`, `this-week`, `last-month`,
    `last-3-months`, `this-year`, default/`this-month`) produces the
    expected `start` date given a fixed "today"
  - `limit` truncates `data[type]` and populates `truncated[type]` with the
    pre-truncation total; `limit=0` returns all records
  - `card_title_fields` normalizes both comma-string and list input; falls
    back to `[]` for other types
- `advance_record`:
  - copies only fields shared between source and target type
  - `target_ctx_fields` overrides shared-field values
  - target type not in schema raises `PTOSError`
  - `missing_required` lists target-type required fields absent from the
    new record
  - source record is unchanged (append-only — no mutation of `old_line`'s
    file position)

**Acceptance:** `pytest tests/test_board.py` passes; coverage includes at
least one negative case (`PTOSError`) per public function in the board
section of `ptos_service.py`.

---

## 3. Boards with no columns fail loudly instead of vanishing

**Problem:** In `save_queries_full`, the boards loop only writes an entry
`if cols:` — a board with an empty `columns` list is silently dropped from
`queries.toml` with no error returned to the caller. A user who clicks
"+ board", names it, and hits Save All before adding 2+ columns loses the
board with no feedback.

**Fix — pick the validation layer:**

- **Backend (preferred):** in `save_queries_full`, raise `PTOSError` for any
  entry in `raw_boards` with an empty `columns` list, same as
  `svc.save_board` already does. This makes bulk-save and single-save
  consistent (relevant regardless of the decision in item 1).
- **Frontend, in addition:** in `query_builder.html`'s `saveAll()`, validate
  `_st.boards` client-side before the POST and show the same kind of inline
  error Query Builder already shows for other invalid entries — avoids a
  round trip for something checkable locally.

**Acceptance:** creating a board, leaving `columns` empty, and clicking Save
All shows a visible error and does not modify `queries.toml`; existing valid
boards in the same save are unaffected.

---

## 4. `advance_record` — avoid the file re-scan for the new record's line number

**Problem:** After `ptos.append_record(new_line)`, `advance_record` reopens
the year's `.log` file, reads all lines, and scans in reverse for
`l.strip() == new_line` to recover `new_lineno`. O(n) per advance, and not
guaranteed-correct if a byte-identical line already exists earlier in the
file (matches the *last* occurrence, which happens to be right for a fresh
append but relies on that coincidence).

**Fix:** Have `append_record` (or a variant) return the file path and line
number it just wrote, and have `advance_record` use that directly instead of
re-deriving it by scanning. If `append_record` is shared by other callers
that don't need the position, add an optional return-position flag or a
thin wrapper rather than changing its existing contract.

**Files:** `ptos.py` (`append_record`), `ptos_service.py`
(`advance_record`).

**Acceptance:** `test_board.py`'s `advance_record` tests still pass;
`advance_record` no longer opens the year file for reading after the
append; behavior unchanged for the missing-required-fields redirect path.

---

## 5. Downgrade or remove the debug logging in `edit_get`/`edit_post`

**Problem:** `app.logger.warning`/`.info` calls were added tracing every
`return_to` decision (external-path rejection, success, no-op). This reads
as scaffolding from chasing the redirect bug rather than logging meant to
run at INFO level on every single edit indefinitely.

**Fix:** Either remove these calls now that the underlying bug (item raised
in the commit itself — `onParentChange`/`editCard` `return_to` handling) is
fixed, or drop them to `app.logger.debug` so they're available when needed
without adding permanent per-request INFO noise.

**Files:** `ptos_web.py` (`edit_get`, `edit_post`).

**Acceptance:** normal edit operations produce no new log lines at the
default log level.

---

## 6. Small cleanups (bundle into whichever of the above touches the same file)

- `advance_record(filepath, ...)`: `filepath` is accepted but never read in
  the function body. Either use it for a path-containment check mirroring
  `edit_post`'s `os.path.abspath(filepath).startswith(os.path.abspath(svc.RECORDS_DIR))`
  guard, or drop the parameter from the signature and the caller
  (`board_advance` route, `board.html`'s `onDrop`).
- `query_builder.html`: `renderBoardColChips` and `renderBoardTitleChips`
  are near-duplicate chip-render/drag-reorder functions. Factor into one
  helper (e.g. `renderChipPicker(elId, selected, available, {onReorder,
  onAdd, onRemove})`) to avoid the two drifting apart on the next board-UI
  change.
- `save_queries_full`: the `isinstance(raw_ctf, list)` / `isinstance(raw_ctf,
  str)` branches both do `entry["card_title_fields"] = raw_ctf` — collapse
  to a single assignment (the `elif` adds nothing).
- `get_board_data`'s `"all"` time window hardcodes
  `start = dt.date(2000, 1, 1)`. Fine today given your ~12 years of history,
  but note it as a constant to revisit if older records are ever backfilled
  — could instead pull the earliest record date from the log directory once,
  or just leave a comment noting the assumption.

---

## Suggested order

1 → 3 → 2 → 4 → 5, with item 6 folded into whichever commit touches each
file first. Item 2 (tests) is easiest to write *after* 1 and 3 land, so the
tests aren't covering code that's about to be deleted or behavior that's
about to change.
