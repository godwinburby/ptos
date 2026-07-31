# Spec — Board column rollups

## Problem

Board columns currently show a card list and a count (`counts[col_type]`)
in `get_board_data`'s return, but no sum/average — e.g. a "Pending" column
of expense records shows "12 cards" but not "₹4,300 pending."

## Note on reuse

The schema already marks numeric fields with `aggregatable = true` in
`schema.toml` — that's the field-selection metadata this feature needs.
The actual summing, though, should **not** go through `run_metric`/
`_run_base_query` in `ptos.py` — those are CLI-print-oriented, keyed to
named `[metrics]` entries in `queries.toml`, and re-run their own query
against the log files. `get_board_data` has already parsed and filtered
the exact rows it needs (`records` per column) — summing a field over
that list already in memory is a five-line loop, not a call into the
metrics engine. Keep it local to `ptos_service.py`.

## Config

Extend the `[board.NAME]` table in `queries.toml` with an optional
`rollup_field`:

```toml
[board.expenses]
columns = ["pending", "approved", "paid"]
time_window = "this-month"
rollup_field = "amount"
rollup_op = "sum"   # "sum" | "avg" | "count" — default "count" if rollup_field unset
```

- `rollup_field` must be a field marked `aggregatable = true` somewhere in
  the schema (validate at save time in `save_queries_full`, same place
  `columns` is validated against `schema.types.allowed`) — reject with a
  clear `PTOSError` if the field isn't aggregatable for at least one of
  the board's column types, since a rollup on a non-numeric field would
  silently produce garbage.
- If a column's type doesn't have `rollup_field` in its own field list
  (fields differ per type), skip that column's rollup — show count only
  for that column, not an error. Boards routinely mix types with
  different fields (that's what `overlap` already handles for the shared
  title-field picker).

## Backend — `get_board_data`

In the existing per-column loop in `ptos_service.py`, after `records` is
built and before truncation:

```python
rollup_field = cfg.get("rollup_field")
rollup_op = cfg.get("rollup_op", "count")
rollup_by_type = {}
...
for col_type in columns:
    ...
    if rollup_field and rollup_field in field_info[col_type]:
        vals = []
        for r in records:  # pre-truncation, full matched set
            raw = r.get(rollup_field)
            try:
                vals.append(float(raw))
            except (TypeError, ValueError):
                continue
        if rollup_op == "sum":
            rollup_by_type[col_type] = sum(vals)
        elif rollup_op == "avg":
            rollup_by_type[col_type] = (sum(vals) / len(vals)) if vals else None
        else:
            rollup_by_type[col_type] = len(vals)
    else:
        rollup_by_type[col_type] = None
```

- **Compute over the full matched set, before `limit` truncation** — a
  rollup that only reflects the visible (possibly truncated) cards would
  be misleading. `total_by_type`/`truncated_by_type` already track the
  distinction between visible and total; rollups follow `total`.
- Non-numeric or missing field values are skipped, not treated as zero —
  avoids silently deflating an average.
- Add `"rollups": rollup_by_type` to the function's return dict.

## Frontend

- `board.html`: column header currently shows type name + count. Add the
  rollup value next to the count when `rollups[col_type]` is not `None` —
  e.g. `Pending (12 · ₹4,300)` for sum, `Pending (12 · avg ₹358)` for avg.
  No currency symbol assumption baked into the backend — format is a
  frontend concern; backend returns a plain number.
- `query_builder.html` board editor: add a `rollup_field` dropdown
  (populated from `overlap` — only fields common to all selected columns,
  since a field only present on one column type would need per-column
  handling in the picker UI, and that's more complexity than v1 needs)
  and a `rollup_op` select (`count` / `sum` / `avg`). Leaving
  `rollup_field` unset keeps current count-only behavior — fully
  backward compatible with existing `[board.*]` configs.

## Testing

Extend `tests/test_board.py` (from the earlier board test-coverage spec —
write these alongside those, not as a separate pass):
- `rollup_field` unset → `rollups[type]` is `None` for all columns,
  existing behavior unchanged
- `rollup_op = "sum"` sums correctly across matched (pre-truncation)
  records, ignoring non-numeric values
- `rollup_op = "avg"` divides correctly; empty column → `None`, not
  `ZeroDivisionError`
- `rollup_field` valid for one column's type but absent from another's →
  that column's rollup is `None`, no error raised
- `save_queries_full` rejects a `rollup_field` that isn't `aggregatable`
  for any of the board's column types

## Acceptance

- An expense board with `rollup_field = "amount"`, `rollup_op = "sum"`
  shows a correct per-column total that matches manually summing the
  same month's records.
- Existing boards with no `rollup_field` render identically to before —
  no visual or data change.
- Query Builder board editor lets you add/change/remove a rollup without
  touching `queries.toml` by hand.
