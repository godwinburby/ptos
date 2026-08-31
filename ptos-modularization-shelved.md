# PTOS: Modularization — Shelved Roadmap

## Status: SHELVED (deferred)

Decision: **do not execute the modularization now.** Rationale: it's a large mechanical change with zero immediate user-visible benefit, executed against the project's hard constraint "should not break the currently stable project." The spec and concerns are preserved as the roadmap for when the monolith becomes a real bottleneck or a feature demands touching a cleaner boundary.

A second, stronger reason surfaced after shelving and is now folded into the spec itself: **single-file CLI portability**. `ptos_cli.py` imports only `ptos` (+ stdlib), so a CLI-only user runs the full engine from exactly two files (`ptos.py` + `ptos_cli.py`) with no install step and no dependency tree. A naive split into `ptos_core.py`/`ptos_records.py`/etc. would **break that property** by requiring the whole module directory. Any future extraction must include an amalgamation/reassembly step (SQLite-amalgamation model) to preserve "copy two files, run anywhere" — meaning the split is *two-way* work, not just readability.

**Do not start this work without revisiting this decision.** Reopen when any of these is true:
- `ptos.py` growth becomes a bottleneck you feel while building a feature.
- A feature is painful to fit into the monolith and would be clearly cheaper with a domain module.
- You have dedicated time to do it step-by-step with the mandated discipline.

## Reference docs (all on disk)
- `ptos-modularization-spec.md` — the plan (facade re-export, non-goals, shared-substrate layer, graph-derived order, `__all__`/surface check, verification). **Revised:** now incorporates all four concerns from the review pass and the single-file portability constraint.
- `ptos-modularization-concerns.md` — the four review concerns (circular imports, thin core, graph-derived order, `__all__`/surface test) accepted as binding rules.

## Key facts established (do not re-derive)
- `ptos.py`: ~5,411 lines, 184 AST defs / 176 top-level functions, 143 public.
- 114 functions make internal calls to other `ptos.py` defs.
- ~64 functions call across proposed module boundaries.
- **Two guaranteed circular-import cycles** in the spec's original provisional boundaries: `records ↔ links` and `records ↔ schema` — resolved structurally by the expanded shared layer (no domain module imports another domain module).
- **CLI portability constraint:** `ptos_cli.py` imports only `ptos` + stdlib; a split must preserve the two-file portable distribution via a reassembly step, or the split is incomplete.

## The plan locked in (when reopened)
1. **Expand the shared substrate layer** (the spec now calls `ptos_core.py`, possibly split with a `ptos_parse.py` sibling) below every domain module to own the cross-cutting primitives: `find_records_with_location`, `get_schema`, line parsing, glob match, numeric/fmt helpers, `build_record_line`, `_run_base_query`, `filters_to_expr`. This breaks both import cycles so no domain module ever imports another domain module directly. **Default when unsure whether a helper belongs in a domain or the shared layer: put it in the shared layer** — a slightly-too-large shared layer is safer than a hidden cross-module dependency.
2. **Extraction order derived from Step-0's graph** (reverse-topological, risk-intuition as tie-break only): shared substrate first (by construction nothing above it), then domain modules per the graph. The exact sequence is not knowable until the graph exists; do not pre-commit to a fixed order.
3. **Per-step verification:** byte-identical diff of moved functions; facade `ptos.foo` resolves; **circular-import confirmation at runtime** (the `ImportError: cannot import name` failure only shows at import, not in a diff); `__all__` on each module; golden-file facade-surface test (`ptos_public_names.txt`) asserting the public surface is unchanged; smoke tests over just-moved module; full suite green before extracting the next; stop/rollback on any behavioral drift.
4. **~69 residual functions** stay in `ptos.py` unmigrated by design.
5. **Execution form:** separate, bisectable pure-move commits — never one big cutover.

## Open design gaps to resolve before ANY execution begins
These are the remaining holes the current spec acknowledges but does not close. They must be answered in Step 0 or a dedicated build-step spec, not discovered mid-extraction:
1. **Amalgamation/build-step design (the critical one).** How is the shipped single-file `ptos.py` generated from the split modules (concatenation vs. a bundler)? How do we guarantee the merged file is behaviorally equivalent to the facade? **Tests must run against BOTH the split tree and the amalgamated artifact**, so what ships (not just what's in source) is verified. Without this, the split regresses CLI portability — the strongest reason this stays shelved.
2. **Facade-persistence framing.** `ptos_cli/service/web` keep importing `ptos.foo()` for the indefinite future, with direct-import cleanup "optional." That yields two live surfaces (domain modules + facade) that can drift. The `__all__`-based surface check makes this safe, but treat the facade as a **permanent compat layer until call sites are updated**, not a temporary scaffold — update sites in a later, separate spec.
3. **Substrate-membership default.** Per plan item 1: "when unsure, into the shared layer" — make this explicit as the standing default to mirror the spec's own "leave unmigrated rather than guess global placement" principle on the records side. Both defaults together prevent both failure directions (missing shared helper vs. wrong global placement).

## When to do this work safely
- Standalone maintenance time, not mixed into a feature push.
- Step-by-step, one module per verified pass, per the spec's discipline.
- Only after the three design gaps above are resolved by their own specs.
