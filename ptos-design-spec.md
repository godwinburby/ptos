# PTOS Design Spec

Suggested location: `docs/specs/ptos-design-spec.md`
Base: `053b908` (2026-11-04)
Scope: how PTOS looks (tokens, dark mode, type, layout, mobile polish, widget colour and icon properties). No change to data formats except two new optional widget keys (`tone`, `icon`).

## 0. Rules for the agent

1. One task per run. Do not start the next one.
2. Do not run `git commit`, `git push` or `git add -A`. Leave changes uncommitted, report what changed, and give a suggested commit message. Godwin commits.
3. Test first where a test is listed. Run `python -m pytest -q` and `node --test tests/js/*.test.js` before reporting done; report the counts.
4. Files are LF. Compare `git diff --stat` with `git diff --stat --ignore-space-at-eol`; stop if they differ.
5. No new hardcoded colours, radii, shadows or font sizes. Use the tokens from D1. If a needed token is missing, stop and write the question under Status.
6. Touch only the files the task lists. No unrelated cleanups.
7. Add a CHANGELOG.md entry for product-file changes.
8. Visual changes need a human check (section 9). Say "needs visual check" in the report; do not claim it looks right.

## 1. Status

- [ ] D1a Token definitions in `base.css`
- [ ] D1b Ratchet test for hardcoded values
- [ ] D1c Migrate radii, shadows, font sizes
- [ ] D1d Migrate hardcoded colours
- [ ] D2a Dark palette and theme switching
- [ ] D2b Theme toggle in settings
- [ ] D2c Contrast test
- [ ] D3a Font and `.num` class
- [ ] D3b Apply `.num` to numbers
- [ ] D4 Layout and mobile polish (several small tasks, see section 5)
- [ ] D5 Inline-style cleanup (ratchet plus top five templates)
- [ ] D6a Widget `tone` and `icon` keys (backend)
- [ ] D6b Render tone and icon (frontend)
- [ ] D6c Tokenize todo group colours
- [ ] D6d Swatch picker in the widget editor
- [ ] B1 Run-together text on Habits summary and Overdue Records row
- [ ] B2 Floating + button covers row actions
- [ ] B3 Browse tooltip overlaps the "VALUES FOR" label
- [ ] B4 Check the "Expense today" card on Home
- [ ] B5 Check completed days on the Habits grid
- [ ] B6 Check the repeated "Now" line on Routines
- [ ] D7 Screen-by-screen design fixes (section 10)

Questions / blockers (agents write here):
- (none)

Order: D1 first. D2 after D1d. D3 any time after D1a. D4 after D1c. D5 in parallel with anything. D6 after D1d and D2a.

## 2. Current state (measured at `053b908`)

- Tokens exist as CSS variables in `web_static/css/base.css` (`--bg --card --border --accent --accent-d --accent-lt --success --success-lt --error --error-lt --warn --warn-lt --text --sub`, `--chart-1` to `--chart-8`, `--chart-other`, plus `--nav-h --safe-b --sidebar-w`). Light theme only.
- Hardcoded hex colours outside the variables: 65 occurrences (38 distinct) in `base.css`, 18 (9 distinct) in `components.css`, 4 in `page_shell.css`, 2 in `base-widgets.css`.
- Corner radii: 4, 6, 8, 10 and 12 px, no scale. 19 different `box-shadow` values.
- Font sizes in use: 10, 10.5, 11, 11.5, 12, 12.5, 13, 14, 15, 16, 18, 20, 22 px. Most common: 12 (49 uses), 13 (34), 11 (27), 14 (21).
- Font stack: `"Segoe UI", system-ui, -apple-system, sans-serif`. Monospace uses Consolas.
- No dark mode (no `prefers-color-scheme`, no `data-theme`).
- Inline `style="..."` attributes: 1,491 in templates (237 in `query_builder.html`, 182 `schema_builder.html`, 164 `settings.html`, 100 `add.html`, 83 `backup.html`) and about 205 in JS.
- Widget instance keys are whitelisted in `ptos_widgets.py:22` (`COMMON_KEYS`: view, name, time, from_date, to_date, title, limit, span, hide_on, live); unknown keys are linted in `ptos_service.py` (around line 3767, message "'{k}' is not a valid key for ...").
- The one data-driven colour today: todo group headings use `g.color` inside an inline style (`web_static/js/widgets.js`, around lines 949 and 955).

