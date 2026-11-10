# PTOS Visual Fixes Spec

Suggested location: `docs/specs/ptos-visual-fixes-spec.md`
Base: `f418210` (2026-11-10). Suites at that commit: 3,964 pytest pass and 1 fails on Linux (inline-style ratchet, see V0), 81 JS pass.
Follows `ptos-design-spec.md` and `ptos-followup-spec.md`. Where they overlap, this file is newer.

## 0. Rules for the agent

1. One task per run. Do not start the next one.
2. Do not run `git commit`, `git push` or `git add -A`, and never use `--no-verify`. Leave changes uncommitted, report what changed, and give a suggested commit message. Godwin commits.
3. Ratchet baselines (`tests/css_token_baseline.json`, `tests/inline_style_baseline.json`, `tests/inline_color_baseline.json`) may only go down. Never raise one to make a test pass. If a count must rise, stop and write the question under Status.
4. No new hardcoded colours, radii, shadows or font sizes. Use tokens (`var(--fs-*)`, `var(--radius-*)`, `var(--shadow-*)`, colour variables). If a token is missing, add it to `base.css` in its own step.
5. No new `style="..."` attributes. Use classes. Dynamic widths and heights are the only exception.
6. Test first where a test is listed. Every fix needs a test that fails without it. Run `python -m pytest tests/ -q` and `node --test tests/js/*.test.js`; report the counts.
7. Product-file changes need a CHANGELOG.md entry.
8. Files are LF. Compare `git diff --stat` with `git diff --stat --ignore-space-at-eol`; stop if they differ.
9. Visual changes need a human check (section 4). Say "needs visual check"; do not claim it looks right.
10. When blocked or unsure, write the question under Status and stop.

## 1. Status

- [ ] V0 Fix ratchet paths on Linux
- [ ] V1 Remove duplicate rules in `components.css`
- [ ] V2 Move utility classes onto tokens and lower the baselines
- [ ] V3 Render widget tone with classes, not inline styles
- [ ] V4 Remove default widget tones, add tone lint
- [ ] V5 Inter font: licence, subset, rupee sign
- [ ] V6 Keyboard chord and help overlay consistency test
- [ ] V7 Visual check (human)

Questions for Godwin:
- Q1 Default widget tones: remove all defaults (recommended; widgets use the accent colour and you set a tone per widget), or keep a few meaningful ones (for example Due = warn)?
- Q2 Mapping the utility font sizes to the type scale shifts 12 px to 13 px and 14 px to 15 px (the scale has 11, 13, 15, 16, 18, 22). Acceptable, or add a `--fs-12` token?
- Q3 Who adds the Inter `OFL.txt` (licence text from the Inter release)? An agent without network access cannot fetch it.

Questions / blockers (agents write here):
- (none)

Order: V0, V1, V2, then V3 and V4, then V5, V6, V7.

## 2. What was found

Measured at `f418210`:

