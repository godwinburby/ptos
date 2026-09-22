# SPEC: Scoped config writes (Query Builder + Schema Builder)

**Project:** PTOS
**Decision locked in:** keep one place to *browse* each config type (Query
Builder stays one page listing queries/metrics/dashboards/aliases/due/
boards/habits/calendars/thresholds/projects; Schema Builder stays one page
listing types) — but every individual *save* becomes scoped to the one
entry being changed, following the pattern `save_project()`/
`delete_project()` and `replace_type_fields()` already prove works.

**What this fixes:** every data-loss bug audited this session
(`ec105d0`/`c5905f3`/`c4bbade`'s schema field-resurrection/leakage bugs,
the near-miss on `["project.*"]` being dropped by unrelated saves) traces
to the same root cause — one function reconstructing *many* sections from
partial UI state in a single call, needing a correctly-implemented
"preserve when not given" branch for every section, forever. Scoped writes
eliminate the failure mode structurally: a function that only ever touches
the one key it's told to touch can't drop a section it was never given.

---

## 0. The two working examples this generalizes

Already proven in this codebase, used as the template for everything below
— don't redesign the pattern, copy it:

**`save_project()`/`delete_project()`** (`ptos_service.py`, added in
`bae08cb`): load `queries.toml` whole via `tomllib`, set or delete exactly
one `f"project.{name}"` key, write the whole (now-modified) dict back via
`tomli_w` + `ptos.AtomicWrite`. No `raw_X=None` juggling, because it never
touches anything besides the one key.

**`replace_type_fields()`** (`ptos.py:4324`): same shape for `schema.toml`
— load, mutate one type's `fields`/`required`, write back. Already the
save path for `/types`, already more reliable in this session's own bug
history than the full Schema Builder's `_build_schema_dict()`.

---

## 1. A shared low-level primitive (don't repeat load/mutate/write per section)

New helper in `ptos_service.py`, since every scoped save/delete below does
the identical dance:

```python
def _load_queries_toml():
    """Load queries.toml as a plain dict, {} if missing/unreadable."""
    if not os.path.exists(ptos.QUERIES_PATH):
        return {}
    try:
        with open(ptos.QUERIES_PATH, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}

def _write_queries_toml_key(key, value):
    """Set data[key] = value (or delete if value is None) and write back
    atomically. Touches nothing else in the file."""
    data = _load_queries_toml()
    if value is None:
        if key not in data:
            raise PTOSError(f"'{key}' not found")
        del data[key]
    else:
        data[key] = value
    with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
        tomli_w.dump(data, w.stream)
```

`save_project()`/`delete_project()` can be refactored to call this (or
left as-is and used as the reference — implementer's call, low
importance either way, since they already work correctly).

---

## 2. Scoped functions, one pair per section — TOML key shape confirmed per section

Checked actual `queries.toml` structure before designing this — two
different key shapes exist, matters for how each wrapper is written:

**Dotted-namespace sections** (`metrics.NAME`, `dashboards.NAME`,
`due.NAME`, `board.NAME`, `habit.NAME`, `calendar.NAME`,
`threshold.NAME`, `project.NAME` — confirmed structurally identical,
just different prefix words):

```python
def save_threshold(name, cfg):
    _write_queries_toml_key(f"threshold.{name}", cfg)

def delete_threshold(name):
    _write_queries_toml_key(f"threshold.{name}", None)

# same shape for: save_board/delete_board, save_habit/delete_habit,
# save_calendar/delete_calendar, save_metric/delete_metric,
# save_dashboard/delete_dashboard, save_due/delete_due
# (save_project/delete_project already exist)
```

**Bare-key sections** (plain saved queries, and aliases — confirmed both
live as un-prefixed top-level `[name]` tables, distinguished only by
whether the table contains an `"alias"` key, not by a separate namespace):

