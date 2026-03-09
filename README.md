# PTOS

**Plain Text Operating System for Life Logs**

Record life as structured plain text.\
Analyze it with simple CLI queries.\
Own your data forever.

PTOS turns everyday events into **structured datasets** that can be
analyzed using simple command‑line queries.

## Table of Contents

- [PTOS Architecture](#ptos-architecture)
- [Typical PTOS Workflow](#typical-ptos-workflow)
- [PTOS in 30 Seconds](#ptos-in-30-seconds)
- [Initialize Workspace](#initialize-workspace)
- [Workspace Structure](#workspace-structure)
- [Discover the Dataset](#discover-the-dataset)
- [Record Format](#record-format)
- [Expense Hierarchy](#expense-hierarchy)
- [Adding Records](#adding-records)
- [Presets](#presets)
- [Filtering Records](#filtering-records)
- [Time Filters](#time-filters)
- [Group Analysis](#group-analysis)
- [Pivot Analysis](#pivot-analysis)
- [The PTOS Data Model](#the-ptos-data-model)
- [PTOS vs Spreadsheet vs Database](#ptos-vs-spreadsheet-vs-database)
- [Philosophy of Plain Text Systems](#philosophy-of-plain-text-systems)
- [Closing Thought](#closing-thought)

------------------------------------------------------------------------

# PTOS Architecture

Life Events ↓ Structured Logging (ptos -a / presets) ↓ Plain Text
Records (records/YYYY.log) ↓ Schema Model (schema.toml) ↓ Query Engine
(filters → group → pivot) ↓ Metrics & Dashboards (queries.toml) ↓
Insights

PTOS behaves like a **plain‑text analytics engine**.

PTOS treats logs as structured data where fields become dimensions and numeric fields become measures.

------------------------------------------------------------------------

# Typical PTOS Workflow

PTOS follows a simple workflow that turns everyday events into useful insights.

capture → explore → analyze → dashboard


### 1. Capture

Record structured events.

ptos -a type=expense domain=self category=food amount=20 -n tea
ptos -p tea

Records are stored as plain text:


records/YYYY.log


### 2. Explore

Discover fields and values inside the dataset.


ptos --fields


This helps you understand:

- available fields
- observed values
- recommended grouping dimensions

### 3. Analyze

Use grouping and pivot commands.


ptos -y expense -G category
ptos -y expense -v domain category


Saved analytics queries can be defined in:


config/queries.toml


and executed with:

ptos -q query_name


### 4. Dashboard

Metrics and dashboards defined in `queries.toml` allow PTOS to produce summary reports and performance snapshots from plain text data.

------------------------------------------------------------------------

# PTOS in 30 Seconds

Initialize a workspace:

    ptos --init

Add records:

    ptos -a type=expense domain=self category=food amount=20 -n tea
    ptos -a type=expense domain=self category=transport amount=30 -n "bus to office"
    ptos -a type=expense domain=self category=food amount=200 -n "veg biryani"

Analyze:

    ptos -y expense -G category

Result:

    food        ₹220
    transport   ₹30

Three commands → three records → one insight.

------------------------------------------------------------------------

# Initialize Workspace

Run:

    ptos --init

Generated folders:

    records/
    config/
    presets/
    templates/
    journal/

Generated configuration:

    config/schema.toml
    config/config.toml
    config/queries.toml
    presets/presets.toml

Optional folders you may add:

    tasks/
    notes/

# Workspace Structure

A typical PTOS workspace looks like this:

```
ptos/
├── ptos.py
├── records/
│ └── YYYY.log
├── config/
│ ├── schema.toml
│ ├── queries.toml
│ └── config.toml
├── presets/
│ └── presets.toml
├── templates/
└── journal/
```

Each component has a clear responsibility:

- **records/** → raw event logs  
- **schema.toml** → data structure and validation rules  
- **queries.toml** → analytics, metrics, and dashboards  
- **presets/** → record templates for fast entry

------------------------------------------------------------------------

# Discover the Dataset

    ptos --fields

Example output:

    Fields by record type

    [expense]

      amount       20, 200, 30
      category     food, transport
    ★ domain       self
    ★ type         expense

This command shows:

• observed field values\
• available dimensions\
• recommended grouping fields

Results reflect the **currently loaded dataset**.

------------------------------------------------------------------------

# Record Format

Each event is one line:

    DATE key=value key=value | optional note

Example:

    2026-03-08 type=exercise activity=walk duration=30 tag=morning

Rules:

• structured fields appear before `|`\
• note appears after `|`\
• values contain no spaces\
• underscores replace spaces

------------------------------------------------------------------------

# Expense Hierarchy

Expense records follow a hierarchy:

    domain → category → tag

Example:

    ptos -a type=expense domain=self category=food tag=tea amount=20 -n tea

Example structure:

    self
      └── food
           ├── tea
           ├── snacks
           └── restaurant

This allows analysis such as:

    ptos -y expense -G domain
    ptos -y expense -G category
    ptos -v domain category

Other record types can use fields in any order.

------------------------------------------------------------------------

# Adding Records

Direct entry:

    ptos -a type=expense domain=self category=food amount=50

Interactive entry:

    ptos -a

Add note:

    ptos -a type=expense domain=self category=food amount=50 -n tea

------------------------------------------------------------------------

# Presets

Presets provide a fast way to create records using predefined field
values.

They behave like **record templates** stored in:

    presets/presets.toml

Instead of typing every field manually, a preset supplies common fields
and lets you override or complete the rest.

Example preset:

``` toml
[tea]

type = "expense"
domain = "self"
category = "food"
tag = "tea"
amount = 20
```

## Using a Preset

    ptos -p tea

PTOS expands the preset and writes:

    2026-03-09 type=expense domain=self category=food tag=tea amount=20

## Overriding Preset Fields

Command‑line values override preset values.

    ptos -p tea amount=25

Result:

    2026-03-09 type=expense domain=self category=food tag=tea amount=25

## Interactive Field Completion

If required fields are missing, PTOS asks for them interactively.

Example preset:

``` toml
[restaurant]

type = "expense"
domain = "self"
category = "food"
tag = "restaurant"
```

Run:

    ptos -p restaurant

PTOS prompts:

    amount:

After entering the value the record is written.

## Mixed Usage

Presets support hybrid usage:

    ptos -p restaurant amount=300 -n "veg biryani"

If required fields are still missing PTOS prompts only for those fields.

Final record logic:

    preset fields
    + CLI fields
    + interactive completion
    = final record

------------------------------------------------------------------------

# Filtering Records

Filter by type:

    ptos -y expense

Filter by tag:

    ptos -g tea

Field filters:

    ptos -w domain=self category=food

Search records:

    ptos -S courier

------------------------------------------------------------------------

# Time Filters

Examples:

    ptos -t today
    ptos -t this-week
    ptos -t this-month
    ptos -t last-month

Calendar month:

    ptos -t 2026-03

Custom date range:

    ptos -f 2026-01-01 -T 2026-01-31

Custom cycles can be defined in `config.toml`.

------------------------------------------------------------------------

# Group Analysis

    ptos -G category
    ptos -G domain category

Example:

    food        ₹4500
    transport   ₹2100

------------------------------------------------------------------------

# Pivot Analysis

    ptos -y expense -v domain category
    ptos -v source outcome --count

------------------------------------------------------------------------

# The PTOS Data Model

PTOS separates data into three layers:

    records → schema → queries

• **records/** store events\
• **schema.toml** defines structure and validation\
• **queries.toml** defines analytics and dashboards

------------------------------------------------------------------------

# PTOS vs Spreadsheet vs Database

PTOS sits between spreadsheets and databases.

| Tool | Strength | Limitation |
|-----|-----|-----|
| Spreadsheet | Easy data entry | Hard to maintain structure and history |
| Database | Powerful queries | Requires schema, setup, and tooling |
| **PTOS** | Structured logs + simple queries | Designed for event-based data |

PTOS works best for **event streams** such as:

- expenses
- habits
- medical visits
- sales pipelines
- customer interactions
- learning logs

Instead of editing rows in a spreadsheet, PTOS records **events over time**:

2026-03-10 type=expense domain=self category=food amount=20 | tea


Those events become a dataset that can be analyzed using simple CLI queries:

ptos -y expense -G category

This approach combines the **simplicity of plain text** with the **analytical power of structured data**.
------------------------------------------------------------------------

# Philosophy of Plain Text Systems

PTOS follows three principles.

### Small Events Matter

Patterns emerge from repeated small actions.

### Plain Text Lasts

Plain text is durable and future‑proof.

### Simple Systems Survive

Simple tools remain usable for decades.

------------------------------------------------------------------------

# Closing Thought

**Record life as it happens.**
