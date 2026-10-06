# PTOS record format

PTOS stores every record as one line of plain text. This page is the complete
specification of that line, written so you can read, write and search your data with
nothing but a text editor, `grep`, `awk` or a few lines of your own code.

- **Format version:** 1
- **Encoding:** UTF-8
- **Files:** `records/YYYY.log` (see [Files](#files))

---

## At a glance

```
2026-03-11 type=expense domain=self category=food amount=120 tag=restaurant | lunch with team
────────── ──────────── ─────────────────────────────────── ─────────────── ────────────────
date       type         fields (key=value, any order)       tag             note
```

A record is:

1. an ISO date,
2. one or more `key=value` pairs separated by spaces,
3. optionally a `|` followed by a free-text note.

That is all. There is no quoting, no escaping and no nesting.

**One rule to remember:** both halves of `key=value` are single tokens, so neither carries
spaces — write `unit_price=Big_Bazaar`, not `unit price=Big Bazaar`. The note after `|` is
the only place free-form text belongs. See [Keys](#keys) and
[Values carry no spaces](#values-carry-no-spaces).

---

## Grammar

```
line    = date { SP field } [ SP? "|" note ]
date    = YYYY-MM-DD
field   = key "=" value
key     = one or more characters other than whitespace and "="
value   = zero or more characters other than whitespace and "|"
note    = any characters (may contain "|", "=", quotes and spaces)
SP      = one or more spaces or tabs
```

Rules in plain words:

1. **The date comes first.** It must be `YYYY-MM-DD`. Always write it in this form.
2. **Everything before the first `|` is the field part.** Everything after it is the note.
   Because the split happens at the *first* `|`, a `|` can never appear inside a value.
   It may appear freely inside the note.
3. **The field part is split on whitespace.** Each piece containing `=` is a field. The
   key is the text before the *first* `=`; the value is everything after it, so a value
   may itself contain `=`.
4. **A key and a value are each a single token.** Neither may contain whitespace, and a
   value may not contain `|` either. See [Keys](#keys) and
   [Values carry no spaces](#values-carry-no-spaces).
5. **A value may be empty.** `amount=` is a field whose value is the empty string.
6. **Pieces without `=` are ignored.** A stray word in the field part is skipped, not an
   error.
7. **Order does not matter** to readers. By convention PTOS writes `type=` right after the
   date and puts `tag=` and `note` last.
8. **A repeated key means several values.** `tag=auto tag=bus` is one field `tag` with the
   values `auto` and `bus`, in order.
9. **The note is trimmed** of leading and trailing whitespace, and any line break
   (LF, CR or CRLF) inside it becomes a single space — a record is one physical line. It is
   not searched as a field.
10. **Blank lines and lines starting with `#` are ignored.**
11. **Quotes and backslashes are ordinary characters.** `"` has no special meaning
    anywhere. See [Things that do not work](#things-that-do-not-work).

---

## Keys

A key is the text before the first `=`, and it obeys the same single-token rule as a
value — so **keys carry no spaces either**. Field names defined in your schema must match
`^[a-z][a-z0-9_]*$`: lowercase letters, digits and underscores, starting with a letter.
Use the same style for any key you add by hand.

Why it matters: a space inside a key would make the key unrepresentable. `unit price=50`
parses as the field `unit` with the value `price`, plus the word `50` silently dropped —
a key you can write but never read back. Underscores are the only separator a key can use.

PTOS enforces this wherever a name is minted, so a spaced name cannot reach your data:

| Where you create a name | What happens to `my name` |
|---|---|
| Record Types page (`/types`) | coerced to `my_name` as you type |
| Schema Builder (`/schema-builder`) | rejected, listing the offending field names |
| Query Builder (`/query-builder`) | coerced to `my_name` as you type, rejected on save |
| `ptos --add-type` / `--add-field` | rejected with the name in the message |
| `ptos --add-preset` | rejected with the name in the message |
| Any hand-edited `schema.toml` | reported by `ptos --check-schema` |

The two ends differ on purpose. The beginner-facing pages (Record Types, Query Builder)
coerce, because the name is being typed fresh and nothing references it yet. The
Schema Builder and the CLI reject, because those paths edit or script a schema where a
surprise rename would be harder to spot.

- `type` is required. Every record needs a `type=` field naming its record type.
- `tag` is the conventional key for free labels; use it more than once for several tags.
- `id` and `links` are optional keys PTOS uses to link records (`links=expense:k3f9a1`).
  See the *Cross-record Links* section of the README.

A key that is not in the schema is still stored and read like any other. Lint reports it
as an unknown field, so you will know if a typo created one.

---

## Values and types

The file contains text only. A value has no type in the syntax: `amount=120` and
`done=true` are both just strings.

Meaning comes from your **schema** (`config/schema.toml`): the schema says which record
types exist, which fields each one requires, which values a field such as `category`
may take, and what type a field has. Field types in the schema are `int`, `string`,
`datetime` and `bool`. Two of them are checked strictly by Lint:

- an `int` field must contain only digits (no sign and no decimal point), so store
  amounts in whole units, for example paise or cents;
- a `datetime` field must be an ISO timestamp such as `2026-03-11T14:30`.

The file itself stays plain text; the checks run when PTOS writes a record and when you
run `ptos --lint`.

When a key appears once, readers get one string. When it appears two or more times, they
get a list. **Code that reads `tag` (or any multi-value field) must accept both.**

---

## Values carry no spaces

**A value must not contain a space. Write an underscore instead.** This is the one hard
rule of the format:

```
merchant=Big_Bazaar          correct — one token, greppable
merchant=Big Bazaar          wrong  — two tokens; see below
```

```
2026-03-13 type=expense merchant=Big_Bazaar amount=250 | monthly shopping
```

The app shows underscores as spaces ("Big Bazaar") wherever a stored value is displayed to
you — record tables, the add/edit forms (free-text fields, option menus and tag chips), and
the filter/query chips — so you normally never see the underscore while using PTOS. The file
keeps it. Pages that define the stored vocabulary (Record Types, Schema Builder) and the
engine-reserved `id`/`links` tokens show the exact stored form.

What happens if you get it wrong, exactly:

```
2026-03-13 type=expense merchant=Big Bazaar amount=250
```

The field part is split on whitespace, so this is read as `merchant=Big`, then the
stray piece `Bazaar` (no `=`), then `amount=250`. **`Bazaar` is silently discarded** —
no error, no warning, and the value on screen reads "Big". Nothing is lost permanently
if you notice, but nothing tells you either. A `|` in a value is worse: it starts the
note, so the rest of the field part is thrown away.

PTOS therefore never writes a space or a `|` into a value. It writes the underscore,
and turns `|` into `/`. The same rule applies to keys, which is why field names are
written `unit_price` and never `unit price` — see [Keys](#keys). Whatever you type into
the app is stored in the conforming shape; see
[Writing from your own script](#writing-from-your-own-script) for doing the same in your
own code.

Two consequences of the underscore convention:

- A literal underscore and a space look the same on screen. If the exact text matters,
  put it in the note.
- `grep merchant=Big_Bazaar` finds the record. There is only one spelling of each value.

Anything free-form (sentences, names with punctuation, quotes, pipes) belongs in the
note, not in a field.

---

## The note

Everything after the first `|` is the note. It can contain any characters.

```
2026-03-14 type=income source=salary amount=450 | bonus | q1 = good, "paid" early
```

The note is `bonus | q1 = good, "paid" early`. The second `|` and the `=` are part of the
note, not new fields.

Write ` | ` (a space on each side) for readability. PTOS reads `|` with or without
spaces around it.

---

## Examples

| Line | What a reader sees |
|---|---|
| `2026-03-11 type=expense category=food amount=120 tag=restaurant \| lunch` | date `2026-03-11`; `type`, `category`, `amount`, `tag` as strings; note `lunch` |
| `2026-03-12 type=expense amount=40 tag=auto tag=bus \| commute` | `tag` is the list `["auto", "bus"]` |
| `2026-03-15 type=link url=https://example.com/?a=1&b=2` | `url` is `https://example.com/?a=1&b=2` (the value contains `=`) |
| `2026-03-16 type=expense amount= category=food` | `amount` is the empty string |
| `2026-03-17 type=expense merchant=Big_Bazaar amount=250` | `merchant` is `Big_Bazaar` (shown as "Big Bazaar") |
| `2026-08-17 type=income amount=450 id=ins9x links=expense:k3f9a1 \| refund` | `id` and `links` are ordinary fields with a linking convention |
| `# my comment` | ignored |
| (empty line) | ignored |

---

## Things that do not work

| You write | What happens |
|---|---|
| `merchant=Big Bazaar` | The field is `merchant`=`Big`; the piece `Bazaar` has no `=` so it is silently dropped. You see "Big". Write `merchant=Big_Bazaar`. |
| `unit price=50` | The field is `unit`=`price`; the piece `50` is dropped. A key with a space can be written but never read back. Use `unit_price=50`. |
| `merchant="Big Bazaar"` | Quotes are not special, so this is the same mistake twice: the field is `"Big` and `Bazaar"` is dropped. |
| `A\| inside a value` | The note starts at the `|` and the rest of the field part is lost. Put it in the note, or write `/`. |
| `amount=5|note` with no space | Works: the note starts at `|`. |
| `type=expense amount=5` (no date) | The first piece is not a date, so the line cannot be parsed. Queries skip it; Lint reports "cannot parse line". |
| `2026-02-30 type=expense` | Not a real date. Same as above. |
| `2026-03-11 amount=5` (no `type`) | Parses, but Lint reports "missing type field". |

Every one of these is silent *in the file*: nothing errors, the value is just shorter than
you meant. PTOS itself never writes a line like this — the writer normalizes values and
keys, flattens a multi-line note, and refuses a bad date, a bad key, a line containing a
line break, or a line that would not parse back — so these only happen in a hand-edited
file. `ptos --lint` (or the Lint page in the web app) shows the file and line number.

---

## Files

Records live under your data folder:

```
records/2026.log                 one file per year, any number of lines
records/<group>/2026.log         optional: a record type kept in its own folder (log_group)
```

- Each file is UTF-8 text, one record per line. Any line ending (`\n` or `\r\n`) is fine.
- The year in the file name is used to skip files outside a query's date range, so keep
  names as `YYYY.log`.
- The order of lines inside a file does not matter to readers.
- Files are plain text, so Git, Syncthing, backups and any editor work on them directly.
  PTOS writes through a temporary file and renames it, so a crash does not leave a
  half-written file.

---

## Read it yourself

### Python (standard library only)

```python
import datetime as dt

def parse_record(line):
    """Return (date, fields, note), or None for a blank or comment line.
    Raises ValueError if the line cannot be parsed (bad or missing date)."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    main, _, note = line.partition("|")
    parts = main.split()
    if not parts:
        raise ValueError("empty line")
    date = dt.date.fromisoformat(parts[0])
    fields = {}
    for token in parts[1:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key not in fields:
            fields[key] = value
        elif isinstance(fields[key], list):
            fields[key].append(value)
        else:
            fields[key] = [fields[key], value]
    return date, fields, note.strip()
```

Read a whole year:

```python
with open("records/2026.log", encoding="utf-8") as f:
    for line in f:
        try:
            rec = parse_record(line)
        except ValueError:
            continue
        if rec:
            date, fields, note = rec
```

The equivalent JSON for the first example is:

```json
{"date": "2026-03-11", "type": "expense", "domain": "self", "category": "food",
 "amount": "120", "tag": "restaurant", "note": "lunch with team"}
```

(`tag` is a string here because it appears once; with two `tag=` pieces it would be a list.)

### Writing from your own script

1. Start with the date as `YYYY-MM-DD`.
2. Add `key=value` pairs separated by single spaces. Use one `key=value` per value for
   multi-value fields.
3. Normalise every value: collapse whitespace runs to `_`, trim the ends, and turn any
   `|` into `/`. This step is not optional — see
   [Values carry no spaces](#values-carry-no-spaces). PTOS applies it to every value it
   writes, so a line that skips it is the only kind that can break.
4. Append ` | ` and the note if you have one. The note is the one place where spaces
   and `|` are fine.
5. Append the line to the right year file with a trailing newline.

```python
def build_record(date, fields, note=None):
    parts = []
    for key, value in fields.items():
        for v in (value if isinstance(value, list) else [value]):
            v = "_".join(str(v).split()).replace("|", "/")
            parts.append(f"{key}={v}")
    line = f"{date.isoformat()} " + " ".join(parts)
    return line + (f" | {note}" if note else "")
```

### grep and awk

All food expenses in 2026:

```sh
grep ' type=expense' records/2026.log | grep ' category=food'
```

Records with the tag `bus` (the tag may be followed by a space or the `|`):

```sh
grep -E ' tag=bus([ |]|$)' records/*.log
```

Search the notes (and everything else) for a word:

```sh
grep -i 'lunch' records/*.log
```

Total expenses for March 2026 (the note is stripped first so it cannot interfere):

```sh
awk '{ sub(/\|.*/, "") }
     / type=expense( |$)/ && $1 ~ /^2026-03/ {
       for (i = 2; i <= NF; i++) if ($i ~ /^amount=/) s += substr($i, 8)
     }
     END { print s + 0 }' records/2026.log
```

Number of expenses per category, most frequent first:

```sh
awk '{ sub(/\|.*/, "") }
     / type=expense( |$)/ {
       for (i = 2; i <= NF; i++) if ($i ~ /^category=/) c[substr($i, 10)]++
     }
     END { for (k in c) print c[k], k }' records/*.log | sort -rn
```

Lines that do not start with a date (ignoring blank and comment lines):

```sh
grep -v -E '^(#|$|[0-9]{4}-[0-9]{2}-[0-9]{2} )' records/*.log
```

Or let PTOS check everything, including the schema rules: open the Lint page in the web
app, or run `ptos --lint` from the command line. To get data out as CSV, add `--export` to
any query, for example `ptos -y expense -t tm --export`.

---

## Why this format

- **One line, one fact.** `grep`, `sort`, `diff`, `wc -l` and `git log -p` all work on it
  with no tooling.
- **Easy to reconcile.** If two devices change the same year file, your sync tool keeps a
  conflict copy. Because a record is one line, `ptos --resolve-conflicts` can show exactly
  which lines differ and let you keep both.
- **Forgiving by design.** A stray word or a hand-typed typo in a field part does not break
  the line.
- **No lock-in.** If PTOS disappears, your data is still readable. The reference parser
  above is short enough to rewrite in any language in a few minutes.

The trade-off is simple: values are single tokens, and free-form text goes in the note.
For data that needs nested or typed structure, export it (CSV from the CLI) rather than
bending the record format.

---

## Stability

The rules on this page are stable. A line that is valid today keeps its meaning in future
versions. Any new syntax would be added only in a backwards-compatible way, and readers of
this version that meet something they do not understand skip it rather than fail, exactly
as they already skip pieces without `=`.