| ID | Finding |
|---|---|
| F1 | `css_token_baseline.json` fontsize rose 11 to 24 and radius 4 to 6; `inline_style_baseline.json` rose `widgets.js` 76 to 95 and `widget_picker.js` 1 to 2. All were raised, against rule 3. |
| F2 | The 24 raw font sizes are all in `components.css`, mostly repeated rules: `.text-sub-fs13` is defined 4 times (lines 40, 188, 198, 358), `.fs-11` to `.fs-14` twice (lines 49 to 52 and 372 to 375), `.d-none`, `.d-flex` and `.d-block` twice (lines 32 to 35 and 128 on). Duplicates inflate the counts. |
| F3 | Raw radii in `components.css`: `.alert-warn`, `.alert-error`, `.alert-success`, `.alert-info` (lines 80 to 83), `.rounded-7` (7 px, line 229), `.rounded-full` (9999 px, line 992). |
| F4 | Widget tone is drawn with inline `style="border-left:4px solid var(--chart-N)"` from a JS lookup table (`_toneColor`, `widgets.js` lines 14 to 31) in 15 render functions plus the widget picker. The lookup is an allowlist (11 values: `chart-1` to `chart-8`, `success`, `error`, `warn`), so there is no injection risk, but it adds inline styles and omits `accent` and `sub`, which the design spec allows. No `tone-*` CSS classes exist. |
| F5 | All 17 widget registrations in `ptos_service.py` (lines 3149 to 3379) have a default tone, using 10 distinct colours. Expect a rainbow dashboard. I found no tone lint and no tone tests. |
| F6 | `web_static/fonts/InterVariable.woff2` is the full 352 KB file. The repo has no OFL licence text (only the PTOS MIT licence and the `marked` and `purify` licences). |
| F7 | `tests/test_inline_style_ratchet.py` builds keys with `os.path.relpath`, so on Linux they use `/`, while 111 keys in `inline_style_baseline.json` use `\`. On Linux every JS file looks like it has a baseline of 0 and the test fails. CI runs on ubuntu-latest. |
| F8 | `web_static/sw.js` is a retired service worker that deletes caches; the PWA does not precache anything, so fonts rely on normal HTTP caching. |
| F9 | G-chord shortcuts were reshuffled in `1a9fc86` (for example `gb` board, `gh` habits). Some pages now have two chords (`gb` and `go`). No test checks that the help overlay matches the real chords. |

## 3. Tasks

### V0: ratchet paths on Linux

Files: `tests/test_inline_style_ratchet.py`, `tests/inline_style_baseline.json`. Also check `tests/test_inline_color_ratchet.py` and `tests/test_css_tokens.py` (their baselines already use `/`).
Steps:
1. Test first: add a small test that the function building the counts returns only forward-slash keys, and that the baseline file has no backslash in any key. Both fail today.
2. Change the key builder to use `pathlib.Path(...).as_posix()`.
3. Rewrite `inline_style_baseline.json` with forward-slash keys. Values must stay the same or go down; do not change any count.
4. When loading the baseline, normalise any backslash to `/` so a Windows-generated baseline still works.
Done when: `python -m pytest tests/test_inline_style_ratchet.py -q` passes on Linux and on Windows.
Suggested commit message: "Normalize ratchet baseline paths".

### V1: remove duplicate rules

Files: `web_static/css/components.css`.
Steps:
1. Write a throwaway script (do not commit it) that lists selectors defined more than once with identical declaration blocks. At least these are duplicated: `.d-none`, `.d-flex`, `.d-block`, `.text-sub-fs13`, `.fs-11`, `.fs-12`, `.fs-13`, `.fs-14`.
2. Delete the later copies, keeping the first. If two copies of one selector differ, stop and write the difference under Status.
3. Add `tests/test_css_duplicates.py`: fails if any selector in `components.css` has two identical definitions. It fails before step 2 and passes after.
4. Lower the baselines to the new counts in `tests/css_token_baseline.json`.
Done when: the duplicate test passes, both suites are green, and the `fontsize` count has dropped from 24 (report the new number).
Needs a quick visual check; no appearance change is expected.
Suggested commit message: "Remove duplicate utility rules".

### V2: utilities onto tokens

Files: `web_static/css/components.css`, `web_static/css/base.css` (one token), `tests/css_token_baseline.json`.
Mapping:

| Rule | New value |
|---|---|
| `.fs-11`, `.text-*-fs11` | `var(--fs-xs)` |
| `.fs-12`, `.fs-13`, `.text-*-fs12`, `.text-*-fs13` | `var(--fs-sm)` |
| `.fs-14` | `var(--fs-md)` |
| `.alert-warn`, `.alert-error`, `.alert-success`, `.alert-info` radius | `var(--radius-md)` |
| `.rounded-7` | `var(--radius-sm)` (7 px becomes 6 px) |
| `.rounded-full` | add `--radius-pill: 999px` to `:root` and use it |

Steps:
1. Add `--radius-pill: 999px` to `base.css` `:root` if it is missing. Check that the contrast and parity tests still pass.
2. Apply the mapping. Keep every class name, so no template changes.
3. Update `tests/css_token_baseline.json` to the new, lower counts (target: `fontsize` 0 for new utilities and `radius` at most 4, the pre-migration count).
Done when: both suites are green, the baseline is lower than at `f418210` for fontsize and radius, and no `px` literals remain in the utility classes listed above.
Needs visual check (Q2).
Suggested commit message: "Use design tokens in utility classes".

### V3: tone with classes

Files: `web_static/js/widgets.js`, `web_static/js/widget_picker.js`, `web_static/css/components.css`, `tests/inline_style_baseline.json`, new `tests/js/widget_tone.test.js`.
Steps:
1. Test first (jsdom, same pattern as other tests in `tests/js/`):
   - rendering a widget with `tone: "chart-3"` gives an element with class `tone-chart-3` and no `style` attribute carrying a colour
   - `tone: "red;background:url(x)"` gives no tone class
   - `tone: "accent"` and `tone: "sub"` are accepted
2. In `components.css` add, for each allowed token (`accent`, `success`, `warn`, `error`, `sub`, `chart-1` to `chart-8`): `.tone-NAME { --tone: var(--NAME); }`, plus one rule `[class*="tone-"] { border-left: 4px solid var(--tone); }` scoped to widget cards.
3. In `widgets.js` replace each `style="border-left:..."` with the class from one helper `_toneClass(tone)` that checks the allowlist (the 11 current values plus `accent` and `sub`) and returns `tone-NAME` or an empty string. Remove `_toneColor`. Check what `_toneBg` is used for; if it is unused, delete it, otherwise convert it the same way.
4. Do the same in `widget_picker.js` (`_card(tone)`).
5. Lower `tests/inline_style_baseline.json` for `widgets.js` back to 76 or lower and `widget_picker.js` to 1 or lower.
Done when: the JS tests pass and the baselines are at or below their pre-C8 values (76 and 1).
Needs visual check: widget cards in light and dark; border colour visible in both.
Suggested commit message: "Render widget tone with classes".

### V4: default tones and lint

Files: `ptos_service.py` (registrations at lines 3149 to 3379), `ptos_widgets.py`, `ptos_service.py` key lint (around the "is not a valid key for" message), new `tests/test_widget_tone.py`.
Steps:
1. Decide Q1 with Godwin first. Recommended: remove the default `tone=` from all 17 registrations. Keep `icon`.
2. Test first:
   - a widget with no `tone` renders with no tone class
   - a valid `tone` in the widget spec reaches the rendered spec unchanged
   - an invalid `tone` produces a lint warning of the form `'tone' must be one of: accent, success, ...` and is dropped
   - a widget with neither key behaves as before (existing widget tests stay green)
3. Implement the allowlist once (one constant) and use it for the lint and, if possible, as the source for the JS list via the page data, so there are not two lists to keep in sync. If sharing is hard, add a test that the Python constant and the JS helper accept the same set.
Done when: the new tests pass and no widget shows a tone unless the spec sets one.
Suggested commit message: "Make widget tone opt-in and lint invalid values".

### V5: Inter font hygiene

Files: `web_static/fonts/`, `web_static/css/base.css`.
Steps:
1. Godwin supplies `OFL.txt` (Q3); add it as `web_static/fonts/OFL.txt` (the licence requires the text to travel with the font).
2. Subset to Latin plus the rupee sign. The rupee sign U+20B9 must be in the result because PTOS shows amounts in rupees. Keep the variable weight axis (100 to 900) and the `tnum` feature (tabular numbers). Example (verify the options on your fonttools version):
   ```
   pyftsubset InterVariable.woff2 --flavor=woff2 --layout-features='*' \
     --unicodes="U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+20B9,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD" \
     --output-file=InterVariable-latin.woff2
   ```
3. Check the result: size under about 150 KB, still variable, contains `₹`. Write a test (`tests/test_font_file.py`, using `fontTools` if installed in dev, else skip) that opens the file and asserts U+20B9 is present and an `fvar` table exists.
4. Update the `@font-face` `src` to the new filename; keep `font-display: swap`.
5. Check how `/static/fonts/...` is served: fonts should be cacheable for a long time. If the app sets no cache lifetime for static files, note it; do not change the global setting in this task.
Done when: the rupee sign renders in Inter in Add Record and the Home stat cards, amount columns align, and the file is smaller than 150 KB.
Suggested commit message: "Subset Inter and add its licence".

### V6: chord and help overlay consistency

Files: new `tests/test_nav_chords.py` or a JS test next to `tests/js/slash_nav.test.js`.
Test: every chord defined in `web_static/js/nav_chords.js` appears in the help overlay table (the Extended Navigation section) and every chord in the table exists in the JS; no two chords target different pages with the same keys; list pages that have two chords (for example board has `gb` and `go`) so the duplication is a decision, not an accident.
Done when: the test passes; any duplication is either removed or listed in the test as intentional.
Suggested commit message: "Add chord and help overlay consistency test".

## 4. V7: visual check (human)

After each visual task, check at 390 px and 1440 px width in light and dark: Home, Todos, Routines, Habits, Calendar, Board, Browse, Queries, Query Builder, Schema Builder, Settings, Backup, Add Record, Editor.
Specific things to look at:
- Add Record: the "Show all" presets button opens and closes (it broke once already), and preset chips are visible.
- Backup, Settings, Query Builder and Schema Builder: every section expands and collapses; no stray inline-style gaps.
- Widget cards: tone borders visible only where a tone is set; icons aligned.
- Text: the rupee sign is Inter, and amount columns line up at the decimal point.
- Dark mode: no white boxes, no unreadable text.
Send screenshots of anything wrong; each becomes a small task.

## 5. Risks and not verified

- I have not seen the migrated pages or the widget borders in a browser; findings come from code, diffs and tests.
- The Linux ratchet failure is established (111 backslash keys against `os.path.relpath`); whether CI is currently red I could not see.
- The Inter subset command depends on the fonttools version; verify the output rather than trusting the command line.
- Mapping 12 px to 13 px and 14 px to 15 px is a small visible change (Q2).
- The duplicate rules might differ in a way that matters; V1 stops and asks if they do.
