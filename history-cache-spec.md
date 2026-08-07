# Spec — Cache `get_history_suggestions` / `get_conditional_suggestions`

## Problem

Both functions do a full, unbounded `ptos.scan_records(date.min, date.max, ...)`
over every record ever logged of a given type, with no cache and no date
bound:

- `get_history_suggestions(rtype, context_record)` — called on every
  add/edit page load, and again on every cascade parent-field change
  (`ptos_web.py` line 2529's URL-param reload path).
- `get_conditional_suggestions(rtype, field, value)` — behind
  `/api/field_suggest/<rtype>/<field>/<value>`, called live via AJAX
  **on every cascade selection** — this is the one most directly felt as
  "cascade fill is slow," since it's a fresh full scan per click, not
  per page load.

Cost grows linearly with total history logged for that type, forever.

## Fix — reuse the existing cache infrastructure

`ptos.py` already has a generic cache (`_CACHE` dict + `_invalidate(resource)`
+ `_CACHE_DEPS`), currently used only for TOML config files (`schema`,
`queries`, `config`, `presets`). Extend the same mechanism rather than
building a new caching layer.

### 1. Cache keys

- `get_history_suggestions(rtype, context_record)` — cache key:
  `f"history:{rtype}"`. **Do not include `context_record` in the cache
  key** — the expensive part is the full scan and `tags_by_field_value`
  build; the `filtered_tags` computation from `context_record` at the
  end of the function is cheap (set lookups on already-built data), so
  cache the scan result and re-run only the cheap filtering step per call:

```python
def get_history_suggestions(rtype, context_record=None):
    cache_key = f"history:{rtype}"
    cached = ptos._CACHE.get(cache_key)
    if cached is None:
        cached = _build_history_suggestions(rtype)  # existing scan logic, minus context filtering
        ptos._CACHE[cache_key] = cached
    return _apply_context_filter(cached, context_record)  # existing filtered_tags logic
```

  Split the current function into the expensive scan-and-aggregate part
  (cached) and the cheap context-filter part (run fresh every call, since
  `context_record` varies per request and is cheap once `tags_by_field_value`
  is already built).

- `get_conditional_suggestions(rtype, field, value)` — cache key:
  `f"condsug:{rtype}:{field}:{value}"`. This one's fully cacheable as-is,
  no per-call variable part — cache the whole return dict.

### 2. Invalidation

Add `ptos._invalidate([f"history:{rtype}", ...])`-style calls (or a
broader `records` bucket if simpler — see below) at every record-mutating
function in `ptos_service.py`:

- `append_record(line)`
- `edit_record(filepath, old_line, set_args, new_note, lineno)`
- `delete_record(filepath, old_line, lineno)`
- `advance_record(old_line, lineno, target_type, target_ctx_fields)`

**Simplest correct approach:** since `condsug:*` keys are per-`(rtype,
field, value)` and there could be many live at once, don't try to
selectively invalidate individual `condsug` keys — invalidate **all**
`history:*` and `condsug:*` keys on any record write, regardless of
which `rtype` changed. Add a helper:

```python
def _invalidate_history_cache():
    for key in list(ptos._CACHE.keys()):
        if key.startswith("history:") or key.startswith("condsug:"):
            ptos._CACHE.pop(key, None)
```

Call `_invalidate_history_cache()` at the end of each of the four
functions above, after the write succeeds. Correctness over precision —
a record write is already a relatively rare event compared to reads
(cascade fills happen many times per record actually saved), so
over-invalidating costs nothing meaningful and avoids the bug class of
"only invalidated `history:expense` but the write actually also affected
a `condsug:expense:*` key."

### 3. Bonus: bound the scan window too

Independent of caching, `date.min`→`date.max` is wider than these
suggestions need — "the usual next value" rarely benefits from data more
than a couple years old, and bounding the scan shrinks the cost of the
*first* call after each invalidation (the cache miss), not just steady
state. Add an optional lookback:

```python
lookback_years = 2  # tune to taste; None keeps current unbounded behavior
start = dt.date.min if lookback_years is None else dt.date(dt.date.today().year - lookback_years, 1, 1)
raw, _ = ptos.scan_records(start, dt.date.max, [f"type={rtype}"], None)
```

This is a smaller win than caching (caching removes the cost on every
call after the first; bounding only shrinks the cost of that first
call), but worth doing together since it's a one-line change in the same
function.

## Testing

Extend existing service-layer tests (or add `tests/test_history_cache.py`):
- two consecutive `get_history_suggestions(rtype)` calls with no writes
  in between — second call returns identical data without re-scanning
  (assert via monkeypatching `ptos.scan_records` to raise if called
  twice, or a call-counter)
- `append_record` for `rtype` invalidates the cache — a suggestion call
  after the write reflects the new record's field values
- `edit_record` / `delete_record` / `advance_record` each invalidate too
  — one test per function is enough, don't need the full matrix
- `get_conditional_suggestions` cache hit returns identical dict across
  calls with no intervening write
- context-filtering still varies correctly per `context_record` even
  though the underlying scan result is now shared/cached (this is the
  regression test for the cache-key-excludes-context design decision)

## Acceptance

- Selecting a cascade parent field value no longer triggers a full file
  scan if nothing has been written since the last time that `rtype` was
  scanned — `/api/field_suggest` responses should be near-instant on
  repeat selections.
- Adding, editing, deleting, or advancing any record immediately
  invalidates suggestions for all types (simple, correct, slightly
  coarse — matches the "correctness over precision" call above) so
  suggestions never go stale.
- No change to what suggestions are returned — this is a performance fix,
  not a behavior change. (The optional lookback bound is the one place
  behavior could shift — flag it as opt-in / off by default if you want
  zero behavior change, or on by default if you're fine with "usual
  value" suggestions no longer being influenced by decade-old records.)
