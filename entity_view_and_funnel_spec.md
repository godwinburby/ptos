# Entity View + Pipeline Funnel Metric — Spec

Source: review of a "join" proposal from another AI. Two of its three proposed
features already exist via the current filter/group engine (verified against
`browse_run()` and the README's OR-value/group syntax) — this spec covers only
the genuine gap (funnel conversion) plus a thin dedicated page for the
already-existing cross-type filter capability, so it's actually discoverable
instead of buried as "type an unusual filter in Browse."

**No new join primitive, no new storage, no SQLite.** Both features are built
entirely on existing engine functions (`get_records`, `get_board_data`) — this
is a UI/aggregation layer on top of what already works, not new query
machinery.

---

## 0. What's already there (context, not part of the build)

Confirmed by reading the actual filter path (`browse_run()` in `ptos_web.py`):
`filters` passed to `svc.get_records()` carry no type restriction — a WHERE
expression like `client_code=vka7` matches against any record's parsed
fields regardless of `type=`. Combined with "All time" and existing sort,
Browse already returns every record of any type sharing a field value,
sorted by date. Cross-type grouping (`type=a|b --group field`) works the same
way via the existing OR-value syntax. Neither of these needs new engine code —
they're existing capabilities that are hard to discover because nothing
surfaces "filter without picking a type" as an obvious workflow.

---

## 1. Entity View page

A dedicated page that makes the existing cross-type filter capability
obvious and convenient, rather than something you stumble into by knowing to
leave the type selector blank in Browse.

### Behavior
- New page (e.g. `/entity`) — one input: a field name and value (or a single
  free-text `field=value` box, matching the existing filter syntax so no new
  parsing is needed).
- Under the hood: calls `svc.get_records([f"{field}={value}"], "all", sort="date")`
  — the exact same call Browse would make with no type selected. No new
  service function required; this page is a thin wrapper.
- Renders results as one sorted table across all matched types, using the
  existing `RecordTable` component (same one Home/Browse/Board already use)
  so edit/delete/convert all work identically — no new row-rendering logic.
- Optional convenience: remember the last few field names used (e.g.
  `client_code`, `project`) as quick-pick chips, sourced from schema's
  `linkable` fields (the same field list `get_linkable_fields()` already
  provides for backlinks) — not a new concept, reusing the existing
  `linkable` flag.

### Non-goals for this feature
- No new filter syntax — reuses exactly what WHERE expressions already
  support.
- No entity "profile" beyond the record table itself (no computed summary
  card, no cross-type schema merging) — that's speculative scope the actual
  ask doesn't require. If a summary view is wanted later, that's a separate
  spec built on top of this once the plain table view has been used for a
  while.
- Does not change Browse — Browse keeps working exactly as it does today;
  this is an additional, friendlier entry point to the same capability, not
  a replacement.

### Acceptance criteria
- Entering `client_code=vka7` (or any linkable field) returns every record
  of any type where that field matches, sorted by date, using the existing
  `RecordTable` component.
- Edit/delete/convert on a row from this page behaves identically to the
  same row shown on Browse (same component, so this should be automatic —
  call out as a check, not a new implementation).
- No change in behavior to `/browse`, `get_records`, or any existing route.

---

## 2. Pipeline funnel metric

The one genuine gap: "of N assessed, how many prescribed, how many fitted"
— a stage-to-stage conversion count. Built as an aggregation on top of the
Board's existing `match_field` data, not a new cross-type mechanism.

### Why this reuses Board data
`get_board_data(board_name, ...)` already returns, per column (type), the
list of records in that column — and when `match_field` is configured, the
existing Client Grid view already computes which matched-value rows have a
card in which columns. A funnel is just: for each column in board-defined
order, count how many distinct `match_field` values have **at least one**
record in that column (and, for strict funnel semantics, in every column
before it too — see the two variants below). No new scanning, no new
service primitive for gathering the underlying records — only a new
counting step over data `get_board_data()` already assembled.

### Config
New optional section in `queries.toml`, following the same pattern as
`["threshold.NAME"]`:

```toml
["funnel.job_pipeline"]
board = "job_search"          # must be a board with match_field set
stages = ["applied", "phone_screen", "interview", "offer"]  # column order
time_window = "this-quarter"  # optional — falls back to board's config window
```

`stages` lets the funnel show a subset or reordering of the board's columns
if not all columns represent a meaningful pipeline stage (e.g. a "rejected"
column shouldn't count toward "made it through").

### Two counting variants — pick one, don't build both speculatively
- **Cumulative** (strict funnel): count of matched values present in stage N
  **and every stage before it**. This is the "how many made it all the way
  through" reading — a client with a card in `interview` but who skipped
  `phone_screen` (data entered out of order) would not count at `phone_screen`.
- **Reached** (loosest): count of matched values present in stage N,
  regardless of earlier stages. Simpler, and tolerant of data entered out of
  strict order (which happens — see the earlier CRM `outcome` field
  discussions).

Recommendation: build **Reached** first — it's simpler, matches how you
actually enter records (not always in strict pipeline order), and avoids
silently hiding a real data point (someone fitted without a logged
assessment still shows up at the fitting stage, which is more honest than
making them invisible because an earlier stage's record is missing).
Cumulative can be added later as an explicit option if the strict reading
turns out to matter.

### Page/display
- A new small section (not a full page) — could live on the Board page
  itself as a header strip above the Kanban/Grid view when `match_field` is
  set, or on `/queries` as another query-like item alongside metrics. Your
  call on placement; both reuse the existing `get_board_data()` call
  already made when rendering that board, so neither requires an extra
  fetch.
- Display: a simple stage → count table (`applied: 47 → phone_screen: 22 →
  interview: 9 → offer: 3`), optionally with conversion % between adjacent
  stages. No visual funnel-shape rendering required for v1 — the numbers are
  the value, not the chart.

### Non-goals
- Not a generalized cross-type join engine — this only works for
  board-backed pipelines with `match_field` already configured, which is
  the existing pattern for "linked entity across types."
- No new engine function in `ptos.py` — purely a `ptos_service.py`
  aggregation function operating on `get_board_data()`'s existing return
  value.
- No time-series funnel history (funnel-over-time trend) — this spec is a
  point-in-time count for the board's current/configured window, matching
  how Board itself works today.

### Acceptance criteria
- `["funnel.NAME"]` config validates: `board` must reference an existing
  board with `match_field` set (reject with a clear error otherwise — a
  funnel with no `match_field` has no shared identity to count against).
- Stage counts match manually counting Client Grid rows with a card in each
  named column, for the same board/window — i.e. numbers should be
  independently verifiable against the existing grid view, not a new
  source of truth that could silently diverge from what Board already shows.
- No change to existing Board behavior (Kanban view, Client Grid view,
  drag-and-drop) — funnel is purely additive.

---

## 3. What's deliberately not being built

- No dedicated "join" query type in `queries.toml` — both features route
  through existing `get_records`/`get_board_data`, keeping the "engine has
  no domain logic" principle intact (a join concept would be new domain
  logic in the engine; these two features are not).
- No SQLite, no new indexing layer — confirmed unnecessary at this data
  volume in the earlier performance discussion, and neither feature here
  changes that calculus (both are single-pass reads over already-cached
  data paths).
- No automatic surfacing of "which fields make good entity keys" — the
  person picks the field to filter by (Entity View) or configures
  `match_field`/`stages` explicitly (funnel), consistent with the schema
  being config-driven rather than the engine guessing at meaning.
