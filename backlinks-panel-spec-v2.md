# Spec — Backlinks / "Linked Mentions" panel (v2 — schema-driven field linking)

Supersedes the earlier draft. This version replaces the hardcoded
`project`/`context` field assumption with a schema-driven `linkable` flag,
matching the pattern already used for `aggregatable` (rollups).

## Problem

`[[name]]` references already work across notes, journal, todo, and are
autocompleted via `/api/link-candidates`. That endpoint also scans records
for `project=`/`context=` key-values — but those two field names are
hardcoded into a regex in `ptos_web.py` (`_kv_re = re.compile(r'\b(project|context)=(\S+)')`),
which is domain knowledge baked into the engine layer, not schema-driven
like the rest of PTOS. There's also still no reverse view: nothing shows
what references a given note/project/record field value.

## Goal

1. Fix the existing hardcoding: which fields count as "linkable" becomes
   schema metadata, not an engine-level regex of specific field names.
2. Add a read-only backlinks panel that, given a subject, shows every
   `[[bracket]]` reference and every `linkable` field match across
   notes/journal/todo/records.

## Schema change

Add an optional `linkable = true` flag to field metadata, same shape as
`aggregatable`:

```toml
[global_fields.project]
type     = "string"
linkable = true

[global_fields.context]
type     = "string"
linkable = true

# type-specific example, e.g. in a clinic schema:
[type.assessment.fields.patient]
type     = "string"
linkable = true
```

- Defaults to `false`/unset if not specified — a field must opt in.
- Starter schema (`starters/starter_schema.toml`) ships `project` and
  `context` as `linkable = true`, preserving today's behavior exactly —
  no behavior change for existing installs on upgrade.
- Add a schema helper, e.g. `ptos.get_linkable_fields()` → returns the set
  of field names (global + per-type) marked `linkable`, so both
  `link-candidates` and `get_backlinks` derive the field list from schema
  instead of each hardcoding their own regex.

## Backend changes

**1. Fix `api_link_candidates` (`ptos_web.py`):**
Replace the hardcoded `_kv_re = re.compile(r'\b(project|context)=(\S+)')`
with a regex built from `ptos.get_linkable_fields()` at request time (or
cached with the same invalidation the rest of schema-derived state uses):

```python
linkable = ptos.get_linkable_fields()
if linkable:
    _kv_re = re.compile(r'\b(' + '|'.join(re.escape(f) for f in linkable) + r')=(\S+)')
```

No change to bracket scanning — `[[...]]` stays universal, unconditional,
same as today.

**2. New `get_backlinks(subject)` in `ptos_service.py`:**

```python
def get_backlinks(subject: str) -> dict:
    """
    Returns:
    {
      "notes":   [{"category": str, "slug": str, "title": str, "path": str, "snippet": str}, ...],
      "journal": [{"date": str, "path": str, "snippet": str}, ...],
      "todo":    [{"line": str, "lineno": int, "done": bool}, ...],
      "records": [{"date": str, "type": str, "field": str, "path": str, "lineno": int, "snippet": str}, ...],
    }
    """
```

- Case-insensitive exact match on `subject`, same normalization
  `link-candidates` already uses.
- Bracket matches: any `[[subject]]` in notes/journal/todo (unconditional).
- Field matches: any record where a `linkable`-flagged field equals
  `subject`, plus todo `project:`/`context:` prefix values when those
  fields are linkable.
- **Factor the shared scan logic** — `link-candidates` and `get_backlinks`
  should call one internal helper for "walk notes/journal/todo/records,
  apply bracket regex + linkable-field regex, collect matches" so the two
  can't drift out of sync. `link-candidates` collects *unique candidate
  strings*; `get_backlinks` collects *locations for one specific subject*
  — same underlying scan, different aggregation on top.
- Include a short snippet (~60 chars around the match) per hit.

**3. New route:**

```python
@app.route("/api/backlinks")
def api_backlinks():
    subject = request.args.get("q", "")
    if not subject:
        return jsonify({"notes": [], "journal": [], "todo": [], "records": []})
    return jsonify(svc.get_backlinks(subject))
```

## Frontend

- Reusable panel (vanilla JS, matching `base.html`'s existing shared
  helpers — no new framework) that fetches `/api/backlinks?q=...` and
  renders four collapsible groups, each item linking to its source
  (note edit URL, journal date, todo line via existing highlight/scroll,
  record via `browse`/`edit` with `filepath`+`lineno`).
- Shows nothing if all four groups are empty — no clutter on
  unreferenced notes/records.
- **Where it appears in v1:**
  - `notes.html` (individual note view) — keyed on note title.
  - Skip `journal.html`, `add.html`, `edit.html`, `board.html` in v1 —
    confirm with Godwin whether journal entries are actually referenced
    via `[[date]]` in practice before adding it there.

## Query Builder / Schema Builder UI

Wherever field metadata is currently edited (schema builder or the raw
`schema.toml` editor), a `linkable` checkbox should sit next to wherever
`aggregatable` is already exposed, for the same reason `aggregatable` is
exposed there — this is user-facing schema config, not something that
should only be settable by hand-editing TOML.

## Explicitly out of scope for v1

- No graph/visual view — list only.
- No fuzzy/partial matching.
- No live-updating panel (SSE) — loads once per page load.
- No backlinks from arbitrary free-text substrings — only `[[bracket]]`
  spans and `linkable`-flagged field values.

## Testing

`tests/test_backlinks.py`:
- `[[Subject]]` in a note found when querying `"subject"` (case-insensitive)
- a `linkable`-flagged field match (e.g. `project=Subject`) found under
  `records`; a **non**-linkable field with the same value is NOT found
  (this is the key regression test for the hardcoding fix)
- starter schema's `project`/`context` still resolve as linkable by
  default (upgrade-safety check)
- a todo line with `project:Subject` found under `todo` when `project`
  is linkable
- subject with no references anywhere returns all-empty dict
- snippet extraction doesn't crash on a match at the very start/end of a
  file's content

Also extend `tests/test_link_candidates.py` (or add it if it doesn't
exist) to confirm `link-candidates` now derives its field set from
`ptos.get_linkable_fields()` rather than a fixed `project|context` regex —
add a `linkable = true` field to a test schema that isn't `project` or
`context` and confirm it's picked up.

## Acceptance

- A note referenced by another note, a todo item, and a linkable-field
  record shows all three under the correct groups, each clickable.
- An unreferenced note shows no panel.
- Marking a field `linkable = true` in schema makes it backlink-searchable
  with zero code changes — no field-name edits anywhere in
  `ptos_web.py`/`ptos_service.py`.
- `get_backlinks` and `api_link_candidates` share one scanning helper —
  no duplicated glob/regex code between them.
