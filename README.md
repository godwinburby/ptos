# PTOS — Plain Text Operating System

Record and analyse life, work, and finance events using structured plain-text logs.
One Python file. No database. No dependencies beyond the standard library.

---

## What it is

Every event you record becomes one line in a plain-text `.log` file:

```
2026-03-10 type=expense domain=self category=food amount=120 tag=restaurant | lunch with team
2026-03-10 type=assessment client=C001 name=Rajan source=raf outcome=prescribed fit=binaural
2026-03-10 type=exercise activity=walk duration=30 tag=morning
```

Fields become dimensions for grouping and filtering. Numeric fields become measures for summing and averaging. All rules about what fields exist and what values they accept live in `schema.toml` — the Python script has no domain logic of its own.

---

## Requirements

- Python 3.11+ (uses `tomllib` from the standard library)
- Works on Windows, Linux, macOS, Android (Termux)

---

## Installation

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
ptos --query rx

# Override a saved query's time window
ptos --query rx --time last-month
ptos --query rx --time last-quarter

# Open today's journal
ptos --journal

# Edit config files
ptos --edit s        # schema.toml
ptos --edit q        # queries.toml
ptos --edit c        # config.toml
ptos --edit p        # presets.toml
ptos --edit r        # this year's records log
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

### Analyse

| Flag | Description |
|------|-------------|
| `--group field [field ...]` | Group by one or more fields |
| `--pivot ROW COL` | Pivot table |
| `--count` | Count records instead of summing numeric fields |
| `--sort COL` | Sort pivot rows by a column name |
| `--trend [N]` | Show last N periods side by side (default: 6) |
| `--due [DAYS]` | Show overdue records not updated in N days (default: from queries.toml) |

### Utilities

| Flag | Description |
|------|-------------|
| `--lint` | Lint all records against schema |
| `--journal` | Open today's journal |
| `--edit [TARGET]` | Edit a workspace file (r s q c p d x) |
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
| Custom cycles | Defined in `config.toml` — e.g. `clinic`, `clinic-1` |

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
ptos --query rx --time lm       # last month
ptos --query ass --time tq      # this quarter
ptos --type expense --time td   # today
ptos --query rx --trend --time tm
```

Custom cycles let you define a billing or reporting period that starts on a fixed day of the month rather than the 1st. `clinic-1` means one cycle back, `clinic-2` two cycles back, and so on.

```toml
# config.toml
[cycles]
clinic = 26   # cycle runs 26th → 25th next month
salary = 1    # same as calendar month
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

[type.expense.conditions.fit]                  # conditionally required field
when = { outcome = "prescribed" }
```

### Shared field definitions — define once, reuse everywhere

```toml
[shared.source]
options = ["raf", "ent", "walkin", "marketing"]

# Then in any type:
[type.assessment.fields.source]
use = "shared.source"

[type.prescription.fields.source]
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
[assessments]
where = "type=assessment"

[deferred]
where = "type=assessment outcome=deferred"
```

### Metrics — computed over base queries

```toml
[metrics.prescription_ratio]
ratio = ["prescriptions", "assessments"]   # prescriptions / assessments × 100%

[metrics.asp]
avg = "prescriptions"                      # average numeric field value
```

### Dashboards — named collection of metrics and base queries

```toml
[dashboards.clinic]
metrics = ["assessments", "prescriptions", "prescription_ratio", "asp"]
```

Run with: `ptos --query clinic`

### Saved queries — any combination of filters, time, analysis

```toml
[rx]
where = "type=prescription"
time  = "this-month"
sum   = true

[funnel]
where = "type=assessment"
time  = "this-quarter"
pivot = ["source", "outcome"]
count = true

[exp_cat]
where = "type=expense domain!=work"
time  = "this-month"
group = ["category"]
```

**Saved queries compose with `--time`** — the saved query defines the default time, but you can always override it at the CLI:

```bash
ptos --query rx                   # uses the query's own time setting
ptos --query rx --time last-month     # same filters, different window
ptos --query rx --time last-quarter
ptos --query rx --time 2026-01
```

---

## Trend analysis

`--trend` runs your filters across the last N consecutive periods and shows them side by side. Works with any time window that has a natural predecessor.

```bash
# Prescriptions over last 6 clinic cycles (default)
ptos --where type=prescription --trend

# Assessments by calendar month, last 3 months
ptos --where type=assessment --trend 3 --time this-month

# Work expenses over last 4 months
ptos --where type=expense domain=work --trend 4 --time this-month

# Any saved query + trend
ptos --query rx --trend
```

Output:

```
Trend: type=prescription

period              count      total        avg
-----------------------------------------------
2025-10                 0         ₹0          -
2025-11                 0         ₹0          -
2025-12                 0         ₹0          -
2026-01                 3    ₹303900    ₹101300
2026-02                 2    ₹222650    ₹111325
2026-03                 0         ₹0          -
```

Supported time windows for `--trend`: custom cycles (`clinic`, `clinic-1`…), `this-month`, `last-month`, `this-week`, `this-quarter`, `YYYY-MM`.

---

## Due list

`--due` scans a configured record type, finds the most recent entry per unique key (e.g. client), and surfaces those not updated within N days — sorted by priority.

Priority order is read directly from your schema field options. The first option in the list is the most urgent. No hardcoding in the script.

### Configure in queries.toml

```toml
[due]
type    = "followup"   # record type to scan
key     = "client"     # field that identifies each unique entity
sort_by = "stage"      # field whose schema option order defines priority
days    = 7            # default overdue threshold
```

The `sort_by` field's options in `schema.toml` define the priority order:

```toml
[type.followup.fields.stage]
options = ["trial", "decision", "assessment", "deferred", "unattended"]
#           ↑ most urgent                                 ↑ least urgent
```

### Usage

```bash
ptos --due           # use default days from queries.toml
ptos --due 3         # override to 3 days
ptos --due 0         # show everyone (morning review)
```

Output:

```
Due  (>3 days)  type=followup

   last  stage           client                    note
--------------------------------------------------------------------------------
      5d  trial           george_joseph             needs super power BTE for trial
      5d  decision        zahira_thajudheen         wants BTE with exchange
      5d  assessment      lalitha_k                 will bring her saturday
      4d  assessment      sreedharan_parambath      takes calls, says will come
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

Override any preset field inline:

```bash
ptos --preset commute amount=120        # different amount
ptos --preset commute tag=uber          # different tag
ptos --preset commute --date yesterday      # different date
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

# Pivot assessments: source vs outcome
ptos --type assessment --pivot source outcome --count

# Pivot prescriptions: model vs source, summing amount
ptos --type prescription --pivot model source

# Discover what fields are available in your current results
ptos --type expense --fields

# Discover available group fields
ptos --type assessment --group ?

# Discover available pivot fields
ptos --type assessment --pivot ?
```

---

## Filter expressions

Filters go with `-w` or inside `where =` in queries.

```bash
ptos --where type=expense                   # equality
ptos --where type=expense domain=self       # multiple filters (AND)
ptos --where type=expense domain!=work      # not equal
ptos --where type=expense amount>=500       # numeric comparison
ptos --where type=prescription fit=binaural
```

Operators: `=` `!=` `>` `<` `>=` `<=`

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

Lint catches: missing required fields, invalid field values, unknown fields, conditional required violations (e.g. `fit` missing when `outcome=prescribed`).

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
