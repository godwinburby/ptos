# PTOS: Modularizing `ptos.py` Without Breaking Anything

## Current scale

5,411 lines, 176 top-level functions, one file. Every other file
(`ptos_cli.py`, `ptos_service.py`, `ptos_web.py`) imports it and calls
into it hundreds of times combined. That call volume is exactly why a
naive split is dangerous — and exactly why the re-export approach below
avoids the danger entirely, rather than just hoping nothing breaks.

## The mechanism that makes this safe

`ptos.py` stops being where the code lives and becomes a **facade** —
a thin file whose only job is re-exporting real implementations that now
live in domain-specific modules underneath it:

```python
# ptos.py, after extraction — illustrative shape
from ptos_core import *          # PTOSError, _safe_path, generate_id, ...
from ptos_records import *       # append_record, scan_records, ...
from ptos_links import *         # resolve_link, list_link_ids, ...
from ptos_notes import *         # list_dir, create_folder, ...
from ptos_journal import *       # journal_path, save_journal, ...
# ... etc, one line per extracted module
```

Every existing call site — `ptos.append_record(...)`,
`ptos.resolve_link(...)`, anything already written anywhere in
`ptos_cli.py`/`ptos_service.py`/`ptos_web.py` — **keeps working
unmodified**, because `ptos.append_record` still resolves, it just now
points at code that physically lives in `ptos_records.py` instead of
`ptos.py`. This is what makes "one module at a time, fully verified,
never a big rewrite" possible: the facade absorbs the reorganization, the
callers never see it happen.

## Non-goals, stated explicitly

- **No behavior changes bundled into this.** Every function moves
  verbatim — same body, same signature, same docstring. Refactoring
  logic *while* moving it doubles the risk and makes any resulting bug
  impossible to attribute to "the move" vs. "the change." Behavior
  improvements happen in separate, later specs, same discipline as
  everything else in this project.
- **No changes to `ptos_cli.py`/`ptos_service.py`/`ptos_web.py` call
  sites in this pass.** They keep saying `ptos.foo()` exactly as today.
  Updating them to import from the new modules directly (dropping the
  facade indirection) is a legitimate future cleanup, but it's a second,
  separate, lower-urgency spec — not required for the modularization
  itself to be safe or complete.
- **No fixing of the kernel-boundary issue in the same pass.** That's
  already its own spec (public-vs-private discipline across
  `ptos.py`/`ptos_service.py`). Keep these two efforts separate so a
  problem in one is never confused for a problem in the other.

## Step 0 — inventory before extraction, not instead of it

I've seen real pieces of `ptos.py` across this conversation's specs —
records, links, notes, journal, schema editing, backups — but I have not
read the file end to end, so the domain map below is a **starting
proposal**, not a verified complete inventory. Before extracting
anything, the actual first step is a full pass: list all 176 functions,
tag each with a proposed module, and specifically flag any function that
looks like it's used by more than one obvious domain (a strong signal it
belongs in the shared core module instead of any single domain module).
Skipping this and extracting from memory risks missing a function
entirely or misclassifying something with hidden cross-domain use.

## Proposed module map (provisional, pending Step 0)

**`ptos_core.py`** — extract first, since everything else depends on it:
constants and paths (`NOTES_DIR`, `JOURNAL_DIR`, `TODO_PATH`,
`DONE_PATH`, etc.), `PTOSError`, `_safe_path`-style guards,
`generate_id`/`generate_unique_id`, `resolve_time`/`_resolve_time`. The
common foundation every domain module imports from — must exist before
any domain module can be extracted, and is the least likely of any
module to have surprising cross-dependencies, since it's the dependency
everyone else has.

**`ptos_records.py`** — `append_record`, `scan_records`,
`get_log_files`, `find_records_with_location`, schema
validation/`validate_record`, `filters_to_expr`. The oldest, most
tangled-with-everything-else code — extract this **last**, once the
extraction process has been proven safe on lower-risk modules.

