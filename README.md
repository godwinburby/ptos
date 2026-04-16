# PTOS — Plain Text Operating System

> **New to PTOS?** See [README_START_HERE.md](README_START_HERE.md) for a plain-English overview.

> Log it. Query it. Own it.

Record and analyse life, work, and finance events using structured plain-text logs.
No database. No cloud. You own the data completely.

---

## Table of Contents

### Getting Started
- [What it is](#what-it-is)
- [Requirements](#requirements)
- [Installation & Setup Scripts](#installation--setup-scripts)
- [Folder structure after init](#folder-structure-after-init)
- [Anatomy of a record](#anatomy-of-a-record)

### Web Interface (Primary)
- [Web Interface](#web-interface)
- [Pages reference](#pages-reference)
- [Schema Builder](#schema-builder)
- [Backup & Restore](#backup--restore)

### Configuration
- [Configuration](#configuration)
- [Adding a new record type](#adding-a-new-record-type)
- [Unit labels in schema](#unit-labels-in-schema)
- [Queries reference](#queries-reference)
- [Presets reference](#presets-reference)

### Data Safety
- [Atomic Operations](#atomic-operations)
- [Doctor Command](#doctor-command)
- [Sharing and sync](#sharing-and-sync)
- [Ignore patterns](#ignore-patterns)

### Advanced — CLI Reference
- [Quick start (CLI)](#quick-start-cli)
- [CLI reference](#cli-reference)
- [Time windows](#time-windows)
- [Filter expressions](#filter-expressions)
- [Table view](#table-view)
- [Derived fields](#derived-fields)
- [Trend analysis](#trend-analysis)
- [Due list](#due-list)
- [Exporting to CSV](#exporting-to-csv)
- [Summing a specific field](#summing-a-specific-field)
- [Reading from a specific file](#reading-from-a-specific-file)
- [Selecting output fields](#selecting-output-fields)
- [Analysis examples](#analysis-examples)
- [Validation](#validation)
- [Journal (CLI)](#journal-cli)

---

## What it is

Every event you record becomes one line in a plain-text `.log` file:

```
2026-03-10 type=expense domain=self category=food amount=120 tag=restaurant | lunch with team
2026-03-10 type=expense domain=self category=transport amount=90 tag=auto
2026-03-10 type=exercise activity=walk duration=30 tag=morning
```

Fields become dimensions for grouping and filtering. Numeric fields become measures for summing and averaging. All rules about what fields exist and what values they accept live in `schema.toml` — the engine has no domain logic of its own.

The web app is the primary interface. The CLI is the engine underneath — available for scripting, automation, and power use.

---

## Requirements

- Python 3.11+ (uses `tomllib` from the standard library)
- Flask for the web UI: `pip install flask`
- Works on Windows, Linux, macOS, Android (Termux)

---

## Installation & Setup Scripts

Download all files from the repository, then run the setup script for your platform:

| Platform | Setup | Start |
|----------|-------|-------|
| Linux / macOS | `bash setup_ptos_linux.sh` | `bash start_ptos_linux.sh` |
| Windows | `setup_ptos_windows.bat` | `start_ptos_windows.bat` |
| Android/Termux | `bash setup_ptos_android.sh` | `bash start_ptos_android.sh` |

**Update PTOS:**

| Platform | Command |
|----------|---------|
| Linux / macOS | `bash update_ptos_linux.sh` |
| Windows | `update_ptos_windows.bat` |
| Android/Termux | `bash update_ptos_android.sh` |

Or update directly from the web UI by clicking the Update button in the top banner.

The setup script creates all folders and config files. `--init` (CLI equivalent) is
safe to re-run — it will not overwrite existing files.

---

## Folder structure after init

```
ptos/
├── ptos.py                 # Core CLI engine
├── ptos_service.py         # Service layer (shared by web UI and CLI)
├── ptos_web.py             # Web UI (Flask)
├── setup_ptos_linux.sh    # Linux setup script
├── setup_ptos_windows.bat  # Windows setup script
├── setup_ptos_android.sh   # Android/Termux setup script
├── start_ptos_linux.sh     # Linux start script
├── start_ptos_windows.bat  # Windows start script
├── start_ptos_android.sh   # Android/Termux start script
├── update_ptos_linux.sh    # Linux update script
├── update_ptos_windows.bat # Windows update script
├── update_ptos_android.sh   # Android/Termux update script
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

A record missing a tag or note is valid but weak — Lint will warn you.
A record missing a date or type is broken — Lint will error.

---

## Web Interface

`ptos_web.py` is a mobile-first Flask web app — the primary interface for all
day-to-day use. It shares all data and logic with the CLI through `ptos_service.py`.

### Starting the web app

```bash
python ptos_web.py
```

Then open `http://localhost:5000` in your browser. For mobile access, use your
device's local IP (e.g. `http://192.168.1.x:5000`). The Android/Termux start script
opens the browser automatically.

### Files

| File | Purpose |
|------|---------|
| `ptos_web.py` | Flask application |
| `ptos_service.py` | Service layer — shared data access for web and CLI |
| `web_templates/` | HTML templates |

---

## Pages reference

### Home

Dashboard stats (first 4 metrics from the configured dashboard), overdue due-list
summary (up to 5 rows), quick-add preset buttons, and today's records. A dropdown
lets you switch between dashboards. The default dashboard is set in `config.toml`
under `[dashboard] default`.

### + Add Record

Schema-driven add form. Select a record type and all required and optional fields
appear automatically. Features:

- Dropdowns for fields with defined options
- Conditional fields that appear/disappear based on other field values
- Numeric fields with unit labels (e.g. `₹`, `min`)
- Tag checkboxes plus a custom tags field
- Preset loading — pick a preset from a dropdown to pre-fill the form
- Save as Preset — fill the form, click Save as Preset, name it, done
- Multi-record presets — add a group of related records in one tap
- History-based defaults — most common values for option fields are pre-selected
- Cascade suggestions — picking a field value (e.g. `source=mgm`) suggests the
  most common co-occurring values for related fields

### Browse

Filter, search, and group records. Features:

- Type selector and time window
- Free-text expression filter (full boolean syntax: `AND`, `OR`, `NOT`, parentheses)
- Free-text search
- Group by field
- Sort by field
- Specific log file selection
- Inline edit and delete for each result row
- Export current results to CSV
- Save current filter as a named query (Save as Query button)

### Queries

Run any named query, metric, or dashboard from `queries.toml`. Choose a query from
the list, optionally override the time window, and run. Results render inline:
records as a table, groups as a summary, metrics as a value, dashboards as a card grid.

### Due

Overdue record list with heat indicators (hot / warm / cool) based on days since
last contact. Days threshold can be adjusted on the page.

### Journal

Daily markdown journal editor. Opens today's journal. Navigate to previous or future
dates; forward navigation is blocked past today. Creates a new entry from template
for dates with no file. Autosaves after 2.5 seconds of inactivity. Saves with a
`.bak` backup automatically.

### Log Editor

View and edit any `.log` file in `records/` directly in the browser. File selector
dropdown at the top. Saves with a `.bak` backup before every write. Use this only
to correct a record that can't be fixed through Browse → Edit.

### Schema Builder

Visual editor for `schema.toml`. Add, edit, and delete record types; define fields,
types, and conditions. See [Adding a new record type](#adding-a-new-record-type).

### Backup

Create full or config-only backups, download existing backups, restore from a local
backup or uploaded ZIP file, and delete old backups. See [Backup & Restore](#backup--restore).

### Lint

Run validation on all records against the schema. Results show errors, warnings, and
quality notes grouped by severity. Each issue links to the Log Editor at the exact line.

---

## Schema Builder

Navigate to the **Schema Builder** tab in the web app to:

- Add, edit, and delete record types
- Define required and optional fields per type
- Set field types (text, int, options)
- Configure conditional fields and tags

No need to edit `schema.toml` directly for most changes.

### Manual schema editing

For advanced changes or bulk edits, edit `schema.toml` directly:

1. Add the type name to `[types] allowed`
2. Define `required`, `fields`, and optionally `tags` and `conditions`
3. Run Lint (web UI) or `ptos --lint` (CLI) to verify existing records still pass
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

---

## Backup & Restore

### Web UI (recommended)

Access the **Backup** tab:

- Create full or config-only backups
- Download any backup
- Restore from a local backup or uploaded ZIP file
- Delete old backups

### CLI

```bash
ptos --backup-full    # Full backup: records/, templates/, config/, backups/
ptos --backup-config  # Config-only backup: schema, queries, presets, config
```

### Backup retention

- **Full backups:** Keeps the last **10 backups** automatically. Older ones are
  deleted after each new backup.
- **Config backups:** Never automatically deleted — kept indefinitely.

### Backup files

Stored in `backups/` with timestamped names:
- Full: `ptos-backup-full-YYYYMMDD_HHMMSS.zip`
- Config: `ptos-backup-config-YYYYMMDD_HHMMSS.zip`

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

By default PTOS places all files next to `ptos.py`. Set `PTOS_HOME` to use a
different location:

```bash
export PTOS_HOME=/data/ptos    # Linux / macOS / Termux
set PTOS_HOME=C:\ptos          # Windows
```

Useful when the script is on `PATH` but data lives in a synced folder.

---

## Adding a new record type

Preferred: use the **Schema Builder** tab in the web app (visual, no file editing).

For manual editing, see the [Schema Builder](#schema-builder) section above.

Example full type definition with a saved query and preset:

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

---

## Unit labels in schema

To show a unit hint next to a numeric field in the web UI add forms:

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

The `unit` key is read by the web UI only — `ptos.py` ignores it.

---

## Queries reference

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

Tokens in the expression can be other metrics or base queries directly. Base queries
used in derived metrics yield their numeric total. The base query's own time window
applies when it has one defined.

### Dashboards — named collections of metrics and queries

```toml
[dashboards.clinic]
metrics = ["assessments", "prescriptions", "total_revenue", "asp", "prescription_ratio"]
```

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

---

## Presets reference

Shortcuts for entries you add frequently. Any field can be omitted — PTOS will prompt
for it (CLI) or leave it blank (web form).

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

---

## Atomic Operations

PTOS ensures data safety through atomic write operations at every level.

### File writes (`.bak` + `.tmp` pattern)

Every write operation follows this sequence:
1. Copy current file to `*.bak`
2. Write new content to `*.tmp`
3. Atomic rename `.tmp` → final file
4. On success: delete `.bak`
5. On failure: restore from `.bak`, delete `.bak`

This applies to adding records, editing records, saving presets, saving journal
entries, and Log Editor saves.

### Backup creation (`.tmp` + verify pattern)

1. Write backup to `*.tmp` file
2. Verify ZIP integrity with `testzip()`
3. Atomic rename `.tmp` → final `.zip`
4. Clean up old backups if limit exceeded

### Restore operations (pre-restore backup + `.bak` pattern)

1. Create a full backup before restore (safety net)
2. Extract new files to temp directory
3. Copy existing folders to `*.bak`
4. Copy new files from temp to destination
5. On success: delete all `*.bak` backups
6. On failure: restore from `*.bak` backups

### Crash safety

If PTOS crashes mid-write, the original file is preserved (still in `.bak`),
the incomplete `.tmp` is cleaned up, and on next run PTOS restores from `.bak`.

Add `*.bak` and `*.tmp` to your `.gitignore` and Syncthing ignore patterns.

---

## Doctor Command

```bash
ptos --doctor           # Check for issues
ptos --doctor --fix     # Auto-fix issues where possible
```

Checks performed: Python version, Flask installed, required folders exist, config
files are valid TOML, schema is valid, templates folder exists, backups folder is
writable.

---

## Sharing and sync

Records are plain text — one line per entry, one file per year.

- **Git** — commit `records/` after each session. Full history, diff-friendly.
- **Syncthing / Dropbox / iCloud** — sync the whole `ptos/` folder.
- **Termux** — run the same script on Android. Set `PTOS_HOME` to your synced folder.

Multiple devices can safely append to the same log file as long as writes don't overlap.

---

## Ignore patterns

Add to `.gitignore` and Syncthing ignore patterns:

```
*.tmp
*.bak
ptos_error.log
```

---

---

# Advanced — CLI Reference

The CLI is `ptos.py` — the engine that powers the web app. Use it directly for
scripting, automation, bulk analysis, or terminal-only environments.

---

## Quick start (CLI)

```bash
# Initialise (first time only if not using setup script)
python ptos.py --init

# Optional: add an alias
alias ptos="python ~/ptos/ptos.py"

# Add a record
ptos --add type=expense domain=self category=food amount=120

# Add with a specific date
ptos --add type=expense domain=self category=food amount=120 --date yesterday
ptos --add type=expense domain=self category=food amount=120 --date 2026-03-08

# Use a preset
ptos --preset commute
ptos --preset commute --date yesterday

# Interactive add
ptos --add

# Run a saved query
ptos --query monthly_expenses
ptos --query monthly_expenses --time last-month

# Open today's journal
ptos --journal

# Edit config files
ptos --edit s        # schema.toml
ptos --edit q        # queries.toml
ptos --edit c        # config.toml
ptos --edit p        # presets.toml
ptos --edit r        # this year's records log
ptos --edit d        # today's journal
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
When multiple records match and `--all` is not given, PTOS lists them and asks you to
pick by number.

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
| `--backup-full` | | Create full backup (records/, config/, templates/, backups/) |
| `--backup-config` | | Create config-only backup (schema, queries, presets, config) |
| `--doctor` | | Check PTOS installation health |
| `--doctor --fix` | | Auto-fix issues found by --doctor |

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

Custom cycles let you define a billing or reporting period that starts on a fixed day
of the month rather than the 1st. `clinic-1` means one cycle back, `clinic-2` two
cycles back, and so on.

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

Boolean expressions and simple `field=value` conditions can be mixed freely. Works
in saved queries too:

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

Columns are auto-detected from the fields present in the result set. When results
contain multiple record types, each type gets its own sub-table.

```
[ expense ]
date        domain  category   amount  tag      note
-----------------------------------------------------
2026-03-10  work    food       32      snacks   coffee and biscuits
2026-03-11  home    grocery    190     fruits   weekly fruits
```

Width is adaptive — `note` column shrinks first when the terminal is narrow.

---

## Derived fields

Fields whose values are computed from other fields or date arithmetic. Defined in
`schema.toml`, available automatically in `--table` output and in filters.

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

Expressions support: `today`, `date`, `today - date` (returns days as int), and any
numeric field from the record. Boolean results display as `true`/`false`.

---

## Trend analysis

`--trend` runs your filters across the last N consecutive periods and shows them
side by side.

```bash
ptos --where type=expense --trend
ptos --where type=expense --trend 3 --time this-month
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

Supported time windows for `--trend`: custom cycles, `this-month`, `last-month`,
`this-week`, `this-quarter`, `YYYY-MM`.

---

## Due list

`--due` scans a configured record type, finds the most recent entry per unique key
(e.g. client), and surfaces those not updated within N days — sorted by priority.

Priority order is read from your schema field options. The first option listed is the
most urgent.

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

## Exporting to CSV

`--export` saves results to the `exports/` folder. Works in all output modes.

```bash
ptos -y expense -t tm --export                  # exports/expense_this-month.csv
ptos -y expense -t tm --export march_spend      # exports/march_spend.csv
ptos -y expense -t tm -G category --export      # exports/expense_this-month_grouped.csv
ptos -y sale -t tq -v source outcome --export   # exports/sale_this-quarter_pivot.csv
```

All filters, `--select`, `--sort`, and `--sum-field` apply before export — what you
see is what gets exported. Multi-value fields like `tag` are joined with a comma.

---

## Summing a specific field

By default PTOS auto-detects the first numeric field and sums it. Use `--sum-field`
when a record type has more than one numeric field.

```bash
ptos -y sale -t tm --sum-field advance
ptos -y sale -t tm --group category --sum-field advance
ptos -y sale -t tm --pivot source category --sum-field amount
```

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

Lint catches: missing required fields, invalid field values, unknown fields,
conditional required violations (e.g. `fit` missing when `outcome=prescribed`).

---

## Journal (CLI)

`--journal` opens today's journal in your editor. Creates the file from a template
if it doesn't exist.

```bash
ptos --journal        # open today's journal
ptos -j               # short form
ptos --edit j         # same via edit shortcut
```

The built-in template follows an ARRIVE → ENGAGE → RELEASE structure:

- **ARRIVE** — ground yourself before the day: reality check, body, mood, a word or verse, intention, prayer
- **ENGAGE** — top 3 tasks, home item, one person to love well, habits, drift checks at 11 / 2 / 5
- **RELEASE** — end of day: wins, where you drifted, gratitude, one thing to carry forward

The template is embedded in `ptos.py` — it works without a `templates/daily.md`
file. Place your own `templates/daily.md` to override it.

Journal files are stored at `journal/YYYY/YYYY-MM-DD.md`.