```python
_RESERVED_TOP_KEYS = ("metrics", "dashboards")  # existing nested tables
_RESERVED_PREFIXES = ("board.", "habit.", "calendar.", "due.",
                       "threshold.", "project.")

def save_query(name, cfg):
    if name in _RESERVED_TOP_KEYS or name.startswith(_RESERVED_PREFIXES):
        raise PTOSError(f"'{name}' collides with a reserved section name")
    _write_queries_toml_key(name, cfg)

def delete_query(name):
    _write_queries_toml_key(name, None)

def save_alias(name, cfg):
    # same collision guard as save_query — same flat namespace
    if name in _RESERVED_TOP_KEYS or name.startswith(_RESERVED_PREFIXES):
        raise PTOSError(f"'{name}' collides with a reserved section name")
    entry = dict(cfg)
    entry["alias"] = True   # or whatever marks it as an alias today — confirm exact shape against current save_queries_full alias handling
    _write_queries_toml_key(name, entry)

def delete_alias(name):
    _write_queries_toml_key(name, None)
```

Reuse the exact reserved-name/collision-checking logic already in
`save_queries_full()` (the `all_names`/`_is_config_key` validation) rather
than re-deriving it from scratch — copy the existing regex/name checks,
don't invent new ones.

---

## 3. Route changes

### `/query-builder/save` — replace with per-kind endpoints
Current behavior: one endpoint receives the *entire* client-side `_state`
(all nine section types) and calls `save_queries_full()` with everything
at once — this is the literal "Save everything" button. Replace with:

```
POST /api/query-builder/query      { name, cfg }        → save_query
POST /api/query-builder/metric     { name, cfg }        → save_metric
POST /api/query-builder/dashboard  { name, cfg }        → save_dashboard
POST /api/query-builder/alias      { name, cfg }        → save_alias
POST /api/query-builder/due        { name, cfg }        → save_due
POST /api/query-builder/board      { name, cfg }        → save_board
POST /api/query-builder/habit      { name, cfg }        → save_habit
POST /api/query-builder/calendar   { name, cfg }        → save_calendar
POST /api/query-builder/threshold  { name, cfg }        → save_threshold
POST /api/query-builder/project    { name, cfg }        → already exists
```
(Exact URL shape is implementer's call — a single
`POST /api/query-builder/<kind>` with `kind` as a path param, dispatching
to the right `save_X`, is equally valid and less route boilerplate than
ten separate routes — either satisfies this spec.)

Each save action in the UI (editing one threshold, adding one habit) now
POSTs only that one item's data, not the entire page's accumulated state.

### `/query-builder/delete` — drastically simplified
Current behavior: reconstructs `_raw_q()`/`_raw_a()`/`_raw_thr()` from the
*entire* current file state, deletes one item from an in-memory copy, and
re-passes everything through `save_queries_full()` — real work for a
single delete. Replace with:

```python
@app.route("/query-builder/delete", methods=["POST"])
def query_builder_delete():
    data = request.get_json(silent=True) or {}
    name, kind = data.get("name", "").strip(), data.get("kind", "query")
    deleters = {"query": svc.delete_query, "metric": svc.delete_metric,
                "dashboard": svc.delete_dashboard, "alias": svc.delete_alias,
                "threshold": svc.delete_threshold, "board": svc.delete_board,
                "habit": svc.delete_habit, "calendar": svc.delete_calendar,
                "due": svc.delete_due, "project": svc.delete_project}
    try:
        deleters[kind](name)
        return jsonify(ok=True)
    except (KeyError, PTOSError) as e:
        return jsonify(ok=False, error=str(e))
```
One dict dispatch, one scoped call — no whole-file reconstruction.

---

## 4. Query Builder page/JS changes

- **Browsing stays exactly as-is** — one page, all section types listed,
  per the locked decision. No new pages, no new nav entries.
- **What changes**: the client-side `_state` object currently accumulated
  across the whole page and sent wholesale on "Save" no longer needs to
  exist in that form. Each add/edit action (opening a threshold's edit
  form, hitting save on it) posts just that threshold's data to its own
  endpoint from §3, and the page can refresh just that section's rendered
  list — not force a full-page reload/full-state resend for every small
  edit (bonus: this also removes a page's worth of "did I forget to
  include an unrelated section in this save payload" risk on the
  JavaScript side, mirroring the fix on the Python side).
- If a genuine "add many things in one sitting" flow is still wanted
  (e.g. defining five thresholds back to back before navigating away),
  that's still fine — it just means five scoped save calls in sequence,
  not one call bundling all five. The UI doesn't need "unsaved changes"
  tracking across the whole page anymore, since every save is already
  committed the moment it happens.

