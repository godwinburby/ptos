# PTOS — Plain Text Operating System

> **New to PTOS?** See [README_START_HERE.md](README_START_HERE.md) for a plain-English overview.

> Log it. Query it. Own it.

Record and analyse life, work, and finance events using structured plain-text logs.
One Python file. No database. No dependencies beyond the standard library.

---

## What it is

Every event you record becomes one line in a plain-text `.log` file:

```
2026-03-10 type=expense domain=self category=food amount=120 tag=restaurant | lunch with team
2026-03-10 type=expense domain=self category=transport amount=90 tag=auto
2026-03-10 type=exercise activity=walk duration=30 tag=morning
```

Fields become dimensions for grouping and filtering. Numeric fields become measures for summing and averaging. All rules about what fields exist and what values they accept live in `schema.toml` — the Python script has no domain logic of its own.

---

## Anatomy of a record

Every record follows this exact structure:

```
2026-03-11  type=expense  domain=self category=food amount=120  tag=restaurant  | lunch with team
──────────  ────────────  ──────────────────────────────────────  ─────────────  ────────────────
date        type          fields                                  tag(s)         note
```

| Part | Required | Description |
|------|----------|-------------|
| date | yes | `YYYY-MM-DD` — always first |
| type | yes | what kind of event — always second |
| fields | yes | `key=value` pairs defined by schema for this type |
| tag | recommended | freeform labels for cross-cutting queries — `tag=auto tag=bus` |
| note | recommended | human context after `\|` that fields cannot capture |

A record missing a tag or note is valid but weak — `--lint` will warn you.
A record missing a date or type is broken — `--lint` will error.

---

## Requirements

- Python 3.11+ (uses `tomllib` from the standard library)
- Works on Windows, Linux, macOS, Android (Termux)

---

## Installation

`ptos.py` is a single self-contained file — it has no dependencies beyond Python 3.11+.

```bash
# 1. Download ptos.py to a folder of your choice
mkdir ~/ptos && cd ~/ptos
# (copy ptos.py here)

# 2. Initialise — creates all config files and the first log file
python ptos.py --init

# 3. Optional: add an alias
alias ptos="python ~/ptos/ptos.py"
```

`--init` is safe to run more than once. It will not overwrite existing files.

If you want the GUI front-end, also download `ptos_gui.pyw` into the same folder. The GUI requires `ptos.py` to be present alongside it — it imports it directly at runtime.

---

## Folder structure after init

```
ptos/
├── ptos.py
├── config/
│   ├── config.toml      ← editor, currency, billing cycles
│   ├── schema.toml      ← record types, field definitions, validation rules
│   ├── queries.toml     ← saved queries, metrics, dashboards, due config
│   └── presets.toml     ← quick-add shortcuts
├── records/
│   └── 2026.log         ← one file per year, append-only
├── journal/
│   └── 2026/
│       └── 2026-03-10.md
└── templates/
    └── daily.md
```

---

## GUI front-end (Windows)

For users who prefer not to use the terminal, PTOS includes a graphical interface — `ptos_gui.pyw` — that runs on any Windows machine with Python installed.

### Files

| File | Purpose |
|------|---------|
| `ptos.py` | The core engine — required by both CLI and GUI |
| `ptos_gui.pyw` | The GUI application — requires `ptos.py` in the same folder |
| `ptg.bat` | Windows launcher — runs the GUI without a console window |
| `ptos_init.bat` | First-time setup — creates folders, config files, and first log file |
| `README_START_HERE.md` | Plain-English guide for non-technical users |

### Launching

Double-click `ptg.bat`, or from the terminal:

```cmd
python ptos_gui.pyw
```

### Tabs

**+ Add Record** — schema-driven form that renders dynamically from `schema.toml`. Select a record type and all fields appear. Supports presets, date picker, tag checkboxes, and note. Validates the record before saving.

