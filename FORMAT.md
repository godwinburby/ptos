# The PTOS record format

PTOS (Plain Text Operating System) stores every record as one line in a `.log` file.
There is one record per line, fields are `key=value` pairs, and the human-readable
free text lives in a quoted `note="..."` field at the end.

The format is deliberately plain: a `.log` file is a text file you can open in any
editor, `grep`, sort, and diff. No parser is required to *read* it, and no database
sits underneath it.

---

## The shape of a line

```
2026-03-11 type=expense domain=self category=food amount=120 tag=lunch note="Team lunch"
```

Reading left to right:

1. **A leading date**, `YYYY-MM-DD`.
2. **`type=<kind>`** immediately after the date — always the second token.
3. **Any number of `key=value` fields** in whatever order the writer chose.
4. **Zero or more `tag=<label>` fields** (repeat the key for multiple tags).
5. **An optional `note="..."` field**, always last, holding free text.

Every piece is separated by a single space. A value that contains a space, a `"` or
a `\` is wrapped in double quotes and those characters are escaped (`\"` and `\\`);
everything else is written bare.

---

## The grammar

```
line    = date SP "type=" token { SP field } [ SP "note=" quoted ]
date    = YYYY-MM-DD
field   = key "=" ( token | quoted )
key     = one or more characters other than whitespace, "=", "|"
token   = one or more characters other than whitespace, '"' , "\"
quoted  = '"' { any-character | '\"' | '\\' } '"'
note    = the value of the final note= field
SP      = one or more spaces or tabs
```

The rules in plain words:

1. **A record is one physical line.** A record never spans two lines.
2. **The first token is the date**, strictly `YYYY-MM-DD`.
3. **The second token must be `type=<name>`.** A line whose second token is not
   `type=` is not a v2 record line.
4. **`key=value`; the key is everything before the first `=`.** Keys never contain a
   space, `"` or `=`.
5. **A bare value is a single token.** If a value contains a space, a `"` or a `\`,
   it is *quoted*: `"..."`. Inside a quoted value, `\"` is a literal quote and `\\` is
   a literal backslash.
6. **Empty values are not allowed.** Write `amount=0`, or omit the field — never
   `amount=`.
7. **`note` is special.** It is the free-text field. There may be at most one, it is
   always last, and — because it is reserved by the format — a schema may not define
   a field named `note`.
8. **The reader pops `note` out.** When a line is parsed you get `(date, fields, note)`:
   the note is a separate value, *not* an entry in the field dictionary.
9. **`tag` repeats.** Because a dictionary has one value per key, `tag=a tag=b` is read
   as the list `["a", "b"]`. Any key may repeat this way.
10. **Blank lines and lines starting with `#` are ignored.**
11. **Order is canonical, not required for reading.** The writer emits the date, then
    `type`, then the record's fields in order, then `tag`s, then `note`. A reader
    accepts any order as long as `type=` is second and `note=` is last.

---

## Keys

A key is the text before the first `=`. Keys obey the **single-token rule**: no
spaces, no `"`, no `|`. By convention keys are lowercase `snake_case`
(`amount`, `due_date`, `merchant_name`).

| Field | Meaning |
|---|---|
| `type` | Required. The record kind, e.g. `expense`. Must be the second token. |
| `tag` | Free labels; repeat the key for several. Single-token values only. |
| `note` | Reserved. The free-text tail of the record. Never a schema field. |
| `id` | Optional. A short opaque id (e.g. `k3f9a1`) for cross-record links. |
| `links` | Optional. Comma-separated `type:id` targets this record points at. |

The schema's field list is the vocabulary the Add/Edit forms offer. A key not in the
schema is still stored and read; Lint reports it as an unknown field.

---

## Values and quoting

A bare value is a single token: no spaces, no `"`, no `\`. It may contain almost
anything else — including `=`, `|`, `/`, `.`, `:` and `@` — because the parser splits
fields on *whitespace*, not on punctuation:

```
2026-03-13 type=link url=https://example.com/?a=1&b=2
```

Here `url` is the whole value `https://example.com/?a=1&b=2`. The `=` inside it does
not start a new field.

### When a value is quoted

A value is quoted — wrapped in `"..."` with `\"` and `\\` escaped — **only when it
contains whitespace, `"` or `\`**. So:

```
2026-03-13 type=expense merchant=Big_Bazaar amount=250
2026-03-13 type=note title="Meeting with Dr. Mehta" category=work
```

`Big_Bazaar` needs no quotes; `Meeting with Dr. Mehta` has spaces, so it is quoted and
parsed back with its spaces intact. Quotes are *not* decoration: an unquoted value
with a space would split into two tokens and the parser would reject it. Quote
whenever the value contains a space.

### Token fields vs free-text fields

Your schema decides whether a field is a **token field** (the engine-reserved
`type`/`tag`/`id`/`links`) or a **free-text field** (every schema field, including one
with an `options` dropdown). PTOS treats them differently on write:

- **Token fields never carry spaces.** If you type `Big Bazaar` into a `tag`, PTOS
  stores `Big_Bazaar` (a space becomes `_`, a `|` becomes `/`). Matching an option value
  to a stored value normalises both sides, so a schema option written as `Big Bazaar`
  still validates a stored `Big_Bazaar`.
- **Every schema field keeps spaces**, via quoting, exactly as typed — including an
  `options` field. A schema option `money received` is stored as
  `source="money received"`, and `merchant` in a schema with no `options` likewise
  accepts `merchant="Big Bazaar"`.

Underscores in a schema value are therefore literal — unlike v1, PTOS no longer converts
a space to `_`. If you want a literal space, the value preserves it.

---

## The note

The note is the free text at the end of a record, written as the final `note=` field:

```
2026-03-14 type=income source=salary amount=4500 note="March salary, including bonus"
```

Everything inside the quotes is the note. It may contain spaces, `=`, `|`, commas,
punctuation and even an escaped `\"`. Line breaks are not allowed inside a record;
if a note is given with embedded newlines when a record is built, they are collapsed
to a single space (a record is one physical line).