---

## 5. Schema Builder — smaller change, same principle

`/types` already saves scoped (`replace_type_fields()`) — no change
needed there. The gap is the **full Schema Builder page**
(`_build_schema_dict()`/`svc.save_schema()`), which still reconstructs
every type + global fields + derived fields in one call.

- Per-type edits on the full Schema Builder page should call
  `replace_type_fields()` directly (same function `/types` already uses)
  instead of routing through `_build_schema_dict()`'s full reconstruction.
- Global-level settings (global derived fields, `[fields.*]` metadata,
  `[global_fields.*]`) don't have a scoped save function yet — add one
  (e.g. `save_global_field(name, cfg)` / `save_derived_field(name, expr)`)
  following the same load-whole/touch-one-key/write-back shape, operating
  on `schema.toml` instead of `queries.toml`.
- `_build_schema_dict()` itself: keep it only if something still needs
  "reconstruct the whole schema from scratch" (e.g. a bulk import/restore
  path) — if nothing does once per-type/per-global-setting saves cover
  every UI action, it can be retired. Don't assume retirement without
  checking every current caller first.

---

## 6. What happens to `save_queries_full()`

Once every UI save action routes through the scoped functions in §2, audit
whether anything still needs "write everything at once":

- If nothing does: retire it, or keep it only for a genuinely bulk
  operation (e.g. a future config-import/restore feature) — not as a UI
  write path.
- If it's kept for any reason: it no longer needs to be the *primary*
  write path, which removes the pressure to keep its `raw_X=None`
  preserve-branches perfectly in sync with every new section forever —
  that correctness burden moves to "does this bulk operation need every
  section," a much rarer code path to get right, versus "does every
  single-item edit correctly preserve nine other section types," which is
  what it was doing before.

---

## 7. Non-goals

- No new pages, no new nav entries — browsing stays exactly where it is
  today, per the locked decision at the top of this spec.
- No change to `queries.toml`'s on-disk format/shape for any section —
  this is a write-path refactor, not a data-model change.
- Not touching `ptos.py`'s `schema.toml` structure either — same
  reasoning, write-path only.
- Not building a generic "config CRUD framework" — nine section-specific
  thin wrappers over one shared primitive (§1) is the right amount of
  abstraction; don't over-generalize into something that has to guess
  section shape at runtime.

---

## 8. Tests

1. Each new `save_X`/`delete_X` function: touching one entry leaves every
   other section (including ones it doesn't "know about," like a
   hand-added `["project.*"]` entry) completely untouched — the
   regression test this whole spec exists to guarantee.
2. `save_query`/`save_alias` reject a name colliding with a reserved
   section prefix (`board.foo`, `metrics`, etc.) — same validation
   `save_queries_full()` already has, now enforced per-call instead of
   once at whole-file-save time.
3. `/query-builder/delete` for each `kind` calls the correct scoped
   deleter and doesn't touch unrelated sections.
4. Schema Builder: editing one type via the full builder page produces
   the same `schema.toml` result as editing the same type via `/types`
   directly (both should now go through `replace_type_fields()`).
5. Regression: existing Query Builder / Schema Builder / Types page tests
   still pass after the route/JS changes — behavior from the user's
   perspective (what gets saved, what survives) should be unchanged
   except for the bugs this fixes.

---

## 9. Acceptance criteria

- [ ] Query Builder remains one page; no new nav entries added
- [ ] Every individual save action (one threshold, one habit, one query,
      etc.) calls a scoped `save_X`/`delete_X` function, never
      `save_queries_full()` with a full multi-section payload
- [ ] `/query-builder/delete` no longer reconstructs the whole file state
      to delete one item
- [ ] Editing an unrelated section (e.g. a habit) cannot drop a
      hand-added `["project.*"]`, `["threshold.*"]`, or any other section
      — verified by the test in §8 item 1
- [ ] Schema Builder's per-type edits go through `replace_type_fields()`,
      matching `/types`'s existing (already-correct) behavior
- [ ] `save_queries_full()`/`_build_schema_dict()` are either retired or
      demoted to bulk-only use, not the primary UI write path
- [ ] No change to `queries.toml`/`schema.toml`'s on-disk format