**Queries** — run any named query, metric, or dashboard from `queries.toml`. Selecting a query or changing the time window runs it immediately. Reload button refreshes the query list if `queries.toml` has changed.

**Browse** — filter records by type, time window, and field values. When a type is selected, dimension field dropdowns appear automatically for filtering. Also supports free-text search, sort, file selection, and a Group by dropdown for grouped output. Due List button shows overdue records from the `[due]` config in `queries.toml`. Export CSV exports current results. **Save as Query** saves the current filter state as a named query to `queries.toml` — accessible from the Queries tab immediately after saving.

**Journal** — daily journal editor. Opens today's journal automatically. Navigate with ◀ Prev / Next ▶ or click the date label / 📅 icon to jump to any date. Forward navigation is blocked past today. For past dates with no entry, a **+ Create Entry for This Date** button appears. Ctrl+S saves; Ctrl+Enter toggles checkbox items. Markdown syntax colouring for headings, checkboxes, bold, italic, and rules. A `.bak` backup is written before every save.

**Log Editor** — view and edit any `.log` file in the `records/` folder. A dropdown at the top lets you switch between files (one per year). Full undo support. Save with the button or Ctrl+S. A `.bak` backup is written automatically before every save.

### Add Record — form behaviour

- **Dropdowns** — fields with defined options render as dropdowns. Parent-dependent dropdowns (e.g. `category` depending on `domain`) update automatically when the parent changes.
- **Conditional fields** — fields that only apply under certain conditions appear and disappear automatically (e.g. `fit` appears only when `outcome=prescribed`).
- **Number fields** — `int` fields only accept digits. A unit label appears to the right (e.g. `₹` for `amount` and `advance`, `min` for `duration`).
- **Date picker** — click the 📅 icon to open a popup calendar. Navigate months with ◀ ▶, click a date to select. Today shortcut at the bottom.
- **Tags** — schema-defined tags appear as checkboxes. Additional custom tags can be typed as comma-separated values.
- **Text fields** — spaces are converted to underscores automatically before saving, since the plain-text log format uses spaces as field separators. Notes are exempt — spaces in notes are preserved.

### Presets in the GUI

The **Load preset** dropdown at the top of the Add Record form pre-fills the form with any preset from `presets.toml`. Only the fields defined in the preset are filled — blank fields stay empty for you to complete. Tags defined in the preset are ticked automatically.

The **Save as Preset** button (footer, next to Save Record) saves the current form state as a new preset. Only filled fields are saved — intentionally blank fields are omitted, so the preset will prompt for them when loaded. The preset dropdown refreshes immediately after saving.

### Unit labels in schema

To show a unit hint next to a numeric field, add a `unit` key to the field's global metadata in `schema.toml`:

```toml
[fields.amount]
type         = "int"
dimension    = false
aggregatable = true
unit         = "₹"

[fields.duration]
type         = "int"
dimension    = false
aggregatable = true
unit         = "min"
```

The `unit` key is ignored by `ptos.py` — it is only read by the GUI.

### Ignore patterns

Add these to Syncthing and `.gitignore` for the PTOS folder:

```
*.tmp
*.bak
ptos_error.log
```

### Error log

If the GUI crashes or a callback raises an error, the full traceback is written to `ptos_error.log` in the PTOS folder and shown in a popup with a **Copy to Clipboard** button. The app continues running after the error is dismissed.

### Requirements

Same as `ptos.py` — Python 3.11+, standard library only. No extra packages needed.

---

## Quick start

```bash
# Add a record
ptos --add type=expense domain=self category=food amount=120

# Add with a date (today is default)
ptos --add type=expense domain=self category=food amount=120 --date yesterday
ptos --add type=expense domain=self category=food amount=120 --date 2026-03-08

# Use a preset (shortcut for frequent entries)
ptos --preset commute
ptos --preset commute --date yesterday

# Interactive add (prompts for all fields)
ptos --add

# Run a saved query
ptos --query monthly_expenses

# Override a saved query's time window
ptos --query monthly_expenses --time last-month
ptos --query monthly_expenses --time last-quarter

# Open today's journal
ptos --journal

# Edit config files
ptos --edit s        # schema.toml
ptos --edit q        # queries.toml
ptos --edit c        # config.toml
ptos --edit p        # presets.toml
ptos --edit r        # this year's records log
ptos --edit d        # today's journal (same as --journal)
ptos --edit j        # same as --edit d
ptos --edit x        # ptos.py itself
```

