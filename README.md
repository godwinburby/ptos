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
- Web UI additionally requires Flask: `pip install flask`

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

---

## Folder structure after init

```
ptos/
├── ptos.py              # Core CLI engine
├── ptos_service.py      # Data layer (used by web UI and GUI)
├── ptos_web.py          # Web UI (optional)
├── ptos_gui.pyw         # Desktop GUI (optional, Windows)
├── config/
│   ├── config.toml      # Editor, currency, cycles, dashboard
│   ├── schema.toml      # Record types, fields, validation
│   ├── queries.toml     # Saved queries, metrics, dashboards, due
│   └── presets.toml     # Quick-add shortcuts
├── records/
│   └── 2026.log         # One file per year
├── exports/             # CSV exports land here
├── web_templates/       # HTML templates for web UI
├── journal/
│   └── 2026/
│       └── 2026-03-10.md
└── templates/
    └── daily.md         # Journal template (optional override)
```

---

## Quick start

```bash
# Add a record
ptos --add type=expense domain=self category=food amount=120

# Add with a specific date (today is default)
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

# Edit config files in your editor
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

| Flag | Short | Description |
|------|-------|-------------|
| `--add [field=value ...]` | `-a` | Add a record. No arguments = interactive mode |
| `--note "note text"` | `-n` | Attach a note to the record |
| `--date DATE` | `-d` | Date for the record. Accepts `YYYY-MM-DD`, `today`, `yesterday` (default: today) |
| `--preset [name] [field=value ...]` | `-p` | Quick-add from preset. Override fields inline |
| `--save-preset NAME` | | Save the record being added as a preset under this name |

### Query

| Flag | Short | Description |
|------|-------|-------------|
| `--query [name]` | `-q` | Run a saved query. No name = list all queries, metrics, dashboards |
| `--where expr ...` | `-w` | Filter expressions. Simple: `field=value`. Boolean: `"field=a AND field!=b"` |
| `--time TIME` | `-t` | Time window (see below). Default: `this-month` |
| `--from YYYY-MM-DD` | `-f` | Start date (use with `--to` for custom ranges) |
| `--to YYYY-MM-DD` | `-T` | End date |
| `--type TYPE` | `-y` | Filter by record type |
| `--tag TAG` | `-g` | Filter by tag (repeatable: `--tag auto --tag bus`) |
| `--search text` | `-S` | Full-text search |
| `--save NAME` | | Save current query filters and analysis to queries.toml |
| `--file FILENAME` | | Read from a specific file in `records/` (e.g. `2025.log`) |
| `--select field ...` | | Show only specified fields. Date, type always included; add `note` to include notes |

### Analyse

| Flag | Short | Description |
|------|-------|-------------|
| `--group field [field ...]` | `-G` | Group by one or more fields. Counts records; sums numeric fields when present |
| `--group ?` | | Discover available group fields for current results |
| `--pivot ROW COL` | `-v` | Pivot table |
| `--pivot ?` | | Discover available pivot fields |
| `--count` | | Count records instead of summing numeric fields. Works with `--group` and `--pivot` |
| `--sort COL` | | Sort results or pivot rows by a column |
| `--sum-field FIELD` | | Sum a specific numeric field instead of auto-detecting |
| `--trend [N]` | | Show last N periods side by side (default: 6) |
| `--due [NAME\|DAYS]` | | Show overdue records. Optional: named due config or days override |
| `--table` | | Display results as a formatted table instead of raw lines |
| `--export [FILENAME]` | | Export to CSV in `exports/`. Auto-named if no filename given |
| `--fields` | | Field discovery report for current results |

### Edit / Delete

| Flag | Description |
|------|-------------|
| `--set key=value ...` | Edit matched records. Shows diff and asks for confirmation |
| `--set key+=value` | Append a value to a list field (e.g. add a tag) |
| `--set key-=value` | Remove a value from a list field |
| `--set key=` | Delete a field entirely (empty value) |
| `--set date=YYYY-MM-DD` | Change the date — moves record to the correct year file automatically |
| `--set-note "text"` | Replace the note on matched records |
| `--delete` | Delete matched records |
| `--all` | Apply `--set` or `--delete` to all matched records without interactive pick |

`--set` and `--delete` require at least one filter (`--where`, `--type`, or `--tag`).
When multiple records match and `--all` is not given, PTOS lists them and asks you to pick by number.

```bash
# Fix a typo in a field
ptos -y expense -t td --set category=food

