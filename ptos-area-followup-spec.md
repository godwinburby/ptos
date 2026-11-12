# PTOS Area Follow-up Spec

Suggested location: `docs/specs/ptos-area-followup-spec.md`
Base: `e61e653` (2026-11-12). Suites at that commit: 4,070 pytest and 90 JS pass.
Follows `ptos-area-pages-spec.md` and `area-page-template.md`. Where they disagree, this file wins.

## 0. Rules for the agent

1. One task per run. Do not start the next one.
2. Do not run `git commit`, `git push` or `git add -A`, and never use `--no-verify`. Leave changes uncommitted, report what changed, give a suggested commit message. Godwin commits.
3. Test first. Every fix needs a test that fails without it. Run `python -m pytest tests/ -q` and `node --test tests/js/*.test.js`; report the counts.
4. CHANGELOG.md entry for every product-file change.
5. No area names in code. Areas are data (schema options, tags, folders).
6. No hardcoded colours, radii, shadows or font sizes; no new inline `style="..."`; ratchet baselines only go down.
7. A todo line must never lose or reorder text silently except for the canonical placement of known tokens. Never drop a token.
8. LF line endings only. Touch only the files the task lists.
9. When unsure, write the question under Status and stop.

## 1. Status

- [ ] AF1 Chord conflicts: Areas and Projects shortcuts
- [ ] AF2 Duplicate `area:` tokens must be stable
- [ ] AF3 Area lists: schema options plus areas in use
- [ ] AF4 `/areas` page: all areas, record counts, links
- [ ] AF5 Starter template: journaling sections, safe placeholders
- [ ] AF6 Validate the area in the New Folder route
- [ ] AF7 Tests for the area schema field, folder template and nav entry
- [ ] AF8 CHANGELOG and README

Questions for Godwin (answer before the task named):
- Q1 (AF2) When a line has two `area:` tags, which wins? Recommended: the last one, because the app appends the canonical tag at the end of the line, so "last wins" is stable. The current rule is "first wins", which flips the area after one save. Changing it means updating one existing test.
- Q2 (AF3) Should area pickers show only the schema options (current behaviour once `global_fields.area.options` is set), or the schema options plus any area already used on a task? Recommended: both.
- Q3 (AF4) Is `/areas` enough as the bird's-eye page, or do you also want a hand-edited `Areas.md` dashboard? Recommended: `/areas` is enough.
- Q4 (AF1) Chords: Areas on `g v`, Projects on `g p`, Entity stays `g j`. Agree?
- Q5 (AF5) Your own areas are work, finance, relationship, health, spirituality, career and business. Should the starter schema's default options stay generic (work, home, personal, health) or use these? Recommended: stay generic; you edit your own schema.

Questions / blockers (agents write here):
- (none)

Order: AF1, AF2, AF3, AF4, AF6, AF5, AF7, AF8. AF1 and AF2 are the two real bugs.

## 2. What was found (at `e61e653`)

| ID | Finding |
|---|---|
| F1 | The nav entry for Areas says `G V` (`ptos_web.py` line 254) but `nav_chords.js` maps `"g v"` to `/entity`. Entity and Projects both show `G J` in the nav (lines 245 and 253); only Entity has that chord in the JS. `"g f"` appears twice in the chord map (lines 234 and 248). Areas has no working shortcut. |
| F2 | `ptos_todo.py` keeps the first valid `area:` token and leaves a second one in the text (line 256), then appends the canonical `area:` at the end on write (line 356). Verified: `Call mom area:relationship area:work` parses as relationship, is written as `area:work area:relationship`, and then parses as work. The area changes on the next save. |
| F3 | `get_todo_areas_with_fallback()` (`ptos_service.py`, near line 9035) returns the schema options and nothing else when `global_fields.area.options` is set, although its docstring says it merges. A task tagged with an area not listed in the schema disappears from the Todos toolbar, quick-add suggestions and quick-pick chips. |
| F4 | `get_areas_with_counts()` builds the list only from areas that already appear on tasks, so schema areas and new area folders are missing until a task uses them. Cards show only task counts, and each links only to `/todo?area=...`, not to the area's page. There are no record counts. |
| F5 | `starters/starter_area.md` has Tasks, Records and "Notes in this area" blocks only; the journaling sections (Now, Plan, Log, Reflections, Reviews) from `area-page-template.md` are not in it. It uses `{{AREA}}` and `{{AREA_TITLE}}` placeholders, which look like the notes renderer's live tokens. Its third block queries `type=note`, which may not be a record type. No test checks that the starter's `ptos` blocks are valid. |
| F6 | `/notes/new-folder` (`ptos_web.py` line 1829) passes `area` straight to `svc_create_folder`, which pastes it into the template. A quote or newline in the value breaks the generated `ptos` block. `_area_slug()` already exists in `ptos_service.py` and raises `PTOSError` on a bad slug. |
| F7 | Commits for the `global_fields.area` starter field, the area folder template, the `/areas` page and nav entry, and both autocomplete commits have no tests (only the todo-side commit has 4 Python and 11 JS tests), and no CHANGELOG entries except the todo-side one. |