---

## CLI reference

### Add

| Flag | Description |
|------|-------------|
| `--add [field=value ...]` | Add a record. No arguments = interactive mode |
| `--note "note text"` | Attach a note to the record |
| `--date DATE` | Date for the record. Accepts `YYYY-MM-DD`, `today`, `yesterday` (default: today) |
| `--preset [preset] [field=value ...]` | Quick-add from preset. Override fields inline |
| `--save-preset NAME` | Save the record being added as a preset under this name |

### Query

| Flag | Description |
|------|-------------|
| `--query [name]` | Run a saved query. No name = list all queries, metrics, dashboards |
| `--where field=value ...` | Filter by field. Overrides saved query filters |
| `--time TIME` | Time window (see below). Default: `this-month` |
| `--from YYYY-MM-DD` | Start date (use with `-T` for custom ranges) |
| `--to YYYY-MM-DD` | End date |
| `--type TYPE` | Filter by record type |
| `--tag TAG` | Filter by tag (repeatable: `--tag auto --tag bus`) |
| `--search text` | Full-text search |
| `--save NAME` | Save current query filters and analysis to queries.toml |
| `--file FILENAME` | Read from a specific file in `records/` folder (e.g. `2025.log`). Full filename with extension. No spaces. |
| `--select field ...` | Show only specified fields in output. Date, type, and note always included. Log format preserved. |

### Analyse

| Flag | Description |
|------|-------------|
| `--group field [field ...]` | Group by one or more fields |
| `--pivot ROW COL` | Pivot table |
| `--count` | Count records instead of summing numeric fields |
| `--sort COL` | Sort records or pivot rows by a column. Works for plain list, table view, and pivot |
| `--trend [N]` | Show last N periods side by side (default: 6) |
| `--due [NAME\|DAYS]` | Show overdue records. Optional: named due config or days override |
| `--table` | Display results as a formatted table instead of raw lines |
| `--export [FILENAME]` | Export results to CSV in `exports/` folder. Optional filename without extension. Auto-named if omitted. |

### Utilities

| Flag | Description |
|------|-------------|
| `--lint` | Lint all records against schema |
| `--journal` | Open today's journal (creates from template if new) |
| `--edit [TARGET]` | Edit a workspace file — r s q c p d/j x |
| `--fields` | Field discovery report for current results |
| `--init` | Initialise workspace |

---

## Time windows

| Keyword | Range |
|---------|-------|
| `today` | Today only |
| `yesterday` | Yesterday only |
| `this-week` | Monday to Sunday |
| `last-week` | Previous Monday to Sunday |
| `this-month` | 1st to last day of current month |
| `last-month` | Previous calendar month |
| `this-quarter` | Current calendar quarter |
| `last-quarter` | Previous calendar quarter |
| `this-year` | Jan 1 to Dec 31 |
| `last-year` | Previous year |
| `YYYY-MM` | Specific month, e.g. `2026-03` |
| `all` | No date filter |
| Custom cycles | Defined in `config.toml` — e.g. `salary`, `salary-1` |

Short aliases are available for faster typing:

| Alias | Expands to |
|-------|------------|
| `td` | `today` |
| `yd` | `yesterday` |
| `tw` | `this-week` |
| `lw` | `last-week` |
| `tm` | `this-month` |
| `lm` | `last-month` |
| `tq` | `this-quarter` |
| `lq` | `last-quarter` |
| `ty` | `this-year` |
| `ly` | `last-year` |