# Add a tag to a specific record
ptos -w "type=expense domain=self" -t td --set tag+=urgent

# Remove a tag
ptos -w type=followup --set tag-=pending

# Change the date of a record (moves to correct year file if needed)
ptos -w "type=expense amount=120" --set date=2026-03-15

# Replace the note
ptos -y expense -t td --set-note "corrected note here"

# Delete all of today's test records
ptos -y test -t td --delete --all
```

### Utilities

| Flag | Short | Description |
|------|-------|-------------|
| `--lint` | `-l` | Lint all records against schema |
| `--lint --fix` | | Open each log file that has errors in the editor after linting |
| `--journal` | `-j` | Open today's journal (creates from template if new) |
| `--edit [TARGET]` | `-e` | Edit a workspace file — `r s q c p d/j x` |
| `--init` | | Initialise workspace (safe to re-run — will not overwrite existing files) |

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
| Custom cycles | Defined in `config.toml` — e.g. `clinic`, `clinic-1` |

Short aliases:

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

Custom cycles let you define a billing or reporting period that starts on a fixed day of the month rather than the 1st. `clinic-1` means one cycle back, `clinic-2` two cycles back, and so on.

```toml
[cycles]
clinic = 26    # billing cycle starting on the 26th of each month
```

---

## Filter expressions

Filters go with `-w` / `--where`, or inside `where =` in saved queries.

```bash
ptos --where type=expense                        # equality
ptos --where type=expense domain=self            # multiple conditions (AND)
ptos --where type=expense domain!=work           # not equal
ptos --where type=expense amount>=500            # numeric comparison
ptos --where type=expense tag=restaurant         # tag match
ptos --where "type=sale product~comfort"         # field contains (case-insensitive)
```

**Operators:** `=` `!=` `>` `<` `>=` `<=` `~` (contains) `!~` (not contains)

**OR values** — use `|` to match any of several values on `=` and `!=`:

```bash
ptos --where domain=self|home                    # self OR home
ptos --where type=assessment|prescription        # two types
ptos --where outcome!=deferred|not_interested    # exclude both
```

**Boolean expressions** — full `AND`, `OR`, `NOT`, and parentheses:

```bash
ptos --where "(category=home OR category=household) AND amount>100"
ptos --where "type=expense AND NOT domain=work"
ptos --where "(tag=auto OR tag=bus) AND domain=self"
```

Boolean expressions and simple `field=value` conditions can be mixed freely. Works in saved queries too:

```toml
[home_spend]
where = "type=expense AND (domain=self OR domain=home)"
```

**Derived fields in filters** — virtual fields computed per record are fully filterable:

```bash
ptos -y followup --where is_overdue=true         # all overdue followups
ptos -y followup --where "is_overdue=true AND intent=trial"
ptos -y expense --where "days_since>30"          # global derived field
```

---

## Table view

`--table` renders results as a formatted table instead of raw log lines.

```bash
ptos -y expense -t tm --table
ptos -q leads --table --sort name
ptos -w type=sale -t tq --table
```

Columns are auto-detected from the fields present in the result set. When results contain multiple record types, each type gets its own sub-table — no empty cells from mismatched fields.

```
[ expense ]
date        domain  category   amount  tag      note
-----------------------------------------------------
2026-03-10  work    food       32      snacks   coffee and biscuits
2026-03-11  home    grocery    190     fruits   weekly fruits

[ sale ]
date        client  name         product          amount  advance
-----------------------------------------------------------------
2026-01-03  Al001   alice_m      comfort_pro_l    83000   10000
2026-01-10  Bo002   bob_k        comfort_pro_xl   98000   98000
```

Width is adaptive — `note` column shrinks first when the terminal is narrow. `--sort` sorts numerically or alphabetically; records missing the sort field sort last.

---

## Derived fields

Fields whose values are computed from other fields or date arithmetic. Defined in `schema.toml`, available automatically in `--table` output and in filters.

**Global derived fields** — apply to any record type:

```toml
[fields.days_since]
derived = "today - date"
type    = "int"
```

**Type-scoped derived fields** — apply only to a specific type:

```toml
[type.followup.fields.is_overdue]
derived = "(today - date) > 30"
type    = "bool"

[type.prescription.fields.balance]
derived = "amount - advance"
type    = "int"
```

Expressions support: `today`, `date`, `today - date` (returns days as int), and any numeric field from the record. Boolean results display as `true`/`false`.

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
avg = "expenses"                 # average amount per record

[metrics.total_spend]
sum = "expenses"                 # total amount across matched records

[metrics.highest_spend]
max = "expenses"                 # highest single record

[metrics.lowest_spend]
min = "expenses"                 # lowest single record
```

