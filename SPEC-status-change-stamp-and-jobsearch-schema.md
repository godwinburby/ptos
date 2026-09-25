# SPEC: Status-change timestamp stamping (status boards) + jobsearch schema

**Project:** PTOS
**Two deliverables:** (1) a generic `stamp_field` board config option so any
status board can record "when did this last move," not just jobsearch —
built as a config-driven engine feature, not hardcoded to one type's field
name; (2) the corrected `jobsearch` schema from the last two messages.

---

## 1. Why this is a board-config feature, not a jobsearch-specific one

Confirmed by reading `move_record()`/`board_move_record()`
(`ptos_service.py:3313`/`3340`): `move_record()` calls
`ptos.apply_set(old_line, [f"{field}={value}"], None)` — a single
`field=value` pair, hardcoded to just the board's `set_field`. The gap
this spec closes — no record of *when* a status changed — isn't unique to
jobsearch; any status board (present or future) has the same problem.
Hardcoding `status_changed` into the engine would put domain knowledge
("jobsearch has a field called status_changed") into `ptos.py`/
`ptos_service.py`, which is exactly what the schema-driven design avoids
everywhere else. So: a new **optional board config key**, and the engine
stays ignorant of what field name it's stamping or why.

---

## 2. Config addition

New optional key on any `["board.NAME"]` status board:

```toml
["board.jobsearch"]
set_field = "status"
stamp_field = "status_changed"     # NEW — optional
columns = [ ... ]
```

- `stamp_field` names a field to set to today's date whenever a card
  moves, alongside `set_field`. Optional — a status board with no
  `stamp_field` behaves exactly as it does today (unchanged).
- No validation coupling to a specific type's schema fields — same as
  `set_field` itself, the board config doesn't check that
  `stamp_field` is declared in `schema.toml`; if it's misspelled or
  missing from the type's schema, the value still gets written to the
  record line (consistent with how PTOS records already tolerate
  fields not formally declared per-type — worth confirming this
  matches existing tolerance elsewhere rather than assuming).

---

## 3. Engine change — `move_record()`/`board_move_record()`

```python
def move_record(filepath, old_line, field, value, lineno=None,
                 stamp_field=None, stamp_value=None):
    """... existing docstring ...
    stamp_field/stamp_value: optional second field=value to set in the
    same operation (e.g. a 'last moved' timestamp) — applied atomically
    alongside the primary field change, not as a separate write."""
    set_args = [f"{field}={value}"]
    if stamp_field:
        set_args.append(f"{stamp_field}={stamp_value}")
    try:
        new_line, _ = ptos.apply_set(old_line, set_args, None)
    except SystemExit as e:
        raise PTOSError(str(e))
    except Exception as e:
        raise PTOSError(str(e))
    ...  # rest unchanged
```

```python
def board_move_record(board_name, filepath, old_line, lineno, target_lane):
    ...  # existing set_field/lane resolution unchanged
    stamp_field = cfg.get("stamp_field")
    stamp_value = ptos.today_str() if stamp_field else None  # confirm exact "today as string" helper already used elsewhere in ptos.py — reuse it, don't reformat a date independently here
    return move_record(filepath, old_line, set_field, target["set_value"],
                        lineno=lineno, stamp_field=stamp_field, stamp_value=stamp_value)
```

**One atomic write, not two** — both fields land in the same
`apply_set()` call and the same `_update_record_in_file()` write, so a
crash mid-operation can't leave `status` updated but `status_changed`
stale (or vice versa). This matters precisely because it's the kind of
partial-write risk the earlier restore/backup audit was about — worth
being deliberate about it here even though the write itself is small.

**What doesn't change**: boards with no `stamp_field` configured behave
identically to today — `stamp_field=None` short-circuits to the existing
single-field `apply_set()` call.

---

## 4. Effect on Project Drift Review's board-stall signal

Once `stamp_field` is configured for `jobsearch`, the board-stall
computation (`get_board_data()`'s per-column oldest-record-age, consumed
by Project Drift Review) should read `stamp_field`'s value instead of the
record's leading date, **when a board defines one** — otherwise it keeps
using the record date exactly as it does today for boards without a
`stamp_field` (like `client_sale_journey`, where the record date is
already correct and meaningful).

- [ ] `get_board_data()`/Project Drift Review's stall calculation checks
      for `stamp_field` on the board config; if present, ages are
      computed from that field's value per record instead of the
      record's own date
- [ ] Boards without `stamp_field` are completely unaffected — this is
      additive, not a change to existing stall-calculation behavior

---

## 5. Updated `jobsearch` schema