```bash
ptos --query monthly_expenses --time lm       # last month
ptos --query monthly_expenses --time tq       # this quarter
ptos --type expense --time td                 # today
ptos --query monthly_expenses --trend --time tm
```

Custom cycles let you define a billing or reporting period that starts on a fixed day of the month rather than the 1st. `salary-1` means one cycle back, `salary-2` two cycles back, and so on.

```toml
# config.toml
[cycles]
salary = 26   # cycle runs 26th → 25th next month
billing = 1   # same as calendar month
```

---

## Schema

The schema is the only file you need to edit to make PTOS work for your domain. Everything else — the engine, queries, presets — adapts automatically.

### Every type follows the same four-section pattern

```toml
[type.expense]
required = ["domain", "category", "amount"]   # flat list

[type.expense.fields.domain]
options = ["self", "home", "work"]             # flat options

[type.expense.fields.category]
parent       = "domain"                        # options depend on domain
options.self = ["food", "transport", "health"]
options.home = ["grocery", "utilities", "rent"]
options.work = ["admin", "supplies", "meals"]

[type.expense.tags.category]                   # tags triggered by field value
options.food      = ["snacks", "coffee", "restaurant"]
options.transport = ["auto", "bus", "taxi"]

[type.sale.conditions.warranty]                 # conditionally required field
when = { category = "appliance" }              # warranty required only for appliances
```

### Shared field definitions — define once, reuse everywhere

```toml
[shared.source]
options = ["referral", "walkin", "online", "marketing"]

# Then in any type:
[type.lead.fields.source]
use = "shared.source"

[type.sale.fields.source]
use = "shared.source"
```

Changing `shared.source` updates it everywhere it's referenced.

### Global field metadata

Fields declared in `[fields]` control how PTOS handles them across all types:

```toml
[fields.amount]
type         = "int"          # validated as integer, summed in group/pivot
dimension    = false          # excluded from grouping suggestions
aggregatable = true

[fields.tag]
type      = "string"
dimension = true
multi     = true              # a record can have multiple tag= entries
```

---

## Queries

### Base queries — reusable filters

```toml
[expenses]
where = "type=expense"

[food]
where = "type=expense category=food"
```

### Metrics — computed over base queries

```toml
[metrics.food_ratio]
ratio = ["food", "expenses"]     # food spend as % of total expenses

[metrics.avg_spend]
avg = "expenses"                 # average spend per record

[metrics.total_spend]
sum = "expenses"                 # total amount across all matched records

[metrics.highest_spend]
max = "expenses"                 # highest single record amount

[metrics.lowest_spend]
min = "expenses"                 # lowest single record amount
```

`avg` also supports weighted averaging via `unit_field` and `unit_weights` — see the weighted average section below.

### Dashboards — named collection of metrics and base queries

```toml
[dashboards.monthly]
metrics = ["leads", "sales", "conversion_ratio", "avg_sale"]
```

Run with: `ptos --query monthly`

### Saved queries — any combination of filters, time, analysis

```toml
[monthly_expenses]
where = "type=expense"
time  = "this-month"
sum   = true

[expense_funnel]
where = "type=lead"
time  = "this-quarter"
pivot = ["source", "outcome"]
count = true

[exp_cat]
where = "type=expense domain!=work"
time  = "this-month"
group = ["category"]

[sales_trend]
where = "type=sale"
time  = "this-month"
trend = 6          # run as trend automatically when queried
sum   = true
```

**Saved queries compose with `--time`** — the saved query defines the default time, but you can always override it at the CLI:

```bash
ptos --query monthly_expenses                       # uses the query's own time setting
ptos --query monthly_expenses --time last-month     # same filters, different window
ptos --query monthly_expenses --time last-quarter
ptos --query monthly_expenses --time 2026-01
```

**Save any CLI command as a query with `--save`** — the query runs normally and is appended to queries.toml in one step:

```bash
ptos -w type=expense domain!=work -G category -t tm --save exp_cat
ptos -w type=sale --trend 6 -t tm --save sales_trend
ptos -y lead -t tq -v source outcome --count --save funnel
```

---

## Trend analysis

`--trend` runs your filters across the last N consecutive periods and shows them side by side. Works with any time window that has a natural predecessor.

```bash
# Expenses over last 6 months (default)
ptos --where type=expense --trend

# Expenses by calendar month, last 3 months
ptos --where type=expense --trend 3 --time this-month

# Work expenses over last 4 months
ptos --where type=expense domain=work --trend 4 --time this-month

# Any saved query + trend
ptos --query monthly_expenses --trend
```

Output:

```
Trend: type=expense

period              count      total        avg
-----------------------------------------------
2025-10                12      ₹3,840       ₹320
2025-11                14      ₹4,210       ₹300
2025-12                10      ₹3,100       ₹310
2026-01                12      ₹3,964       ₹330
2026-02                14      ₹4,793       ₹342
2026-03                10      ₹2,153       ₹215
```

Supported time windows for `--trend`: custom cycles (e.g. `salary`, `salary-1`…), `this-month`, `last-month`, `this-week`, `this-quarter`, `YYYY-MM`.

---

## Table view

`--table` renders results as a formatted table instead of raw log lines.

```bash
ptos -y expense -t tm --table
ptos -q leads --table --sort name
ptos -w type=sale -t tq --table
```

Columns are auto-detected from the fields present in the result set. When results contain multiple record types, each type gets its own sub-table with only its relevant columns shown — no empty cells from mismatched fields.

```
[ expense ]
date        domain  category   amount  tag      note
-----------------------------------------------------
2026-03-10  work    food       32      snacks   coffee and biscuits
2026-03-11  home    grocery    190     fruits   weekly fruits

[ sale ]
date        client  name         product          amount  advance  category
--------------------------------------------------------------------------
2026-01-03  Al001   alice_m      comfort_pro_l    83000   10000    appliance
2026-01-10  Bo002   bob_k        comfort_pro_xl   98000   98000    appliance
```

Width is adaptive — if the full table fits in your terminal, nothing is truncated. If the terminal is too narrow, the `note` column shrinks first, then other wide columns, with a minimum of 6 characters per column.

`--sort` works with `--table` and with plain list view. Numbers sort numerically, strings sort alphabetically. Records missing the sort field sort last.

```bash
ptos -q leads --table --sort name      # alphabetical by name
ptos -q leads --table --sort status    # by status field
ptos -y expense -t tm --table --sort amount   # low to high
```

---

## Due list

`--due` scans a configured record type, finds the most recent entry per unique key (e.g. client), and surfaces those not updated within N days — sorted by priority.

Priority order is read directly from your schema field options. The first option in the list is the most urgent. No hardcoding in the script.

### Configure in queries.toml

You can have a single default `[due]` block, or multiple named configs under `[due.NAME]`:

```toml
# default — used by: ptos --due
[due]
type            = "lead"       # record type to scan
key             = "client"     # field that identifies each unique entity
sort_by         = "status"     # field whose schema option order defines priority
days            = 7            # default overdue threshold
exclude_results = ["fix_appointment", "deceased"]  # skip these result values entirely

# named — used by: ptos --due outreach
[due.outreach]
type    = "outreach"
key     = "place"
days    = 14
```

The `sort_by` field's options in `schema.toml` define the priority order:

```toml
[type.lead.fields.status]
options = ["trial", "decision", "negotiation", "deferred", "unattended"]
#           ↑ most urgent                                 ↑ least urgent
```

### Usage

```bash
ptos --due                  # use default [due] block, default days
ptos --due 3                # use default [due] block, override to 3 days
ptos --due 0                # show everyone (morning review)
ptos --due outreach         # use [due.outreach] named config
```

Output:

```
Due  (>3 days)  type=lead

   last  status      client          note
--------------------------------------------------------------------
      5d  trial       alice_m         trialling comfort_pro, happy so far
      5d  decision    bob_k           discussing with family
      4d  negotiation carol_r         said will call back next week
      3d  negotiation david_s         takes calls, asks for discount
```

### Adapting for other domains

A sales person tracking leads:

```toml
[due]
type    = "lead"
key     = "company"
sort_by = "status"
days    = 3
```

A habit tracker:

```toml
[due]
type    = "habit"
key     = "name"
sort_by = "category"
days    = 30
```

---

## Journal

`--journal` (or `--edit j` / `--edit d`) opens today's journal in your editor. If the file does not exist it is created from a template automatically.

```bash
ptos --journal        # open today's journal
ptos -j               # same, short form
ptos --edit j         # same via edit shortcut
```

The built-in template follows an ARRIVE → ENGAGE → RELEASE structure:

- **ARRIVE** — ground yourself before the day starts: reality check, body, mood, a word or verse, intention, prayer
- **ENGAGE** — top 3 tasks, home/personal item, one person to love well, habits, drift checks at 11 / 2 / 5
- **RELEASE** — end of day: wins, where you drifted, gratitude, one thing to carry forward

The template is embedded in `ptos.py` so it works even without a `templates/daily.md` file. If you place your own `templates/daily.md` that will be used instead.

Journal files are stored at `journal/YYYY/YYYY-MM-DD.md` — one file per day, plain markdown.

---

## Presets

Shortcuts for entries you add frequently. Any field can be omitted — PTOS will prompt for it interactively.

```toml
[presets.commute]
type     = "expense"
domain   = "self"
category = "transport"
amount   = 90
tag      = ["auto"]

[presets.snacks]
type     = "expense"
domain   = "work"
category = "staff_welfare"
tag      = ["snacks"]
# amount omitted — will be prompted each time
```

**Save a preset directly from the command line** using `--save-preset`:

```bash
# inline add — record is saved and preset is created in one step
ptos --add type=expense domain=work category=staff_welfare tag=snacks --save-preset snacks

# interactive add — skips the end-of-session prompt, uses the provided name directly
ptos --add --save-preset my_preset
```

Override any preset field inline:

```bash
ptos --preset commute amount=120        # different amount
ptos --preset commute tag=uber          # different tag
ptos --preset commute --date yesterday  # different date
```

---

## Analysis examples

```bash
# Group expenses by category this month
ptos --type expense --group category

# Group by domain and category together
ptos --type expense --group domain category

# Group expenses by month over the year
ptos --type expense --time this-year --group month

# Pivot expenses: domain vs category
ptos --type expense --pivot domain category --count

# Pivot leads: source vs outcome, summing amount
ptos --type lead --pivot source outcome

# Discover what fields are available in your current results
ptos --type expense --fields

# Discover available group fields
ptos --type expense --group ?

# Discover available pivot fields
ptos --type expense --pivot ?
```

---

## Filter expressions

Filters go with `-w` or inside `where =` in queries.

```bash
ptos --where type=expense                        # equality
ptos --where type=expense domain=self            # multiple filters (AND)
ptos --where type=expense domain!=work           # not equal
ptos --where type=expense amount>=500            # numeric comparison
ptos --where type=expense tag=restaurant         # tag match
ptos --where type=sale product~comfort      # field contains text
ptos --where type=sale product~comfort --group product  # group by variant
```

Operators: `=` `!=` `>` `<` `>=` `<=` `~` (contains, case-insensitive)

The `~` operator is useful when field values share a common prefix — for example `product~comfort` matches `comfort_pro_l`, `comfort_pro_xl`, and any future comfort variants without listing each one.

**OR values** — use `|` to match any of several values on `=` and `!=`:

```bash
ptos --where domain=self|home                    # self OR home
ptos --where type=assessment|prescription        # two types
ptos --where outcome!=deferred|not_interested    # exclude both
```

Works in saved queries too: `where = "type=expense domain=self|home"`