Known contrast problems in the light palette (WCAG ratios, measured):

| Pair | Ratio | Needs |
|---|---|---|
| `--warn` text on white | 2.77 | 4.5 for text |
| `--warn` on `--warn-lt` | 2.53 | 4.5 for text |
| `--accent` text on `--accent-lt` | 4.00 | 4.5; use `--accent-d` there |
| `--sub` on `--bg` | 4.47 | 4.5; darken `--sub` slightly |
| `--accent` on white / white on `--accent` | 4.51 | borderline, passes |

Fix: add `--warn-text` (a darker amber, for example `#B45309`; verify it reaches 4.5 on white with the D2c test) and use it for warning text; keep `--warn` for fills and borders.

## 3. D1: design tokens

### D1a: define tokens

File: `web_static/css/base.css`, inside `:root`. Add without changing existing variables:

```
/* spacing */
--space-1: 4px;  --space-2: 8px;  --space-3: 12px;
--space-4: 16px; --space-5: 24px; --space-6: 32px;
/* radius */
--radius-sm: 6px;   /* inputs, chips */
--radius-md: 10px;  /* cards, buttons */
--radius-lg: 14px;  /* modals, sheets */
/* shadow */
--shadow-1: 0 1px 2px rgba(0,0,0,.06);
--shadow-2: 0 4px 16px rgba(0,0,0,.12);   /* popovers, menus */
--shadow-3: 0 8px 32px rgba(0,0,0,.20);   /* modals */
/* type scale */
--fs-xs: 11px; --fs-sm: 13px; --fs-md: 15px; --fs-base: 16px;
--fs-lg: 18px; --fs-xl: 22px;
/* extra colour tokens */
--surface-2: #F8F9FC;   /* subtle panels inside cards */
--warn-text: #B45309;   /* verify contrast in D2c */
```

Done when: both suites green; no other file changed.
Suggested commit message: "Add design tokens".

### D1b: ratchet test

File: new `tests/test_css_tokens.py`. The test reads every file in `web_static/css/`, strips comments, and counts occurrences outside `:root` and theme blocks of:
- hex colours (`#[0-9a-fA-F]{3,8}`)
- `border-radius` values that are not `var(--radius-*)`, `0`, `50%`, `999px`
- `box-shadow` values that are not `var(--shadow-*)`, `none`, or an inset status bar (`inset 3px 0 0 var(--...)`)
- `font-size` values in px that are not `var(--fs-*)`

It compares each count to a committed baseline file `tests/css_token_baseline.json` and fails if any count increases. A second assertion fails if a count decreased but the baseline was not updated, so the baseline is always tight. Initial baseline = today's counts.
Done when: the test passes at the baseline and fails if you add one hex colour to a copy of `components.css`.
Suggested commit message: "Add CSS token ratchet test".

### D1c: migrate radii, shadows, font sizes

Files: `web_static/css/*.css` (one file per run is fine). Mapping:
- Radius: 4 and 6 px to `--radius-sm`; 8 and 10 px to `--radius-md`; 12 px and above (modals, sheets) to `--radius-lg`. Pills (`999px`) and circles (`50%`) stay.
- Shadow: card shadows to `--shadow-1`; menus and popovers to `--shadow-2`; modals and overlays to `--shadow-3`. Inset status bars (`inset 3px 0 0 var(--success)`) stay.
- Font size: 10, 10.5, 11, 11.5 to `--fs-xs`; 12, 12.5, 13 to `--fs-sm`; 14, 15 to `--fs-md`; 16 to `--fs-base`; 17 to 20 to `--fs-lg`; 22 and above to `--fs-xl`.
After each file, update the ratchet baseline in the same run.
Done when: ratchet counts for radius, shadow and font size are at or near zero (document any exceptions in the baseline file with a one-line reason).
Needs visual check: compare home, todo, queries, settings before and after at 390 px width.
Suggested commit message: "Migrate radii, shadows and font sizes to tokens".