## 3. Tasks

### AF1: chords

Files: `web_static/js/nav_chords.js`, `ptos_web.py` (nav entries), new `tests/test_nav_chords.py`.
Steps:
1. Test first (pytest, text scan, no browser needed):
   - every nav entry shortcut of the form `G X` has a matching `"g x"` key in `nav_chords.js` pointing at that entry's path
   - no key appears twice in the chord map
   - each chord key maps to exactly one path
   - pages with several chords (for example board has `g b` and `g o`) are listed in the test as intentional aliases
2. Fix: `"g v"` points to `/areas`; add `"g p"` for `/projects` and set the Projects label to `G P`; remove the duplicate `"g f"` line. Keep `"g j"` for Entity.
3. If the help overlay lists chords (search templates and JS for the Extended Navigation table), update it to match and cover it in the test.
Done when: the test passes and pressing `g v` opens Areas, `g p` Projects and `g j` Entity (manual check).
Suggested commit message: "Fix area and project chords and add chord test".

### AF2: stable duplicate area tags

Files: `ptos_todo.py`, tests in `tests/test_todo.py` (or the file that holds the area tests).
Steps:
1. Test first. Over these lines assert that parse, then write, then parse gives the same area, and that no token is lost from the text (every original token is still present after one write):
   - `Call mom area:relationship area:work`
   - `area:work Task area:health`
   - `Pay bill area:Bad Name area:work`
   - `x 2026-11-10 Done thing area:finance area:work`
2. Apply Q1. If "last wins": scan all tokens, take the last valid `area:` slug as the area, keep every other `area:` token in the description unchanged, and keep appending the canonical tag at the end (which is then the last one, so it is stable). Update the one existing test that asserts "first wins" and say so in the report. If Q1 is "first wins": write the canonical tag before the first leftover `area:` token in the text instead of at the end.
3. Add a lint warning for lines with more than one valid `area:` tag (the Todos lint, so the file owner can clean it up).
Done when: the idempotence test passes for all four lines and the existing todo tests still pass.
Suggested commit message: "Keep area stable when a todo has two area tags".

### AF3: area lists

Files: `ptos_service.py` (`get_todo_areas_with_fallback`), tests.
Steps:
1. Test first: with schema options `["work","home"]` and a todo tagged `area:finance`, the returned list is `["work","home","finance"]` (schema order first, then extras alphabetically, no duplicates); with no schema options it returns only the areas in use; with neither it returns an empty list.
2. Implement the union (Q2) and update the test changed in `e61e653` (`tests/test_todo_widget.py`) to match; confirm the Todos toolbar select, quick-add autocomplete and quick-pick chips all read from this one function.
Done when: all three sources show a task's area even if it is not in the schema.
Suggested commit message: "Merge schema and in-use areas in pickers".

### AF4: `/areas` page

Files: `ptos_service.py` (`get_areas_with_counts`), `ptos_web.py` (`areas_index`), `web_templates/areas.html`, `web_static/css/components.css` only if a class is missing (tokens only).
Behaviour:
- list every area from the union in AF3, including ones with no tasks (zeros)
- each card shows the existing task counts (open, done, overdue, due today) and a "this month" record count (records whose `area` equals the slug)
- each card links to the Todos filter as now, and also to the area's page when a notes folder named after the slug exists; otherwise it shows a plain "No page yet" text (no create button in this task)
Steps:
1. Find how the `records` widget evaluates `where` and `time` without a saved query (`_w_records` near line 2756 in `ptos_service.py`, and what it calls) and reuse that for the count; do not write a second query engine. If no reusable function exists, add a thin helper that calls the same code and report where.
2. Test first:
   - schema options `["work","health"]` and no tasks: both cards render with zeros
   - a todo tagged `area:finance` (not in the schema) also renders
   - with fixture records, the this-month count per area is right and records without an area are ignored
   - the page renders no inline `style=` and no hex colours; links are correct for an area with and without a folder