---

## Reading from a specific file

By default PTOS reads all `.log` files in `records/`. Use `--file` to read from one specific file — useful for querying a past year or an archive.

```bash
ptos -y expense --file 2025.log              # all expenses from 2025.log
ptos -y expense --file 2025.log -t lq        # last quarter of 2025
ptos --file archive.log -w type=sale         # query an archive file
```

The full filename including extension is required. No spaces allowed. The file must exist in the `records/` folder.

---

## Selecting output fields

By default PTOS prints the full raw record line. Use `--select` to show only the fields you care about. Date, type, and note are always included regardless of what you specify.

```bash
ptos -y followup -t tm --select name intent result
ptos -y followup -t tm --select name intent result --table
ptos -y followup -t tm --select name intent --sort intent
```

Output keeps log format with only the selected fields:

```
2026-03-11 type=followup name=george_joseph intent=trial | will call back next week
2026-03-11 type=followup name=alice_m intent=decision | discussing with family
```

`--select` works with `--table`, `--sort`, and `--due`. Position in the command does not matter.

---

## Exporting to CSV

`--export` saves results to a `.csv` file in the `exports/` folder next to `records/`.

```bash
ptos -y expense -t tm --export              # exports/expense_this-month.csv
ptos -y expense -t tm --export march_spend  # exports/march_spend.csv
ptos -q flp -t tq --export                  # exports/followup_this-quarter.csv
ptos -y prescription --export               # exports/prescription_this-month.csv
```

Auto-naming uses the active type filter and time label so the filename tells you what's in it. All filters, `--select`, and `--sort` apply before export — what you see is what gets exported.

Columns are auto-detected from fields present in results. Multi-value fields like `tag` are joined with a comma. The file can be opened directly in Excel or any spreadsheet app.

---

## Configuration

### config.toml

```toml
[editor]
command = "nvim"        # falls back to $EDITOR, then notepad/nvim by OS

[display]
currency = "₹"          # prefix shown on all numeric output

[cycles]
salary = 26             # billing cycle starting on the 26th
```

### PTOS_HOME environment variable

By default PTOS places all files next to `ptos.py`. Set `PTOS_HOME` to use a different location:

```bash
export PTOS_HOME=/data/ptos    # Linux / macOS / Termux
set PTOS_HOME=C:\ptos          # Windows
```

Useful when you want to keep the script somewhere on `PATH` but your data in a synced folder.

---

## Validation

```bash
ptos --lint          # check all records against schema
```

Lint catches: missing required fields, invalid field values, unknown fields, conditional required violations (e.g. `warranty` missing when `category=appliance`).

---

## Sharing and sync

Records are plain text — one line per entry, one file per year. They work well with any sync tool:

- **Git** — commit `records/` after each session. Full history, diff-friendly.
- **Syncthing / Dropbox / iCloud** — sync the whole `ptos/` folder.
- **Termux** — run the same script on Android. Set `PTOS_HOME` to your synced folder.

Multiple devices can safely append to the same log file as long as writes don't overlap. For teams, keep one canonical copy and merge with `sort -u`.

---

## Adding a new record type

1. Add the type name to `[types] allowed` in `schema.toml`
2. Define `required`, `fields`, and optionally `tags` and `conditions`
3. Run `ptos --lint` to verify existing records still pass
4. Optionally add saved queries in `queries.toml` and presets in `presets.toml`

Example — adding a `mood` type from scratch:

```toml
# schema.toml

[types]
allowed = [..., "mood"]

[type.mood]
required = ["rating", "context"]

[type.mood.fields.rating]
options = ["1", "2", "3", "4", "5"]

[type.mood.fields.context]
options = ["work", "home", "social", "health", "travel"]
```

```toml
# queries.toml
[mood_today]
where = "type=mood"
time  = "today"
```

```bash
ptos --add type=mood rating=4 context=work
ptos --query mood_today
ptos --type mood --time this-week --group context
```