Corrected from the last message: `next_followup`/`phone` need **no**
per-type field declaration at all — confirmed by reading
`get_global_fields()` (`ptos.py:1359`), `[global_fields.*]` entries apply
automatically to every type. `use = "shared.X"` is only for the
`[shared.*]` table (confirmed via `apply_set`'s/schema-loading code's
`"shared."` prefix handling) — there is no `use = "global"` mechanism, and
none is needed since global fields don't require opting in per type. This
is simpler than what I gave you last message, not just corrected.

```toml
[type.jobsearch]
required = ["company", "status", "source"]

[type.jobsearch.fields.company]
type = "string"
aggregatable = false
dimension = false

[type.jobsearch.fields.role]
type = "string"
aggregatable = false
dimension = true

[type.jobsearch.fields.status]
type = "string"
options = ["lead", "applied", "interview", "offer", "hired", "rejected"]
aggregatable = false
dimension = true

[type.jobsearch.fields.status_changed]
type = "datetime"
aggregatable = false
dimension = true

[type.jobsearch.fields.source]
type = "string"
options = ["linkedin", "referral", "company_site", "recruiter", "naukri", "walkin", "other"]
aggregatable = false
dimension = true

[type.jobsearch.fields.offer_amount]
type = "int"
aggregatable = true
dimension = false

[type.jobsearch.fields.rejection_reason]
type = "string"
options = ["no_response", "not_qualified", "position_filled", "salary_mismatch",
           "rejected_offer", "withdrew", "other"]
aggregatable = false
dimension = true

[type.jobsearch.conditions.rejection_reason]
when = { status = "rejected" }

[type.jobsearch.fields.url]
type = "string"
aggregatable = false
dimension = false

[type.jobsearch.derived_fields]
```

- `next_followup` and `phone` are **not** declared here — they apply
  automatically as global fields, exactly like every other type in your
  schema already benefits from without a per-type declaration.
- `status_changed` declared as `datetime` so it renders/sorts like your
  other datetime fields (`next_followup` at the global level, `test` at
  the field-metadata level) — consistent typing, not a bare string.
- Matching board config addition (from §2):
```toml
["board.jobsearch"]
set_field = "status"
stamp_field = "status_changed"
columns = [
    { label = "Lead", where = "type=jobsearch AND status=lead" },
    { label = "Applied", where = "type=jobsearch AND status=applied" },
    { label = "Interview", where = "type=jobsearch AND status=interview" },
    { label = "Offer", where = "type=jobsearch AND status=offer" },
    { label = "Hired", where = "type=jobsearch AND status=hired" },
    { label = "Rejected", where = "type=jobsearch AND status=rejected" },
]
time_window = "tm"
limit = 100
card_title_fields = ["company", "role"]
```

---

## 6. Still your call, not decided here

From the last message, unresolved: work mode/location field, and whether
you want a separate salary-expectation field alongside `offer_amount`.
Not included above — add them the same way as any other field once
you've decided, no engine change needed for either (both are plain
schema fields, not board/engine behavior).

---

## 7. Tests

1. A status board with `stamp_field` set: moving a card updates both the
   set field and the stamp field in one write, verified by re-reading the
   record line after the move.
2. A status board with no `stamp_field`: behavior identical to before
   this change — single-field write only.
3. `move_record()` called directly with `stamp_field=None` (default)
   matches its exact pre-change behavior — regression test.
4. A crash/exception simulated mid-`apply_set()` (both fields being set
   together) doesn't leave a partially-updated record — since it's one
   `apply_set()` call producing one new line before any write happens,
   this should hold structurally, but worth a test asserting the file's
   old line is unchanged if the set step raises before
   `_update_record_in_file()` is reached.
5. Project Drift Review's board-stall signal for a `stamp_field`-configured
   board uses that field's value, not the record's leading date; a board
   without `stamp_field` is unaffected (regression).
6. Schema: `rejection_reason` is enforced as required only when
   `status=rejected` (via the `conditions`/`when` mechanism) — a record
   with `status=applied` and no `rejection_reason` validates fine; one
   with `status=rejected` and no `rejection_reason` fails validation.

---

## 8. Acceptance criteria

- [ ] `stamp_field` is a board-config-only concept — no hardcoded field
      name anywhere in `ptos.py`/`ptos_service.py`
- [ ] Moving a card on a `stamp_field`-configured board updates both
      fields in one atomic write
- [ ] Boards without `stamp_field` are completely unaffected
- [ ] Project Drift Review board-stall reads `stamp_field` when present,
      falls back to record date otherwise
- [ ] `jobsearch` schema matches §5 exactly, including the corrected
      (no `use`) handling of global fields
- [ ] `rejection_reason` is conditionally required only when
      `status=rejected`, via existing `conditions`/`when`, not a new
      validation mechanism