**`ptos_links.py`** — `resolve_link`, `list_link_ids`,
`check_dangling_links`, `append_links_to_line`/`append_links_to_todo_line`,
`append_record_id`/`append_todo_id`. Depends on `ptos_core.py` and needs
to reach into records/todo/journal/notes to resolve targets — extract
after those exist, not before.

**`ptos_notes.py`** — `list_dir`, `create_folder`, `create_file`,
`rename_note`, `delete_note_entry`, `ensure_note_id`, `note_id_of`,
`find_parent_template`, `resolve_new_file_template`. Recently built,
relatively self-contained, good candidate for an **early** extraction —
proves the process on a module with a small, well-understood surface.

**`ptos_journal.py`** — `journal_path`, `save_journal`,
`get_today_journal`, `delete_journal`. Small, self-contained, another
good early candidate.

**`ptos_schema.py`** — `add_type`, `add_type_field`, `remove_type`,
`save_schema`, `validate_schema_structure`, `get_schema`.

**`ptos_backup.py`** — `delete_backup`, `restore_config`,
`backup_config_only`, related backup-lifecycle functions.

Anything not confidently placeable during Step 0's inventory stays in
`ptos.py` itself for now, as a residual "not yet categorized" section —
better to leave something unmigrated than to guess wrong and create a
new hidden cross-module dependency.

## Extraction order — safest first, most tangled last

1. `ptos_core.py` — foundation, must exist before anything else.
2. `ptos_journal.py` and `ptos_notes.py` — small, self-contained, low
   risk, good process validation.
3. `ptos_schema.py` and `ptos_backup.py` — moderate size, moderate
   coupling.
4. `ptos_links.py` — depends on several of the above existing first.
5. `ptos_records.py` — largest, most tangled, most other code depends on
   it — do this last, once the extraction process itself is proven
   trustworthy on everything smaller.

## Verification per step — same discipline as every other feature here

Each single-module extraction gets its own spec turn and its own audit,
exactly like every feature built in this project:

1. **Diff-based confirmation** — the moved functions are byte-identical
   to their pre-move bodies (a mechanical diff check, not a re-read for
   correctness, since nothing should have changed).
2. **Facade confirmation** — `ptos.py`'s new `from ptos_X import *` line
   is present and `ptos.<function>` still resolves for everything that
   moved.
3. **Smoke test pass** — exercise a handful of CLI commands and web
   routes that are known to touch the just-moved module specifically
   (e.g., after `ptos_notes.py`: browse a folder, create a file, check a
   template-choice prompt) — not the whole app, just the surface that
   plausibly could have broken.
4. **Stop and fix before extracting the next module** — never queue up
   multiple module extractions in one unverified batch, same "ordinary
   writes first, borderline last" discipline used throughout this
   project's specs.

## What this buys you, concretely

Not safety from bugs in new features — that was never really at risk
given how this project has actually gone. What it buys is **spec and
audit tractability going forward**: asking an AI to add a feature that
touches only `ptos_notes.py`'s ~200 lines is a smaller, more reviewable
diff than one touching some subset of a single 5,411-line file, and it's
easier for you to audit "did this feature stay inside notes, or did it
reach into records unexpectedly" when notes' entire surface is one
file's worth of code, not a search through five thousand lines to find
where notes-related code happens to sit today.

## Suggested build order

1. Step 0's full inventory pass — a spec of its own, produces the real
   (not provisional) module map.
2. `ptos_core.py` extraction + verification.
3. `ptos_journal.py` extraction + verification.
4. `ptos_notes.py` extraction + verification.
5. `ptos_schema.py` extraction + verification.
6. `ptos_backup.py` extraction + verification.
7. `ptos_links.py` extraction + verification.
8. `ptos_records.py` extraction + verification — last, most tangled.
9. Once all extractions are verified and stable for a while: optionally
   revisit whether `ptos_cli.py`/`ptos_service.py`/`ptos_web.py` should
   be updated to import from the new modules directly, retiring the
   facade — not required, purely a later cleanup if the indirection ever
   actually bothers you.
