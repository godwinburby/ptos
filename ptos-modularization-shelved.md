# PTOS: Modularization — Shelved Roadmap

## Status: SHELVED (deferred)

Decision: **do not execute the modularization now.** Rationale: it's a large mechanical change with zero immediate user-visible benefit, executed against the project's hard constraint "should not break the currently stable project." The spec and concerns are preserved as the roadmap for when the monolith becomes a real bottleneck or a feature demands touching a cleaner boundary.

**Do not start this work without revisiting this decision.** Reopen when any of these is true:
- `ptos.py` growth becomes a bottleneck you feel while building a feature.
- A feature is painful to fit into the monolith and would be clearly cheaper with a domain module.
- You have dedicated time to do it step-by-step with the mandated discipline.

## Reference docs (both on disk)
- `ptos-modularization-spec.md` — the original plan (facade re-export approach, non-goals, provisional module map, extraction order, verification).
- `ptos-modularization-concerns.md` — the four review concerns (circular imports, thin core, order, `__all__`/surface test) accepted as binding rules.

## Key facts established (do not re-derive)
- `ptos.py`: ~5,411 lines, 184 AST defs / 176 top-level functions, 143 public.
- 114 functions make internal calls to other `ptos.py` defs.
- ~64 functions call across proposed module boundaries.
- **Two guaranteed circular-import cycles** in the spec's provisional boundaries: `records ↔ links` and `records ↔ schema`.

## The plan locked in (when reopened)
1. **Expand `ptos_core.py`** beyond the spec's thin set to own the shared primitives: `find_records_with_location`, `get_schema`, line parsing, glob match, numeric/fmt helpers, `build_record_line`, `_run_base_query`. This breaks both import cycles so every domain module depends only on core — never on each other.
2. **Extraction order (dependency-ordered, replaces spec's intuition list):** core → journal/notes → backup → links → schema → records last.
3. **Per-step verification:** byte-identical diff of moved functions; facade `ptos.foo` resolves; `__all__` on each module; golden-file facade-surface test (`ptos_public_names.txt`) asserting the public surface is unchanged; smoke tests over just-moved module; full suite green before extracting the next; stop/rollback on any behavioral drift.
4. **~69 residual functions** stay in `ptos.py` unmigrated by design.
5. **Execution form:** separate, bisectable pure-move commits — never one big cutover.

## When to do this work safely
- Standalone maintenance time, not mixed into a feature push.
- Step-by-step, one module per verified pass, per the spec's discipline.
