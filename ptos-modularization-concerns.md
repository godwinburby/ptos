# PTOS: Modularization Concerns — Review of `ptos-modularization-spec.md`

## Purpose

A companion review of `ptos-modularization-spec.md`. That spec's core mechanism (facade re-export via `ptos.py`) and its non-goals are **sound** — this document does not propose abandoning the approach. It records four concrete concerns that must be resolved **before** the inventory/extraction work begins, all of which stem from a single measurement of the real code: the internal cross-coupling of `ptos.py` is substantially higher than the provisional module map implies, and the proposed `ptos_core.py` is too thin to own the shared substrate those couplings depend on.

## Evidence — why this matters

Measured against `ptos.py` (5,411 lines, 176 top-level functions):

- **64 functions make internal calls that cross the proposed module boundaries** (a rough tagging of the spec's own module names applied to each `ptos.<fn>(...)` call inside every function body).
- Representative cross-boundary calls found:
  - record-domain → links: `run_set` → `backlink_refs`, `lint_all_records` → `check_dangling_links`, `apply_set` → `resolve_link`/`list_link_ids`
  - records ↔ shared parse: `scan_records` → `apply_where`/`_glob_match`/`numeric_value_for`/`parse_line`
  - schema ↔ records: `remove_type` → `find_records_with_location`, `lint_all_records` → `validate_record`/`get_schema`
  - dashboard/query → core: `run_metric` → `resolve_time`/`numeric_value`/`_run_base_query`

The facade (`ptos.py` re-exporting from `ptos_X`) cleanly preserves **name resolution** for callers. It does **not** by itself resolve **Python import-level circularity** between the extracted modules — which is the actual failure mode this split will hit.

## Concern 1 — Circular imports are the real risk, and the spec never addresses them

The facade absorbs `ptos.foo()` resolution, but when `ptos_records.py` imports a helper that lives in `ptos_links.py`, and `ptos_links.py` (per the spec, "needs to reach into records/todo/journal/notes") imports back into `ptos_records.py`, Python raises `ImportError: cannot import name ...` at module load.

This is the #1 practical failure mode for a split of this size, and the spec has no rule preventing it. A split plan must guarantee: **no domain module imports another domain module directly; every shared dependency is hosted in a common lower layer first.**

## Concern 2 — `ptos_core.py` as proposed is too thin to own the real shared substrate

The proposed `ptos_core` is: constants/paths, `PTOSError`, `_safe_path`-style guards, `generate_id`/`generate_unique_id`, `resolve_time`/`_resolve_time`.

But the cross-coupling measurement shows the genuinely shared, multiply-depended substrates are the **parse/match/numeric/fmt helpers** the proposed domain tags scatter across modules:
- `parse_line`, `safe_parse_line`, `apply_where`, `_is_expression`, `_glob_match`, `numeric_value`, `numeric_value_for`, `compute_derived`, `derived_fields`, `_disp`, `fmt`, `fmt_avg`, `build_record_line`, `_run_base_query`.

Many of these are called by functions in several different proposed modules. If they stay in `ptos_records` (as the provisional map implies for `apply_where`/`parse_line`/`filters_to_expr`), then `ptos_links`/`ptos_notes`/`ptos_journal` all become dependents of `ptos_records` — which is the *highest-tangled* module and the one the spec schedules **last**. That ordering is incompatible with those dependents being extracted earlier.

**Resolution:** expand `ptos_core` (or add a `ptos_parse.py`/`ptos_util.py` sibling) to host the truly shared low-level helpers so that domain modules depend only on core/common, never on each other. The exact membership must come from the Step-0 dependency graph, not from an upfront list.

## Concern 3 — The extraction order must be a dependency-ordered plan, not an intuition-based sequence

The spec's ordering rationale ("notes/journal first, records last") is reasonable as a *risk* sequence, but it is not sufficient as a *dependency* sequence. The binding constraint is: **before extracting module X, every function X depends on must already live in an existing module (or core).**

For example, `ptos_links.py` "depends on several of the above existing first" — but the spec also has links being extracted *before* records (step 7 vs step 8), and links need record helpers. Those helpers must therefore be pre-moved into core *before* the links extraction, which changes the order the spec lists.

The order should be derived by a reverse-topological walk over the Step-0 dependency graph, and documented as such, so that no extraction ever references a function that hasn't been placed yet.

## Concern 4 — `from ptos_X import *` needs `__all__` and an automated surface check

Star-import re-export is fine when the facade is owned by `ptos.py`, but each extracted module should declare an explicit `__all__` containing exactly the public names it owns. Without it:
- private `_`-helpers can leak into the facade namespace and be mistaken for public API (re-introducing the exact kernel-boundary ambiguity the boundary spec is removing);
- name collisions across modules become silent;
- there is no mechanical way to assert the facade surface is unchanged.

**Resolution:** (a) each `ptos_X.py` defines `__all__`; (b) add a test asserting `set(public_names_in_ptos.py)` is identical before vs. after each extraction (a recorded `ptos_public_names.txt` golden file, or an in-test constant snapshot); (c) keep the old underscore aliases inside the owning module for one release, per the boundary spec's aliasing discipline.

## What this changes about the plan (delta vs. original spec)

1. **Step 0 must produce a dependency graph, not just a module tag per function.** For each of the 176 functions: proposed module + every other `ptos.py` function it calls + an explicit circular-import scan across the proposed boundaries. This is a read-only analysis spec of its own, and is required before any extraction.
2. **The shared-helper layer is expanded/redefined** from the graph, so no domain module imports another domain module.
3. **Extraction order is re-derived** as a topological sequence from that graph (with the risk ordering as a tie-break), replacing the intuition-based list.
4. **`__all__` + surface-assertion test** become a hard requirement of every extraction's verification step.

## Non-goals (unchanged, reaffirmed)

- No behavior changes bundled into the modularization.
- No changes to `ptos_cli.py`/`ptos_service.py`/`ptos_web.py` call sites in this pass.
- No kernel-boundary work mixed into this pass.
- Circular-import resolution is a **structuring** concern solved by module placement (core-first), not by fragile `import` gymnastics inside the facade.

## Suggested next step

Author **Step 0 as its own read-only analysis spec**, expanded per the delta above: produce the verified dependency graph, the revised module map (including the shared-helper core), the derived extraction order, and the circular-import check — then stop for review before any file is moved.