`avg` also supports weighted averaging — useful when records represent different unit counts:

```toml
[metrics.asp]
avg          = "prescriptions"
unit_field   = "fit"
unit_weights = { monaural = 1, binaural = 2 }
```

### Derived metrics — arithmetic over other metrics and base queries

```toml
[metrics.balance]
derived = "income - expense - investment"

[metrics.net_clinic]
derived = "total_revenue - expense_work"

[metrics.savings_rate]
derived = "balance / income * 100"
```

Tokens in the expression can be **other metrics** (e.g. `total_revenue`) or **base queries directly** (e.g. `income`, `expense`). Base queries used in derived metrics yield their numeric total. The base query's own time window applies when it has one defined.

### Dashboards — named collections of metrics and queries

```toml
[dashboards.clinic]
metrics = ["assessments", "prescriptions", "total_revenue", "asp", "prescription_ratio"]
```

Run with: `ptos --query clinic`

### Saved queries — any combination of filters, time, and analysis

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
trend = 6
```

**Override time at runtime** — the saved query defines the default, you can always change it:

```bash
ptos --query monthly_expenses                       # uses the query's own time
ptos --query monthly_expenses --time last-month
ptos --query monthly_expenses --time 2026-01
```

**Save any CLI command as a query with `--save`:**

```bash
ptos -w type=expense domain!=work -G category -t tm --save exp_cat
ptos -w type=sale --trend 6 -t tm --save sales_trend
ptos -y lead -t tq -v source outcome --count --save funnel
```

---

## Trend analysis

`--trend` runs your filters across the last N consecutive periods and shows them side by side.

```bash
ptos --where type=expense --trend
ptos --where type=expense --trend 3 --time this-month
ptos --where type=expense domain=work --trend 4 --time this-month
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

Supported time windows for `--trend`: custom cycles, `this-month`, `last-month`, `this-week`, `this-quarter`, `YYYY-MM`.

---

## Due list

`--due` scans a configured record type, finds the most recent entry per unique key (e.g. client), and surfaces those not updated within N days — sorted by priority.

Priority order is read from your schema field options. The first option listed is the most urgent. No hardcoding in the script.

### Configure in queries.toml

```toml
# default — used by: ptos --due
[due]
type            = "followup"
key             = "client"
sort_by         = "intent"
days            = 7
exclude_results = ["fix_appointment", "deceased", "not_relevant"]

# named — used by: ptos --due outreach
[due.outreach]
type    = "outreach"
key     = "place"
days    = 14
```

The `sort_by` field's options in `schema.toml` define priority order:

```toml
[type.followup.fields.intent]
options = ["trial", "decision", "assessment", "mgm"]
#           ↑ most urgent                   ↑ least urgent
```

### Usage

```bash
ptos --due                  # default [due] config, default days
ptos --due 3                # override threshold to 3 days
ptos --due 0                # show everyone (morning review)
ptos --due outreach         # use [due.outreach] named config
```

---

## Presets

Shortcuts for entries you add frequently. Any field can be omitted — PTOS will prompt for it.

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

**Save a preset from the command line:**

```bash
ptos --add type=expense domain=work category=staff_welfare tag=snacks --save-preset snacks
ptos --add --save-preset my_preset    # interactive add, named preset saved immediately
```

**Override any preset field inline:**

```bash
ptos --preset commute amount=120
ptos --preset commute tag=uber
ptos --preset commute --date yesterday
```

Tags are always prompted when using a preset — existing tags are shown first so you can keep or extend them.

### Preset aliases

```toml
[presets.c]
alias = "commute"    # ptos -p c  runs the commute preset
```

### Multi-record presets

```toml
[presets.morning]
records = [
  { type = "exercise", activity = "walk", duration = "30", tag = ["morning"] },
  { type = "learning", topic = "stoicism", source = "podcast", domain = "self" },
]
```

```bash
ptos -p morning         # prompts for missing fields in each record, saves both
ptos -p morning -d yd   # both records dated yesterday
```

---

## Exporting to CSV

`--export` saves results to the `exports/` folder. Works in all output modes.