### D1d: migrate hardcoded colours

Files: `web_static/css/*.css`. For each distinct hex outside `:root`, choose in this order: an existing variable if the colour is within a few units of it, else a new semantic variable (`--surface-2`, `--text-muted`, `--accent-text`, `--warn-text`), else keep with a one-line reason in the baseline file. Do not convert colours inside SVG data URIs unless trivial. Do `base.css` last (65 occurrences).
Done when: hex count outside `:root` is under 10, baseline updated, visuals unchanged (light theme).
Suggested commit message: "Replace hardcoded colours with variables".

## 4. D2: dark mode

### D2a: dark palette and switching

Files: `web_static/css/base.css`, `web_templates/base.html`.
Proposed dark values (contrast measured against `--card`):

```
:root[data-theme="dark"] {
  --bg:#0F1115; --card:#171A21; --surface-2:#1C2029; --border:#2A2F3A;
  --text:#E6E8EE; --sub:#9AA3B2;
  --accent:#7C93FF; --accent-d:#9DB0FF; --accent-lt:#1E2540;
  --success:#4CC38A; --success-lt:#12261D;
  --error:#FF7B6B;   --error-lt:#2C1614;
  --warn:#F0A15E;    --warn-lt:#2B2013;  --warn-text:#F0A15E;
  --chart-1:#7C93FF; --chart-2:#F0A15E; --chart-3:#4CC38A; --chart-4:#FF7B6B;
  --chart-5:#A78BFA; --chart-6:#2DD4BF; --chart-7:#F472B6; --chart-8:#94A3B8;
  --chart-other:#475569;
  color-scheme: dark;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { /* same declarations as above */ }
}
```

Measured: text on card 14.21, sub on card 6.84, accent on card 6.20, dark text on accent button 6.73, success 7.86, error 6.88, warn 8.26. Primary buttons in dark mode use dark text on the accent background.

Switching: set `data-theme` on `<html>` from `localStorage["ptos-theme"]` (`light`, `dark`, or absent for auto) in an inline script at the top of `<head>` so there is no flash. Also set `<meta name="theme-color">` for both schemes. Keep the CSS in one place; do not duplicate the dark block in other files.
Check how charts get their colours: if JS reads hardcoded colours, switch them to `getComputedStyle(document.documentElement).getPropertyValue("--chart-N")` and redraw on theme change.
Done when: with `data-theme="dark"` set by hand, every page has readable text; `grep` finds no unthemed hex colour (D1d done).
Needs visual check (section 9).
Suggested commit message: "Add dark theme".

### D2b: toggle

File: `web_templates/settings.html` and a small JS file. A three-way control (Auto, Light, Dark) that writes `localStorage["ptos-theme"]` and updates `data-theme` immediately.
Test (JS, jsdom): selecting Dark sets `data-theme="dark"` and storage; Auto removes both.
Suggested commit message: "Add theme setting".

### D2c: contrast test

File: new `tests/test_theme_contrast.py`. Parse the `:root` and `:root[data-theme="dark"]` variable blocks from `base.css`, compute WCAG contrast, and assert at least 4.5 for these pairs, in both themes: `--text/--card`, `--text/--bg`, `--sub/--card`, `--sub/--bg`, `--accent-d/--accent-lt`, `--success/--card`, `--error/--card`, `--warn-text/--card`, `--warn-text/--warn-lt`; and at least 4.5 for button text on `--accent` (white in light, `--bg` in dark). Also assert that every variable defined in light `:root` is defined in the dark block (so new tokens cannot be forgotten).
Done when: it passes after the `--sub` and `--warn-text` fixes from section 2 are applied to the light palette.
Suggested commit message: "Add theme contrast and parity test".

## 5. D3 and D4: typography, layout, mobile

### D3a: font and number class

Files: `web_static/css/base.css`, new `web_static/fonts/`. Self-host one variable font (for example Inter, latin subset, woff2) with `@font-face { font-display: swap; }`, put it first in the stack, keep `"Segoe UI", system-ui, ...` as fallback. If the app has a service worker with a precache list, add the font file and bump its cache version. Add:

```
.num { font-variant-numeric: tabular-nums; }
```
Check the font's licence allows redistribution (Inter is OFL).
Suggested commit message: "Self-host UI font and add .num class".

### D3b: apply `.num`

Files: the templates and JS that render money, counts and stat values (browse tables, stat cards, thresholds, charts labels). Apply `.num` to numeric cells and `.stat-value`. Do not change content.
Needs visual check: amount columns line up at their decimals.
Suggested commit message: "Use tabular numbers for amounts and stats".

### D4: layout and mobile polish (each bullet is its own run; keep each small)

- **D4-1 Hierarchy:** define `.page-title`, `.section-title`, `.muted` using the type tokens; apply to the home, todo and queries pages first.
- **D4-2 Spacing:** cards use `--space-4` padding and `--space-3` gap on mobile, `--space-5` on desktop; replace ad hoc margins in `components.css` page by page.
- **D4-3 One primary action:** each card or modal has at most one accent-filled button; other buttons use a neutral style. Audit `query_builder.html`, `settings.html`, `add.html` first.
- **D4-4 Semantic colour:** green, red and orange only for status (done, error, warning); the accent only for primary actions and the active state.
- **D4-5 Touch targets:** 44 px minimum height for `.nav-item`, buttons, checkboxes and row action icons at max-width 767 px. Keep a visible `:focus-visible` outline.
- **D4-6 Empty and loading states:** a shared `.empty-state` (icon, one line, one action) and a `.skeleton` placeholder shimmer that is disabled under `prefers-reduced-motion`.
- **D4-7 Motion:** 150 ms ease transitions on hover and state changes only; nothing animated on load; honour `prefers-reduced-motion`.
Each needs a visual check at 390 px width in light and dark.

## 6. D5: inline-style cleanup

Goal: reduce the 1,491 template and 205 JS inline styles without risking behaviour.
- **D5a ratchet:** new test `tests/test_inline_style_ratchet.py` with a baseline per template (and one for JS); counts may only go down, same mechanism as D1b. Dynamic styles that depend on data (widths, `display:none` toggles) are fine and stay.
- **D5b utilities:** add a small set of utility classes in `components.css` for the repeated patterns (flex row with gap, muted small text, margin-top steps from `--space-*`, `.hidden`). Replace inline styles in one template per run, in this order: `query_builder.html`, `schema_builder.html`, `settings.html`, `add.html`, `backup.html`. Update the baseline each run.
Done when: no behaviour change (suites green) and counts drop.

## 7. D6: widget colour and icon properties

Decision: allow `tone` and `icon` as optional widget keys. `tone` is a named token, never a hex value or arbitrary CSS. The key is named `tone`, not `color`, so nobody types a hex into it.

Example (any place a widget spec is written):

```toml
[spending]
view  = "chart"
tone  = "chart-3"
icon  = "wallet"
title = "Spending"
```

Allowed `tone` values: `accent`, `success`, `warn`, `error`, `sub`, `chart-1` to `chart-8`. Allowed `icon` values: a fixed list of about 16 names (for example `wallet`, `check`, `calendar`, `clock`, `heart`, `book`, `flag`, `home`, `note`, `chart`, `target`, `bell`, `repeat`, `search`, `star`, `tag`) drawn from one inline SVG sprite (for example Lucide, ISC licence). Unknown or invalid values produce a lint warning and the default look; they never fail the page.

### D6a: backend

Files: `ptos_widgets.py` (add `tone` and `icon` to `COMMON_KEYS`), `ptos_service.py` (value validation next to the existing key lint around line 3767), new `tests/test_widget_tone.py`.
- Valid tone and icon pass through the resolver into the rendered widget spec unchanged.
- Invalid values: a lint warning of the form `'tone' must be one of: accent, success, ...`, and the value is dropped from the spec.
- A widget with neither key behaves exactly as today (the existing widget tests stay green).
Suggested commit message: "Allow tone and icon on widgets".