`note` is a **reserved key**: it can never be a schema field name. This does not
change the parsed shape — `parse_line` still returns the note as a separate third
value:

```python
date, fields, note = ptos.parse_line(line)
```

---

## Examples

| Line | What a reader gets |
|---|---|
| `2026-03-11 type=expense category=food amount=120 tag=lunch note="Team lunch"` | `type`, `category`, `amount`, `tag` in the dict; note `Team lunch` |
| `2026-03-12 type=expense amount=40 tag=auto tag=bus note=commute` | `tag` is the list `["auto", "bus"]` |
| `2026-03-15 type=note title="Meeting with Dr. Mehta"` | `title` keeps its spaces |
| `2026-03-16 type=link url=https://example.com/?a=1&b=2` | `url` is the full URL (the `=` is part of the value) |
| `2026-03-17 type=expense merchant="O'Brien & Sons"` | a quoted free-text value with an ampersand |
| `2026-03-18 type=quote text="she said \"hi\""` | the value is `she said "hi"` (escaped inner quotes) |
| `2026-08-17 type=income amount=450 id=ins9x links=expense:k3f9a1 note=refund` | `id`/`links` are ordinary fields with a linking convention |
| `# a comment` | ignored |
| (empty line) | ignored |

---

## Things that do not work

| You write | What happens |
|---|---|
| `2026-03-13 expense amount=40` | No `type=` second → not v2. The v1 reader still reads it, and Lint flags it as a legacy line to migrate. |
| `2026-03-13 type=expense amount=` | Empty value → the parser rejects it. Use `amount=0` or drop the field. |
| `2026-03-13 type=expense merchant=Big Bazaar` | `merchant` is bare but contains a space → the parser sees a bare token `Big` and then `Bazaar` (no `=`), and the line is rejected. Quote it: `merchant="Big Bazaar"`. |
| `2026-03-13 type=expense amount=40 note=hi note=bye` | Two `note` fields — only the last free-text note is meaningful; a schema may not use `note` as a normal field. |
| `2026-03-13 type=expense category="a"b` | Trailing characters after a quoted value → rejected. |
| `2026-03-13 type=expense tag="two words"` | `tag` is a token field: a quoted tag is normalised to `two_words`. |

---

## Legacy v1 lines and migration

Before v2, a record used single-token values for *everything* and put free text after
a `|`:

```
2026-03-13 type=expense merchant=Big_Bazaar amount=250 | monthly shopping
```

PTOS **still reads** these lines (v2 is tried first; a non-conforming line falls back
to v1), so no data is lost and nothing breaks on upgrade. But writers only emit v2.
To rewrite every file in place:

```bash
ptos --migrate-format --dry-run    # report what would change, write nothing
ptos --migrate-format              # rewrite in place (atomic, per file)
```

The migrator leaves a line that is already canonical v2 byte-identical (it is
idempotent), preserves blank lines and `#` comments, and only touches `.log` files.
`ptos --lint` reports any line that still only reads via the v1 fallback so you can
find the stragglers.

The migrator also **decodes** every schema value: the v1 writer encoded spaces as
`_`, so each schema field value — free text **and** an `options` value — has its
underscores turned back into spaces and re-quoted, e.g. `merchant=Big_Bazaar` becomes
`merchant="Big Bazaar"` and `source=money_received` becomes `source="money received"`.
The same decode is applied to the schema's own option values and to config references
(`queries.toml`, `presets.toml`), so a query filter naming `money_received` follows the
value it points at. Token values (`type`/`tag`/`id`/`links`) and fields not defined in
the schema are left untouched. The decode is **lossy for a literal underscore** (e.g. an
email address or a code); that is intended — schema values are expected to hold real
spaces. A value written after this change keeps its underscores literal (only the
migrator decodes).

---

## Writing from your own script

The engine is the only thing that should build record lines:
`build_record_line(date, record_dict, note=None) -> str`. If you write your own, mimic
its rules exactly:

```python
def build(date, fields, note=None):
    parts = ["%s=%s" % ("type", fields["type"])]
    for key, val in fields.items():
        if key in ("type", "tag", "note"):
            continue
        parts.append("%s=%s" % (key, render(val)))
    for t in fields.get("tag", []):
        parts.append("tag=%s" % t)
    line = "%s %s" % (date, " ".join(parts))
    if note:
        line += " note=%s" % quote(note)
    return line
```

where `render`/`quote` wrap a value in `"..."` (escaping `\"` and `\\`) when it
contains whitespace, `"` or `\`, and raise on an empty value. The date must be
`YYYY-MM-DD`.

---

## Where records live

Records live in a configurable folder (default `records/`), one file per year:

```
records/2026.log
records/2026-03/2026-03.log   # optional grouping, if the user chose a log_group
```

The file name must be `YYYY.log` — the year in the file name is how PTOS picks the
files a query scans. A record's own date may differ from the file's year (it is used
for display and filtering, not for the file name).

---

## Full worked example

```
2026-03-11 type=expense domain=self category=food amount=120 tag=lunch note="Team lunch"
2026-03-12 type=expense domain=home category=grocery amount=850 tag=vegetables
2026-03-13 type=note title="Meeting with Dr. Mehta" body="Discussed the hearing aid fitting" tag=work
2026-03-14 type=income source=salary amount=42000 tag=monthly note="September salary"
2026-03-15 type=exercise activity=walk duration=40
```

Each line parses to a date, a field dictionary, and a note (empty when absent).