```bash
ptos -y expense -t tm --export                  # exports/expense_this-month.csv
ptos -y expense -t tm --export march_spend      # exports/march_spend.csv
ptos -y expense -t tm -G category --export      # exports/expense_this-month_grouped.csv
ptos -y sale -t tq -v source outcome --export   # exports/sale_this-quarter_pivot.csv
```

All filters, `--select`, `--sort`, and `--sum-field` apply before export — what you see is what gets exported. Multi-value fields like `tag` are joined with a comma.

---

## Summing a specific field

By default PTOS auto-detects the first numeric field and sums it. Use `--sum-field` when a record type has more than one numeric field.

```bash
ptos -y sale -t tm --sum-field advance
ptos -y sale -t tm --group category --sum-field advance
ptos -y sale -t tm --pivot source category --sum-field amount
```

`--sum-field` works with list view, `--group`, `--pivot`, `--trend`, and `--export`.

---

## Reading from a specific file

```bash
ptos -y expense --file 2025.log              # all expenses from 2025.log
ptos -y expense --file 2025.log -t lq        # last quarter from that file
ptos --file archive.log -w type=sale         # query an archive
```

Full filename including extension is required. No spaces. The file must exist in `records/`.

---

## Selecting output fields

```bash
ptos -y followup -t tm --select name intent result
ptos -y followup -t tm --select name intent result --table
ptos -y followup -t tm --select name intent --sort intent
```

Date and type are always included. Add `note` to `--select` to include notes.

---

## Analysis examples

```bash
# Group expenses by category this month
ptos --type expense --group category

# Group by multiple fields
ptos --type expense --group domain category

# Group expenses by month over the year
ptos --type expense --time this-year --group month

# Pivot: domain vs category
ptos --type expense --pivot domain category --count

# Pivot with amount sums
ptos --type sale -t tq -v source outcome

# Trend: expenses over last 6 months
ptos --where type=expense --trend

# Discover what fields are available
ptos --type expense --fields
ptos --type expense --group ?
ptos --type expense --pivot ?
```

---

## Validation

```bash
ptos --lint          # check all records against schema
ptos --lint --fix    # open files with errors in the editor
```

Lint catches: missing required fields, invalid field values, unknown fields, conditional required violations (e.g. `fit` missing when `outcome=prescribed`).

---

## Journal

`--journal` opens today's journal in your editor. Creates the file from a template if it doesn't exist.

```bash
ptos --journal        # open today's journal
ptos -j               # short form
ptos --edit j         # same via edit shortcut
```

The built-in template follows an ARRIVE → ENGAGE → RELEASE structure:

- **ARRIVE** — ground yourself before the day: reality check, body, mood, a word or verse, intention, prayer
- **ENGAGE** — top 3 tasks, home item, one person to love well, habits, drift checks at 11 / 2 / 5
- **RELEASE** — end of day: wins, where you drifted, gratitude, one thing to carry forward

The template is embedded in `ptos.py` — it works without a `templates/daily.md` file. Place your own `templates/daily.md` to override it.

Journal files are stored at `journal/YYYY/YYYY-MM-DD.md`.

---

## Configuration

### config.toml

```toml
[editor]
command = "nvim"        # falls back to $EDITOR, then notepad/nvim by OS

[display]
currency = "₹"          # prefix shown on all numeric output

[cycles]
clinic = 26             # billing cycle starting on the 26th

[dashboard]
default = "clinic"      # default dashboard shown on web UI home page
```

### PTOS_HOME environment variable

By default PTOS places all files next to `ptos.py`. Set `PTOS_HOME` to use a different location:

```bash
export PTOS_HOME=/data/ptos    # Linux / macOS / Termux
set PTOS_HOME=C:\ptos          # Windows
```

Useful when the script is on `PATH` but data lives in a synced folder.

---

## Automatic backups

Every write operation — `--add`, `--preset`, `--set`, `--delete`, log editor saves from both the web UI and the GUI, and journal saves — creates a `.bak` file alongside the original before writing. For example, before modifying `records/2026.log`, PTOS writes `records/2026.log.bak`.

Add `*.bak` to your `.gitignore` and Syncthing ignore patterns.

---

## Sharing and sync

Records are plain text — one line per entry, one file per year.

- **Git** — commit `records/` after each session. Full history, diff-friendly.
- **Syncthing / Dropbox / iCloud** — sync the whole `ptos/` folder.
- **Termux** — run the same script on Android. Set `PTOS_HOME` to your synced folder.

Multiple devices can safely append to the same log file as long as writes don't overlap.

---

## Adding a new record type

