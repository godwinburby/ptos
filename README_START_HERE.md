# Welcome to PTOS

PTOS is a personal record-keeping system. It lets you log anything that matters
and then search, filter, and report on it whenever you need to.

Everything is stored as plain text files on your computer. No database, no internet,
no account. You own the data completely.

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
at the top explaining exactly how they work. Reading the file itself is usually
enough to figure out what to change.

### `schema.toml` — what you can record

This is the heart of the system. It defines every record type. Out of the box it
comes with four types to get you started:

- **expense** — money going out, with domain (self / home / work), category, and amount
- **income** — money coming in, with source and amount
- **exercise** — physical activity, with activity type and duration
- **learning** — books, podcasts, courses — with topic, source, and domain

For each type, the schema defines which fields are required, what values each field
accepts, and which tags appear as checkboxes in the form. The app's forms are built
entirely from this file.

To add a new record type or a new dropdown option, open `schema.toml` and follow
the pattern already there — every type is documented with comments above it.
The full reference is in `README.md` under the Schema section.

### `queries.toml` — your saved reports

Queries are saved filters and reports that you run repeatedly. Instead of setting
the same filters every time, you save them once with a name and run them in one click
from the Queries tab.

The file starts with one example query, one metric, and one dashboard:

- **all_expenses** — all expense records this month, with a total
- **avg_expense** — average amount per expense record (a metric)
- **home dashboard** — runs both of the above together in one view

These are just starting points. The file is heavily commented — read through it and
the pattern becomes clear quickly. The full reference is in `README.md` under the
Queries section.

### `presets.toml` — quick-add shortcuts

Presets are shortcuts for records you add frequently. A preset pre-fills the form
fields so you just confirm and save — no re-entering the same values every time.

The file starts with a commented-out example to show you the format. You can also
create presets directly from the app without editing this file at all: fill in the
Add Record form, click **Save as Preset** at the bottom, give it a name, and it is
saved immediately. Next time, pick it from the **Load preset** dropdown at the top
of the form.

### `config.toml` — basic settings

Three settings:

- **editor** — which text editor opens when editing files from the terminal (not relevant for GUI users)
- **currency** — the symbol shown next to all money values (default: `₹`)
- **cycles** — custom billing or reporting periods defined by a start day of month
  (e.g. `clinic = 26` means a cycle running 26th to 25th next month)

The file has inline comments explaining each setting. The cycles section is empty
by default — add a named cycle here if you report on periods that don't start on
the 1st of the month.

---

## How to use the app

Double-click `ptg.bat` to open the app. You do not need the terminal.

The app has five tabs:

- **+ Add Record** — fill in a form and save a record. This is where you spend most of your time.
- **Queries** — run saved reports. Pick a query from the list, choose a time window, results appear instantly.
- **Browse** — filter and search records. When you pick a type, field filter dropdowns appear automatically. You can also group results by a field, export to CSV, or click **Save as Query** to save the current filters as a named report for the Queries tab.
- **Journal** — your daily journal. One file per day. Navigate with Prev / Next or the date picker. Past dates with no entry show a Create Entry button.
- **Log Editor** — view and edit the raw log file directly. Use this only to correct a record.

For day-to-day use, you only need **Add Record** and **Journal**.

---

## First time setup

The app needs two Python files in the same folder: `ptos.py` (the engine) and `ptos_gui.pyw` (the GUI). Both must be downloaded. `ptos.py` can also be used on its own from the terminal without the GUI.

1. Make sure both `ptos.py` and `ptos_gui.pyw` are in the same folder.
2. Double-click `ptos_init.bat` — creates all folders and config files.
3. Double-click `ptg.bat` — opens the app.
4. Start adding records.

Run `ptos_init.bat` only once.

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

**The journal backs itself up.** Every time you save, a `.bak` file is written automatically.

**Nothing leaves this computer.** All data stays local.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| App won't open | Make sure Python is installed. Try right-clicking `ptg.bat` → Run as administrator. |
| "schema.toml not found" | Run `ptos_init.bat` first. |
| A field or dropdown option is missing | Open `schema.toml` — find the relevant type and add the option following the pattern already there. |
| Record saved with wrong values | Open the Log Editor tab, find the line, edit it, save. |
| A query is missing or producing unexpected results | Open `queries.toml` — the comments at the top explain the format. |
| Something looks broken and you can't figure it out | Don't change anything — reach out for help and describe what you saw. |

---

*For the full technical reference, see `README.md`.*