### D6b: frontend

Files: `web_static/js/widgets.js`, `web_static/css/components.css`, new `web_static/icons.svg`.
- The widget card gets the class `tone-<token>` only when the token is in the allowlist. No inline style carries the value.
- CSS: `.tone-accent { --tone: var(--accent); }` and so on for each token; the widget header icon and a 3 px left border use `var(--tone, var(--accent))`.
- The icon renders from the sprite with `<use href="/static/icons.svg#name">`, only for allowlisted names.
Tests (JS): `tone: "chart-3"` yields `tone-chart-3` and no `style` attribute; `tone: "red;background:url(x)"` yields no tone class; `icon: "nope"` renders no icon.
Suggested commit message: "Render widget tone and icon".

### D6c: tokenize todo group colours

File: `web_static/js/widgets.js` (around lines 949 and 955, `g.color` in an inline style) and wherever the server sets group colour. Replace with a tone class under the same allowlist; groups with no valid tone use the default. Add a test that a group colour like `red;x:y` produces no style attribute.
Suggested commit message: "Replace todo group inline colours with tone tokens".

### D6d: swatch picker

File: the widget editor (gallery step 2) JS and template. A row of swatches for the allowed tones plus "none", and a simple icon chooser; selected values are written to the widget spec. Swatches are drawn with the `tone-*` classes, no inline colours.
Test (JS): choosing a swatch writes `tone = "<token>"` into the generated spec; choosing none removes the key.
Suggested commit message: "Add tone and icon pickers to the widget editor".

Out of scope: per-widget CSS, fonts, arbitrary hex colours, per-entry colours for habits, thresholds or boards (decide later, reuse the same tokens).

## 8. Risks

- Dark mode with unconverted colours looks broken; that is why D2a waits for D1d.
- Chart code may use hardcoded colours; D2a includes a check. Not verified.
- Cached CSS or fonts on the installed PWA; bump the service worker cache version (if one exists) with D2a and D3a. Not verified whether PTOS has a service worker precache list.
- The ratchet tests make an agent's life harder on purpose; if one blocks a legitimate change, record the reason in the baseline file instead of deleting the test.
- I have not seen any screenshots; the palette choices and the layout items are based on the code only.

## 9. Visual check (human)

After each visual task, check these pages at 390 px width and at 1440 px width, in light and dark (the first screenshots were desktop-wide, about 1650 to 1890 px): home, todo, routines, habits, calendar, board, a browse table with amounts, queries, settings, add. For each: text readable, no clipped content, buttons reachable, primary action obvious, nothing unthemed (white boxes in dark mode). Send screenshots of anything that looks off and the task can be adjusted.

## 10. Screenshot findings (10 screens, desktop width, 2026-11-04)

Screens reviewed: Home (two parts), Add Record, Todos, Routines, Browse, Queries, Board, Habits, Calendar. Dark mode and mobile width were not shown. Windows notification pop-ups visible in two shots are not part of the app.

### 10.1 Bugs and glitches (do these before the visual work)

Each is a small task. Reproduce first; if you cannot reproduce it, write that under Status.

