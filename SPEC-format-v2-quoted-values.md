# SPEC: PTOS record format v2 — quoted free-text values

**Project:** PTOS  
**Applies to:** on-disk records, `FORMAT.md`, parser/writer, web/CLI, migrator, tests  
**Status:** Design locked for implementation  

---

## Goal

Upgrade the record line so that:

1. **Date** stays a bare leading `YYYY-MM-DD` (not `date=`).
2. **Keys** and **tag values** remain **single tokens** (no spaces, no quotes).
3. **Free-text values** (e.g. address) and **notes** may contain spaces via **content-driven double quotes**.
4. **`|` note tail is removed** — use `note=` / `note="..."`.
5. **Underscore-as-space is not required** on v2 writes.
6. **Canonical write order:** date → type → other fields → tags → note.
7. **One physical line per record** (no raw newlines).

Breaking change: **format version 2**, with migration and dual-read.

---

## Non-goals

- `date=YYYY-MM-DD` as the normal form  
- Quoted keys  
- Schema type controlling quotes (`string` ⇒ always quote)  
- Spaces inside `tag=` values  
- JSONL / nested structures  
- Requiring field order on **read** (except date first)

---

## At a glance (v2)

```text
2026-03-11 type=expense domain=self category=food amount=120 tag=restaurant tag=work note="lunch with team"
────────── ──────────── ─────────────────────────────────── ───────────────────────── ────────────────────
date       type         other fields (any order among them)  tags (single tokens)      note (last)
```

Rules in one line:

- **Date first** (bare). **`type=` second** (writer). **Tags** before **note**. **Note last**.
- Keys and tags: **single tokens only**.
- Value has whitespace (or `"\`\) → `"quoted"`; else bare.
- No `|`.

---

## Format version

| Item | Value |
|------|--------|
| Version | **2** |
| Encoding | UTF-8 |
| Files | `records/YYYY.log` (and `log_group` paths) unchanged |
| Config | e.g. `record_format = 2` in config/schema (document in FORMAT.md) |

Writers emit **only v2** when format is 2. Readers dual-read v1 during migration.

---

## Grammar (normative)

```
line         = date SP type-field { SP field } SP?
date         = 4DIGIT "-" 2DIGIT "-" 2DIGIT     ; YYYY-MM-DD only (positional, not date=)
type-field   = "type" "=" bare-value            ; required; writer places second
field        = key "=" value
key          = key-char+
key-char     = ALPHA / DIGIT / "_"              ; schema names: [a-z][a-z0-9_]*
value        = bare-value / quoted-value
bare-value   = *bare-char
bare-char    = any Unicode scalar except WSP, DQUOTE, "\", CR, LF
quoted-value = DQUOTE *( qdtext / escape ) DQUOTE
qdtext       = any Unicode scalar except DQUOTE, "\", CR, LF
escape       = "\" ( DQUOTE / "\" )             ; v2.0: no \n in stored values
SP           = 1*WSP                            ; writer emits single SPACE
```

### Structural rules

1. **Date is positional** — first token, bare `YYYY-MM-DD`. Not written as `date=`.
2. **`type` is required** — every record has `type=<single-token>`.
3. **Keys** are single tokens (no spaces, no quotes, no `=` inside key).
4. **After the date**, the line is only `key=value` fields (no pipe-tail).
5. **Tag values** (`tag=...`) are **always bare single tokens**. Spaces in a tag are rejected or normalized to `_` at input boundaries; **do not** emit `tag="..."`.
6. **Other values:** bare if safe; `"quoted"` if they contain WSP, `"`, or `\`.
7. **Note** is a normal field `note=...`. Writer places it **last**. Prefer `note="..."` when the note has spaces.
8. **No `|` special syntax** in v2.
9. **Repeated keys** (especially `tag=`) mean multi-value lists, same as v1.
10. **Raw CR/LF** in the line → invalid; writer and `append_record` refuse.
11. **Empty value:** accept `key=` and `key=""`; writer canonical form `key=""` if empty is allowed.

### Content-driven quoting (writer)

```
needs_quote(v) =
    empty value under empty-policy
    OR any whitespace in v
    OR '"' or '\' in v

if key == "tag":
    value must be bare single token (never quote; reject or normalize spaces)
elif needs_quote(v):
    emit '"' + escape(v) + '"'
else:
    emit bare v
```

**Do not** quote because schema says `type = "string"`.  
**Do not** force space→`_` on v2 writes for free-text fields (address, note, etc.).  
**Do** keep controlled vocabulary / options as bare tokens in schema.

### Escape

Inside quotes: `\"` and `\\` only for v2.0.  
Do not store raw newlines; do not require `\n` escapes in v2.0.

---

## Canonical write order (builder must emit)

```text
1. date
2. type=...
3. all other fields except tag and note
   (stable order: schema field order or alphabetical — pick one, document in FORMAT.md)
4. all tag=... (preserve multi-tag order as given)
5. note=... (if present)
```

**Read path:** only **date first** is mandatory. `type`, tags, and note may appear in any order after the date; parser keys by name. Lint may *warn* if order differs from canonical.

---

## Examples

Valid:

```text
2026-03-11 type=expense domain=self category=food amount=120 tag=restaurant tag=work note="lunch with team"
2026-03-11 type=visit client=acme address="12 MG Road, Bangalore" city=Bangalore
2026-03-11 type=expense amount=50 note=ok
2026-03-11 type=expense note="said \"nothing\""
```

Invalid:

```text
2026-03-11 type=expense merchant=Big Bazaar
2026-03-11 type=expense tag="big shop"
2026-03-11 type=expense | lunch with team
2026-03-11 date=2026-03-11 type=expense
2026-03-11 type=expense note=lunch with team
2026-03-11 type=expense merchant="unterminated
```

---

## Keys vs tags vs free text

| Kind | Spaces? | Quotes? | Example |
|------|---------|---------|---------|
| Key names | No | No | `category`, `client_code` |
| `type` value | No | No | `type=expense` |
| `tag` value | No | No | `tag=restaurant` |
| Option fields (schema) | No (prefer) | No | `category=food` |
| Free-text fields | Yes if quoted | When needed | `address="12 MG Road"` |
| `note` | Yes if quoted | When needed | `note="lunch with team"` |

---

## Schema relationship

- Schema defines types, required fields, options, int/date, etc.
- Schema does **not** control whether a value is quoted on disk.
- Dropdown **options** remain **bare single tokens** (no spaces in option strings).
- UI may still *display* underscores as spaces via `_disp` for old data; v2 free text stores real spaces inside quotes.

---

## Migration from v1

### v1

```text
YYYY-MM-DD { SP key=value } [ SP? "|" note ]
# single-token values; often underscore-normalized; note after |
```

### Migrator

1. Parse with v1 parser.  
2. Map `| note` → `note` field.  
3. Emit v2 via canonical builder (quote note if spaces; leave existing `_` in tokens as-is).  
4. Atomic per-file write; dry-run required.  
5. Do **not** auto-convert `_` → space unless a separate explicit flag is added later.

### Dual-read

```text
parse_line:
  try v2
  on failure during migration window: try v1
write:
  always v2 when record_format >= 2
```

---

## PTOS code impact (checklist)

| Component | Work |
|-----------|------|
| `FORMAT.md` | Replace with v2 grammar, order, keys/tags rules, migration |
| `parse_line` / `build_record_line` | v2 implementations; tag never quoted; date positional |
| `normalize_field_value` | v2 free-text: no forced `_`; tags/options still single-token normalize |
| `clean_note` | Still flatten newlines for in-memory note; emit as `note=` |
| `append_record` | Reject CR/LF and failed round-trip |
| Web add/edit | Free text can POST spaces; builder quotes; tags still tokenize |
| CLI | Shared builder only |
| Schema / Types | Options stay bare tokens |
| Tests | Order emission, tag reject spaces, quote rules, migrator, no `date=` |
| AGENTS.md / CHANGELOG | Invariants |

---

## Acceptance criteria

- [ ] Date is bare leading `YYYY-MM-DD`, not `date=`.  
- [ ] Writer order: date → type → other fields → tags → note.  
- [ ] Keys and tag values are single tokens only.  
- [ ] Values with whitespace are double-quoted; tags never quoted.  
- [ ] No `|` in v2 output.  
- [ ] Quoting not derived from schema field type.  
- [ ] Parser requires only date-first; tolerates field reorder.  
- [ ] Migrator v1→v2 with dry-run; dual-read documented.  
- [ ] FORMAT.md + tests updated.  

---

## Implementation order

1. v2 parse/build + tests (including write order and tag rules).  
2. Gate writers on `record_format = 2`.  
3. Migrator + dual-read.  
4. FORMAT.md rewrite for PTOS.  
5. Starter/default when ready.

---

## Summary for implementers

```text
YYYY-MM-DD type=<token> <fields...> tag=<token>... note="optional spaces"

- Date positional first (never date=)
- type second on write
- tags = single tokens only
- note last; | gone
- quote values only when they need it (spaces / " / \)
- schema types validate; they do not control quotes
```