Needs a visual check at 390 px and 1440 px, light and dark.
Suggested commit message: "Show all areas with record counts on /areas".

### AF6: validate the area in the New Folder route

Files: `ptos_web.py` (`notes_new_folder`, line 1829), `ptos_service.py` (`svc_create_folder`), tests.
Steps:
1. Test first: posting `area = "work"` creates `template.md` containing no `{{AREA}}` placeholder; posting `Bad Name!`, `x"\\nview = "y`, and `../x` returns `ok=False` with a readable message and creates no folder and no file; an empty area creates the folder without a template.
2. Call `_area_slug()` on the value before creating anything, and return its message on failure. The folder is created only after validation passes (no half-created folder on error).
Suggested commit message: "Validate area before seeding a template folder".

### AF5: starter template

Files: `starters/starter_area.md`, new `tests/test_starter_area.py`.
Steps:
1. Test first:
   - after replacing the placeholders with `work` and `Work`, every ```` ```ptos ```` block is valid TOML and passes the same widget key validation used for notes (`area` is a valid key on `todo` and `todo_summary` after the earlier work)
   - no placeholder text remains after replacement
   - unreplaced placeholders render harmlessly in a note (find how the notes renderer treats `{{...}}` by reading `tests/js/md_tokens.test.js` and the token code it loads; the test asserts that `{{AREA}}` is left as visible text or removed, not turned into something else)
   - the file contains no raw colours or HTML
2. Rewrite the starter from `area-page-template.md`: keep the Tasks block, the Records block and a Numbers block; add the sections Now, Plan (quarter, year, someday), Log, Reflections and Reviews (weekly, monthly, quarterly). Keep the replacement mechanism as it is (`{{AREA}}`, `{{AREA_TITLE}}`) unless the token test above shows a conflict; if it does, switch to a placeholder the renderer ignores and update `_seed_area_template`.
3. Check whether `note` is a real record type in the starter schema. If not, delete the "Notes in this area" block; if it is, keep it.
4. Use `where` in the same form the `records` widget accepts (list or string, whichever its validation and tests use); do not guess.
Suggested commit message: "Restore journaling sections in the area starter".

### AF7: tests for the area schema field, folder template and nav

Files: new `tests/test_area_pages.py`.
Tests (all should pass without production changes; if one fails, stop and write what is wrong under Status):
- `starters/starter_schema.toml` loads with `global_fields.area.options` equal to `["work","home","personal","health"]` and `linkable = true`
- a record written with an `area` value is found by `where = ["area=work"]` for at least two different record types (the field is global)
- creating a folder with an area seeds `<folder>/template.md`; creating a new page in that folder uses the folder's `template.md` (the template inheritance the earlier commit describes)
- the nav sections include an entry with path `/areas` in the Track section; `GET /areas` returns 200 with and without data
Suggested commit message: "Add tests for area schema field, folder template and nav".

### AF8: CHANGELOG and README

Files: `CHANGELOG.md`, `README.md`.
- CHANGELOG: add entries for the commits that have none: `7736e0c` (area field in the starter schema), `fb48827` (area folder template and starter), `45833a1` (`/areas` page and nav), `081fe14` and `e61e653` (area autocomplete from schema), plus one entry per AF task above.
- README: a short "Area pages" section: the `area:` tag and slug rule, the `global_fields.area` schema field and how to edit its options, how to create an area folder from New Folder, what `/areas` shows, and the two chords.
Suggested commit message: "Document area pages and changelog".

## 4. Not verified

- I have not opened `/areas`, the Todos filter or the New Folder dialog in a browser; findings come from code, a round-trip probe and tests.
- How the notes renderer treats unknown `{{...}}` tokens, and whether `note` is a record type, are left to AF5 to check.
- The existing area tests were not read line by line; AF2 may have to change the one asserting "first wins".
- Record counts in AF4 depend on finding a reusable query helper; if none exists the task may need a small new function.