1. Add the type name to `[types] allowed` in `schema.toml`
2. Define `required`, `fields`, and optionally `tags` and `conditions`
3. Run `ptos --lint` to verify existing records still pass
4. Optionally add saved queries in `queries.toml` and presets in `presets.toml`

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

---

## Unit labels in schema

To show a unit hint next to a numeric field in the web UI and GUI add forms:

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

The `unit` key is read by the web UI and GUI only — `ptos.py` ignores it.

---

## Web Interface

`ptos_web.py` is a mobile-first Flask web UI — the primary interface for phone and browser use. It shares all data and logic with the CLI through `ptos_service.py`.

### Requirements

```bash
pip install flask
```

### Running

```bash
python ptos_web.py
```

Then open `http://localhost:5000` in your browser (or your device's IP on the local network for mobile access).

### Files

| File | Purpose |
|------|---------|
| `ptos_web.py` | Flask application |
| `ptos_service.py` | Data layer — shared with GUI |
| `web_templates/` | HTML templates |

### Pages

**Home** — Dashboard stats (first 4 metrics from the configured dashboard), overdue due-list summary (up to 5 rows), quick-add preset buttons, and recent records from today. A dropdown lets you switch between dashboards. The default dashboard is set in `config.toml` under `[dashboard] default`.

**+ Add Record** — Schema-driven add form. Select a record type and all required and optional fields appear. Supports:
- Dropdowns for fields with defined options
- Conditional fields that appear/disappear based on other field values
- Numeric fields with unit labels (e.g. `₹`, `min`)
- Tag checkboxes plus a custom tags field
- Preset loading — picks a preset from a dropdown to pre-fill the form
- Multi-record presets — adds a group of related records in one action
- History-based defaults — most common values for option fields are pre-selected based on your past records
- Cascade suggestions — when you pick a field value (e.g. `source=mgm`), related fields suggest their most common co-occurring values from history

**Browse** — Filter, search, and group records. Supports:
- Type selector and time window
- Free-text expression filter (full boolean syntax)
- Free-text search
- Group by field
- Sort by field
- Specific log file selection
- Inline edit and delete for each result row (opens a full edit form)
- Export current results to CSV

**Queries** — Run any named query, metric, or dashboard from `queries.toml`. Choose a query from the list, optionally override the time window, and run. Results render inline — records as a table, groups as a summary, metrics as a value, dashboards as a card grid. Save the current browse filter as a named query directly from the web UI.

**Due** — Overdue record list with heat indicators (hot / warm / cool) based on days since last contact. Days threshold can be adjusted on the page.

**Journal** — Daily markdown journal editor. Opens today's journal. Navigate to previous or future dates; forward navigation is blocked past today. Creates a new entry from template for dates with no file. Saves with a `.bak` backup automatically.

**Log Editor** — View and edit any `.log` file in `records/` directly in the browser. File selector dropdown at the top. Saves with a `.bak` backup before every write.

---

## GUI (Desktop fallback)

`ptos_gui.pyw` is a Tkinter desktop GUI for Windows. It is the fallback interface — use the CLI or web UI first; the GUI covers the same ground for users who prefer a native window.

### Requirements

Same as `ptos.py` — Python 3.11+, standard library only. No extra packages. Tkinter is included with most Python distributions on Windows.

### Launching

```cmd
python ptos_gui.pyw
```

Or double-click `ptg.bat` (Windows launcher, no console window).

### Tabs

**+ Add Record** — Same schema-driven form as the web UI. Dropdowns, conditional fields, numeric units, tag checkboxes, preset loading and saving. History-based autocomplete on free-text fields.

**Journal** — Daily journal editor. Navigate with ◀ Prev / Next ▶ or click the date to jump. Ctrl+S saves; Ctrl+Enter toggles checkboxes. Markdown syntax highlighting. Creates entry from template for new dates.

**Queries** — Run named queries, metrics, and dashboards. Selecting a query or changing the time window runs it immediately.

**Browse** — Filter records by type, time, and field values. Group by dropdown. Due List button. Export CSV. Inline edit and delete with a full form.

**Log Editor** — Edit any `.log` file with full undo. Saves with `.bak` backup.

### Error log

Crashes and callback errors are written to `ptos_error.log` and shown in a popup with a Copy to Clipboard button. The app continues running after dismissal.

---

## Ignore patterns

Add to `.gitignore` and Syncthing ignore patterns:

```
*.tmp
*.bak
ptos_error.log
```
