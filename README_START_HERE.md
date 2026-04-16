# Welcome to PTOS

PTOS is a personal record-keeping system. Log anything that matters — clinic activity,
expenses, follow-ups, exercise, journal entries — and search, filter, and report on it
whenever you need to.

Everything is stored as plain text files on your computer. No database, no internet,
no account. You own the data completely.

---

## Table of Contents

- [The web app — your main interface](#the-web-app--your-main-interface)
- [How it works — the big picture](#how-it-works--the-big-picture)
- [The four config files](#the-four-config-files)
- [First time setup](#first-time-setup)
- [Where your data lives](#where-your-data-lives)
- [Things to know](#things-to-know)
- [Your data is safe](#your-data-is-safe)
- [The CLI — for advanced users](#the-cli--for-advanced-users)
- [Troubleshooting](#troubleshooting)

---

## The web app — your main interface

PTOS is designed to be used through a browser. Open it on your phone, tablet, or
desktop — no installation beyond the initial setup is needed. The app has ten tabs:

**Home** — your dashboard at a glance. Key metrics from your configured reports,
overdue items that need attention, and quick-add buttons for your saved presets.

**+ Add Record** — the form you use every day. Pick a record type and the right
fields appear automatically. Use a preset to pre-fill common entries with one tap.
The form remembers your past choices and suggests your most-used values.

**Queries** — run saved reports in one click. Pick a report, choose a time window
(this month, last month, a specific month, etc.), and results appear instantly.
No typing, no commands.

**Browse** — filter and explore records. Pick a type, set filters, group or sort
the results, and export to CSV if you need to take the data elsewhere. Click any
result row to edit it.

**Due** — see clients or items that haven't been followed up on. Sorted by urgency.
Adjust the threshold (1 day, 3 days, 7 days, etc.) to focus on what's most overdue.

**Journal** — daily markdown journal. One entry per day. Navigate with Prev / Next
or pick a date. Autosaves as you type.

**Schema Builder** — add or change record types without touching any files. Define
fields, dropdowns, and tags through a visual editor.

**Backup** — create backups, download them, restore from a previous backup. One
button to protect everything.

**Lint** — check your records for errors. Runs automatically and lists any issues.

**Log Editor** — view and edit the raw log file directly. Only needed if you need
to correct a record that can't be fixed through Browse → Edit.

For day-to-day use you only need **Home**, **Add Record**, and **Journal**.

---

## How it works — the big picture

Think of PTOS as a logbook with rules.

You define **what kinds of things you want to track** (called *record types*) and
**what information each one should capture** (called *fields*). Those rules live in
one file called `schema.toml`. The app reads that file and builds the forms and
dropdowns automatically — you never have to touch any code.

Every record you save becomes one line in a plain text file:

```
2026-03-19 type=expense domain=home category=grocery amount=340 tag=vegetables | weekly veggies
```

Date first, then the type, then fields, then an optional note after the `|`.
Simple enough to read in Notepad, powerful enough to query and report on.

---

## The four config files

All the intelligence of PTOS lives in four small files inside the `config/` folder.
They are plain text — open any of them in Notepad and you will find clear comments
at the top explaining exactly how they work.

You rarely need to edit these files directly. The web app's Schema Builder, Browse,
and Queries tabs handle the most common changes through a visual interface.

### `schema.toml` — what you can record

This is the heart of the system. It defines every record type. Out of the box it
comes with four types to get you started:

- **expense** — money going out, with domain (self / home / work), category, and amount
- **income** — money coming in, with source and amount
- **exercise** — physical activity, with activity type and duration
- **learning** — books, podcasts, courses — with topic, source, and domain

For each type, the schema defines which fields are required, what values each field
accepts, and which tags appear as checkboxes in the form. Use the **Schema Builder**
tab in the app to add or change record types — no file editing needed.

### `queries.toml` — your saved reports

Queries are saved filters and reports that you run repeatedly. Instead of setting
the same filters every time, you save them once with a name and run them in one click
from the Queries tab.

The file starts with one example query, one metric, and one dashboard. You can save
new queries directly from the Browse tab — set your filters, click **Save as Query**,
give it a name, and it appears in the Queries tab immediately.

### `presets.toml` — quick-add shortcuts

Presets are shortcuts for records you add frequently. A preset pre-fills the form
fields so you just confirm and save — no re-entering the same values every time.

Create presets directly from the Add Record form: fill in the fields, click
**Save as Preset** at the bottom, give it a name. Next time, pick it from the
**Load preset** dropdown at the top of the form.

Presets can also trigger multiple records at once — for example, a "morning routine"
preset that logs exercise, water intake, and medication in one tap.

### `config.toml` — basic settings

Three settings:

- **editor** — which text editor opens when editing files from the terminal
- **currency** — the symbol shown next to all money values (default: `₹`)
- **cycles** — custom billing or reporting periods defined by a start day of month
  (e.g. `clinic = 26` means a cycle running 26th to 25th next month)

---

## First time setup

Download all the files from the repository and run the setup script for your platform:

| Platform | Run this |
|----------|----------|
| Linux / macOS | `./setup_ptos_linux.sh` |
| Windows | `setup_ptos_windows.bat` |
| Android (Termux) | `./setup_ptos_android.sh` |

The setup script creates all folders and config files. After setup, use the start
script to launch the web app:

| Platform | Run this |
|----------|----------|
| Linux / macOS | `./start_ptos_linux.sh` |
| Windows | `start_ptos_windows.bat` |
| Android (Termux) | `./start_ptos_android.sh` |

Then open `http://localhost:5000` in your browser. On Android (Termux) the script
opens the browser automatically.

---

## Where your data lives

```
ptos/
├── records/
│   └── 2026.log          ← all your records for this year, one line per entry
├── journal/
│   └── 2026/
│       └── 2026-03-19.md ← today's journal entry
├── config/
│   ├── schema.toml       ← record types and field rules
│   ├── queries.toml      ← saved reports and dashboards
│   ├── presets.toml      ← quick-add shortcuts
│   └── config.toml       ← currency, editor, billing cycles
└── exports/
    └── *.csv             ← exported reports (created on demand)
```

These are all plain text files. You can open any of them in Notepad.
Do not rename or move them — the app finds them by name and location.

---

## Things to know

**Nothing is automatic.** Records are added only when you press Save.

**Tags are optional but useful.** They let you cross-filter later — e.g. `tag=petrol`, `tag=morning`.

**The Note field is free text.** Use it for context the structured fields can't capture.
It goes after the `|` in the log line.

**Automatic safety copies.** Every time you save a record or journal, PTOS creates
a backup first. If you need to undo a mistake, the backup is there.

**Nothing leaves this computer.** All data stays local.

---

## Your data is safe

**Automatic backups.** PTOS keeps the last 10 backups automatically. Go to the
**Backup** tab to create a manual backup, download one, or restore from a previous version.

**Crash protection.** Every time you save, PTOS makes a backup copy first. If
something goes wrong, your data is safe.

**Plain text.** Your records are just text files — no special software needed to read them.

---

## The CLI — for advanced users

The command-line interface (`ptos.py`) is the engine that powers everything. Most
users never need to use it directly — the web app handles all day-to-day tasks.

The CLI is useful when you want to:

- Add records quickly without opening a browser (`ptos --add ...`)
- Run complex ad-hoc analysis with grouping, pivots, and trends
- Script or automate record additions
- Use PTOS in a terminal-only environment (e.g. SSH, Termux without a browser)

Full CLI reference is in `README.md`.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| App won't open | Run `python3 ptos_web.py` directly to see error messages, or run `ptos --doctor`. |
| "schema.toml not found" | Run the setup script for your platform first. |
| A field or dropdown option is missing | Go to **Schema Builder** tab — add or edit the field there. |
| Record saved with wrong values | Go to **Browse** tab — find the record, click the **Edit** button next to it. |
| A query is missing or producing unexpected results | Go to **Browse**, set your filters, then click **Save as Query** to save. |
| Want to check for data errors | Go to **Lint** tab. |
| Need to restore a previous backup | Go to **Backup** tab — find your backup and click Restore. |
| Something looks broken and you can't figure it out | Don't change anything — reach out for help and describe what you saw. |

---

*For the full technical reference, see `README.md`.*