- **B1 Run-together text.** Habits cards read `0-day streak0 of 10 daysNov 1 – Nov 4, 2026` (three pieces with no spacing). The Home "Overdue Records" row reads `Madhu S13d— ringing not respondingOpen ↗`. Add separators or spacing (a separator dot, or flex with a gap) in the habit summary renderer and the overdue-record row renderer. Test: the rendered HTML has the pieces in separate elements or separated by a space or `·`.
- **B2 Floating + button covers content.** On Todos, Routines, Browse, Board and Queries the round + button sits over the right edge: it hides the X on the last todo row, the row actions in the Browse table, and the end of the Routines rows. Fix: reserve bottom and right padding for it (for example `padding-bottom: 88px` on the page container), or hide it at widths of 1024 px and above where the sidebar has an Add entry.
- **B3 Tooltip overlaps a label.** In Browse, a small "domain" tooltip box sits on top of the "VALUES FOR domain" label. Fix the tooltip position or `z-index`, or drop the tooltip when the same text is already visible.
- **B4 Check the "Expense today" card.** On Home, EXPENSE and EXPENSE TODAY both show `15 (₹8,652)` with the caption "This month"; Browse for today shows 2 records, total ₹90. Either the card ignores the "today" window (the Home "Time window" control says "Default") or the caption and query are wrong. Find the query behind the card and fix it, with a test that the card's number matches the query's own result for the same window.
- **B5 Check completed days on the Habits grid.** "Maid attendance" says `3 of 10 days`, but the grid cells for Nov 2, 3 and 4 look identical to empty days in all three cards. Verify whether completed days are drawn in a different colour (they should use `--success` or the habit's tone). Fix if they are not.
- **B6 Check the repeated "Now" line.** On Routines the blue "Now: 10:32 AM" line appears at the top of the Afternoon and Evening sections as well as inside Morning. It should appear once, at the correct position. Verify and fix.

### 10.2 Design findings, mapped to the spec

| Finding | Where | Task |
|---|---|---|
| Page title sizes differ: Home headings are about 32 px, Todos, Routines, Browse, Queries and Board titles about 20 px, Habits and Calendar slightly different again | all pages | D4-1 |
| No maximum content width: Todo rows run 1,600 px wide with actions far from the text, the group-by tabs stretch across the whole page, Habits uses a narrower width than other pages | Todos, Routines, Habits, Board | new D4-8 below |
| Home stat cards use flat saturated fills (green, red, slate) that dominate the page | Home | D6 (`tone`): tinted background, coloured number, one larger hero metric |
| Five action icons on every todo row, always visible | Todos | new D4-9 below |
| Group headers are centred with the count at the far right | Todos | D4-1 |
| Group-by segmented control stretches to full width | Todos | D4-8 |
| Large empty space around collapsed "Quick pick" and "Saved views" | Todos | D4-2 |
| Routines rows use full-row pastel fills (pink, green, mint, orange, lavender) and a red "overdue" word on every row | Routines | new D4-10 below |
| Many record types share the same generic document icon; some use emoji, some line icons | Add Record, Browse | D6 (`icon` sprite) plus a per-type icon |
| Every quick preset carries a chip, a lightning button and an x button | Add Record, Home | new D4-11 below |
| 20+ type pills and 40+ query pills wrap over several lines | Browse, Queries | new D4-12 below |
| Board columns run to the bottom of the viewport when empty | Board | D4-2 (`min-height` instead of full height) |
| "Configure" links use the browser's default blue and purple underlined style and are clipped at the right edge on Habits and Calendar | Board, Habits, Calendar | D4-4 (one link style) |
| Calendar day chips read `expense · self · transport` and are cut off (`mutual fu…`) | Calendar | D6 tone per type; show category and amount only |
| Colourful sidebar icons and emoji icons coexist with plain line icons | everywhere | D6 sprite |

Things that already work and should be kept: the sidebar with its keyboard hints, the coloured top borders on the Queries sections, the threshold progress bars with OK and WARN labels, the highlighted today cell on Calendar, and the priority badges on Todos.

### 10.3 New layout and polish tasks

- **D4-8 Readable width.** Add a `--content-max` token (suggest 1200 px) and apply it to text-heavy pages (Todos, Routines, Habits, Calendar settings, Settings, Add). Dashboards (Home, Browse tables) may stay wide. Make the group-by control content-width, not full-width.
- **D4-9 Quieter todo rows.** Show the check circle, text, priority badge and due chip always; move play, stop, link, edit and delete into a "⋯" menu, or show them on row hover and focus (always visible on touch screens). Keep tap targets at 44 px on mobile.
- **D4-10 Routines tone.** Replace full-row pastel fills with a thin left bar plus a small tone chip using the `tone` tokens; show "overdue" as one small badge using `--error`, not the word on every row.
- **D4-11 Tidy quick presets.** Show only the preset chip; put the lightning and remove controls behind a "Manage presets" toggle.
- **D4-12 Tame pill lists.** For Browse types and Queries, show the first row of pills plus "Show all (N)" and a filter box; keep the selected pill visible.
