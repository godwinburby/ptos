# SPEC: Paste to Record (clipboard-first capture, validated append or reviewed convert)

**Project:** PTOS
**Feature name:** Paste to Record
**Supersedes:** `SPEC-add-from-line.md` (uploaded earlier) — this version
corrects that spec's Kind B design after review. Kind A is materially
unchanged; Kind B is substantially different — see §0.

**Goal:** Let a person paste clipboard content — from another app, a
scraped source, or their own typing — and get one of two outcomes:
1. If it's already a valid PTOS record line → **validate, then append
   directly**. No review screen; nothing to review.
2. If it's free-form text → **route through the existing capture-and-convert
   review flow**, pre-filled by the existing scraper, so a person confirms
   the suggested type/fields before anything structured is written.

**Invariants (do not break):**
- One record = one line (`YYYY-MM-DD type=… key=value … | note`)
- Atomic append via existing `append_record` / service wrapper
- Schema validation via existing `validate_record` (same semantics as
  `POST /add` and `ptos -a`)
- CLI remains usable offline with stdlib-only core (`ptos.py` +
  `ptos_cli.py`); web may use the service layer
- Log Editor save stays the unvalidated raw power-user path — unchanged
- **New invariant this revision adds:** free-form text never becomes a
  final structured record without being shown to the person first. Silent
  auto-conversion is explicitly out of scope (see §5).

---

## 0. What changed from the original spec, and why

The original spec's Kind B wrote `type=capture` directly and considered
the job done. Two problems with that, surfaced during review:

1. **It reinvented an existing function.** `ptos_service.py` already has
   `capture(text, date=None, tag=None, links=None)` — checks the `capture`
   type exists in schema, rejects empty text, builds the record, appends
   it. This is Kind B's entire "build + append" step, already working,
   already wired to `POST /api/capture`. The original spec would have
   built a second, parallel implementation of the same four lines of
   logic.
2. **It skipped review entirely**, but the actual want (per follow-up
   discussion) is: free text should land on the same reviewed
   suggest-type / scrape-fields / confirm screen that capture-inbox items
   already go through when converted — not a silent one-shot write. The
   codebase already has this machinery: `suggest_convert_type()`,
   `scrape_convert_fields()`, `convert_draft()`, `convert_record()`. None
   of it needs to be rebuilt; it needs to be *triggered automatically*
   right after paste instead of waiting for someone to find the item in
   the capture inbox later.

Net effect: this revision needs **less new code** than the original spec,
not more — Kind B becomes "call two existing functions in sequence and
redirect," not a new write path.

---

## 1. Two input kinds (detection unchanged from original spec)

Classification rules, applied in order on the stripped, single-line input:

1. Empty → error.
2. Multi-line (more than one non-empty line) → error in v1 (document; do
   not silently join lines).
3. If input **parses** as a PTOS line (via existing `safe_parse_line`) and
   the parsed `kv` contains a non-empty `type` → **Kind A**.
4. Else → **Kind B**.

Notes carried over unchanged from the original spec:
- A string that looks line-shaped (`type=expense amount=abc`) but fails
  validation stays **Kind A** and is rejected with problems — it must
  never silently fall back to capture. Falling back would hide a genuine
  mistake as if it were intentional free text.
- Only fall through to Kind B when the text is not line-shaped at all
  (no `type=` present).

---

## 2. Kind A — proper PTOS line → validate → append directly

Unchanged from the original spec.

```text
YYYY-MM-DD type=<type> key=value key=value tag=t1 tag=t2 | optional note
```

Pipeline for a Kind A input `raw`:

1. Parse via `parse_line`/`safe_parse_line` → `(date, kv, note)`.
2. If no leading date: use today (same resolution as CLI `-a` without
   `-d`).
3. `schema = ptos.get_schema()`; `problems = validate_record(schema, kv)`.
4. If `problems` non-empty → return/display all problems, **no write**.
5. If valid → `line = build_record_line(date, kv, note)`;
   `append_record(line)` (or `svc.append_record` on web).
6. Report success (path/lineno) or the full problem list — no partial
   writes either way.

No review screen for Kind A. There's nothing to review: either it's a
valid record and gets written, or it's invalid and gets rejected with
specific errors.

---

## 3. Kind B — free-form text → capture → immediate reviewed convert

This is the corrected flow. Three steps, all reusing existing functions:

### Step 1 — write the anchor capture record
Call the **existing** `svc.capture(text, date=date_override)` — do not
reimplement schema-check/empty-check/build/append; this function already
does exactly that and is already used by the Home Capture box and
`POST /api/capture`.

- If `capture` type is missing from schema: `svc.capture()` already raises
  `PTOSError` with a clear message — surface that as-is, no new error
  message needed.
- If text is empty: same — already handled.

### Step 2 — get conversion suggestions
Call the **existing** `suggest_convert_type(text, source_kv=..., use_history=True, schema=schema)`
to guess the target type, then `scrape_convert_fields(text, rtype=<suggested_type>, schema=schema)`
to pre-fill field values from the text (amount, option-value tokens,
tags, date — see §6 for exactly what this matches).

### Step 3 — redirect into the existing convert-review screen
Land the person on the same review UI already used when converting an
item from the capture inbox, pre-populated with the suggested type and
scraped fields, referencing the capture record just written in Step 1
(`filepath`, `lineno` from `svc.capture()`'s return value — this is
exactly the `old_line, lineno` shape `convert_draft()`/`convert_record()`
already expect).

- Person reviews, adjusts anything the scraper got wrong or left blank,
  and saves.
- Save runs through the **existing** convert path (`convert_record()`),
  which already validates via `validate_record` before writing the final
  structured record and marks the original capture line as converted
  (`_mark_converted`).
- If the person abandons the review screen without saving: the capture
  record from Step 1 remains in the inbox exactly as if they'd typed it
  into the Home Capture box directly — nothing is lost, it's just an
  unconverted inbox item, same as today's existing behavior for any
  capture nobody's gotten around to converting yet.

**No new validation logic, no new write function, no new "auto-convert"
step** — Kind B is "call `capture()`, call the two suggestion functions,
redirect to the existing convert screen" and stops there. See §5 for why
skipping straight to a written structured record is explicitly rejected.

---

## 4. Retrofit while touching this code: `capture()` doesn't validate today

Confirmed by reading `ptos_service.py`: `capture()` currently does **not**
call `validate_record()` — it only checks the `capture` type exists in
schema and the text is non-empty. This hasn't mattered because
`type.capture` has zero required fields in the starter schema, but it's a
latent gap: if a required field is ever added to `capture`, this path
wouldn't enforce it.

**Fix while in this code, not deferred**: add a `validate_record(schema,
record)` call to `capture()` itself (not a new parallel function), so
both `/api/capture` and this new Kind B path get the fix simultaneously
instead of only the new path being validated.

---

## 5. Non-goal: no silent auto-conversion

Explicitly rejecting a tempting shortcut: Kind B must **not** skip Step 3
and write a fully-guessed structured record directly, even when the
scraper is confident. The scraper's own docstring calls its output
"advisory only" — it's a rule-based heuristic (exact option-token
matching, regex amount extraction), not a validated interpretation of
intent. A paste from another app that happens to contain the word
matching a schema option value (e.g. a note that mentions "self" in an
unrelated sentence) could produce a wrong-but-plausible-looking field
guess. The review screen is the safety net; removing it in the name of
convenience reintroduces exactly the "fails silently in a way you don't
notice" failure mode the original Log Editor problem (unvalidated saves)
already demonstrates the cost of.

---

## 6. Guidance on writing free-form text (for hint text / README, not code)

Not a parsing change — this is documentation the paste UI and CLI
`--help` should surface, since it determines how well-prefilled the
review screen ends up being. Confirmed against `scrape_convert_fields`'s
actual matching logic:

- **The scraper matches natural words against your schema's real option
  values** (lowercased, spaces→underscores) — it does not parse
  `field=value` or `field: value` syntax in free text. Writing
  `domain: self category: transport` will **not** parse correctly — the
  colon breaks tokenization, so `domain:` matches nothing.
- **Use your actual schema vocabulary in a normal sentence**:
  `"rs150 auto to clinic"` — `auto` matches a real tag option, `rs150`
  matches the currency-prefixed amount pattern (preferred over a bare
  number).
- **Prefix amounts with a currency marker** (`rs`, `inr`, `$`, `₹`) when
  precision matters — a bare number is only a fallback match.
- **Tags**: `@tag`/`+tag`/`#tag` are matched explicitly and reliably. A
  bare trailing word after a connector ("for", "with", "on") is also
  checked, but only the *last* word of the note — don't rely on this for
  anything beyond one trailing tag.
- **Dates**: natural expressions (`today`, `yesterday`, `last monday`) are
  recognized; omitting one defaults to today.
- **If you want zero review and a deterministic result, don't use free
  text at all — paste a real Kind A line instead.** `type=` presence is
  the entire fork between "straight append" and "reviewed convert"; there
  is no in-between "mostly-structured free text" mode.

Both examples (a real line, and a natural free-text capture) should appear
side by side in the paste-box hint text and CLI `--help`, matching the
original spec's intent — but now accurately describing what actually gets
matched.

---

## 7. Shared classification/dispatch (CLI and web must match)

One pipeline, one place:

```python
def paste_to_record(raw, date_override=None, dry_run=False):
    # 1. normalize/reject per §1 rules 1-2
    # 2. classify per §1 rule 3-4
    # 3a. Kind A → validate/build/append per §2, OR
    # 3b. Kind B → svc.capture() + suggestion functions per §3
    # returns a result describing which kind, and either
    #   {"kind": "line", "ok": True/False, ...}
    # or
    #   {"kind": "capture", "ok": True, "filepath":..., "lineno":...,
    #    "suggested_type":..., "scraped_fields": {...}}
```

- Prefer implementing this in `ptos.py` (Kind A path — stdlib-only, CLI
  needs it offline) with a thin `ptos_service.py` wrapper that adds the
  Kind B branch (since `suggest_convert_type`/`scrape_convert_fields`
  already live in the service layer, not the CLI-only core).
- `ptos_cli.py` and `ptos_web.py` both call this one function — no
  duplicate classification logic in either.

---

## 8. CLI

### Interface
```text
ptos --paste [TEXT]
```
(Dropping the original spec's `-A` alias — see §9.)

| Invocation | Behavior |
|---|---|
| `ptos --paste "2026-09-14 type=expense …"` | Use argument as input |
| `ptos --paste` with no argument | Read one line from stdin (`pbpaste \| ptos --paste`, `Get-Clipboard \| ptos --paste`) |
| `ptos --paste`, stdin is a TTY | Error: "provide TEXT or pipe input on stdin" |

### Flags
| Flag | Purpose |
|---|---|
| `--date YYYY-MM-DD` | Override/resolve date |
| `--dry-run` | Parse + classify + validate only; for Kind A, print the canonical line; for Kind B, print the suggested type + scraped fields; never write |

### Kind B on the CLI — no interactive review in v1
The CLI doesn't have a web review screen. For v1:
- `ptos --paste "free text"` still writes the capture anchor (Step 1) —
  same as today's `ptos --cap`, no change there.
- It prints the suggested type + scraped fields to stdout (from Steps
  2) as an FYI, but does **not** auto-convert.
- Converting still happens the normal existing way — CLI's existing
  convert command/interactive flow, or the web review screen next time
  they're in the browser.
- This keeps Kind B's "never write a structured record without review"
  invariant intact even on a UI-less surface, rather than inventing a CLI
  interactive-review mode as new scope for v1.

### Exit codes
| Code | Meaning |
|---|---|
| 0 | Kind A: validated and appended (or dry-run ok). Kind B: capture written successfully. |
| 1 | Kind A validation failure (problems to stderr). Kind B: capture failed (e.g. empty text, missing capture type). |
| 2 | Usage / I/O error |

---

## 9. Web UI

### A. `/add` page — clipboard-first

Promoted from the original spec's "optional convenience" to the primary
interaction, per follow-up discussion:

1. Primary control: **"Paste from clipboard"** button —
   `navigator.clipboard.readText()` (HTTPS or localhost). On success,
   immediately classify and act (Kind A → append + confirm; Kind B →
   redirect to convert-review).
2. Fallback (when clipboard permission isn't available, or the person
   wants to type/edit before submitting): a manual textarea + "Add"
   button, same classify/dispatch behind it.
3. On Kind A success: same success UX as the normal Add form (flash
   "Record added", redirect to Browse/`return_to`).
4. On Kind A failure: stay on page, show the problem list (same style as
   existing form validation errors), keep the pasted text in the box.
5. On Kind B: redirect straight into the convert-review screen (§3, Step
   3) — the person never sees an intermediate "capture saved" state
   requiring a separate click to continue.

### B. API (for AHK, PowerShell, other apps/scripts)

```http
POST /api/paste
Content-Type: application/json
{"text": "..."}
```
or raw:
```http
POST /api/paste
Content-Type: text/plain

<pasted content>
```

Response, Kind A:
```json
{"kind": "line", "ok": true, "line": "<canonical>", "path": "records/2026.log", "lineno": 123}
```
```json
{"kind": "line", "ok": false, "error": "validation failed", "problems": ["Missing required field: amount"]}
```

Response, Kind B:
```json
{"kind": "capture", "ok": true, "filepath": "records/2026.log", "lineno": 124,
 "suggested_type": "expense", "scraped_fields": {"amount": "150", "category": "transport"},
 "review_url": "/convert?filepath=...&lineno=124"}
```

The caller (an external script) gets a `review_url` to open in a browser
if they want to finish the conversion right away, or can leave it — the
capture record already exists in the inbox either way, same as any other
capture.

Auth: same as other mutating routes — if `[auth] enabled`, require the
existing session/auth mechanism. No new unauthenticated write surface.

### C. Log Editor
No change, per original spec — stays the raw, unvalidated power-user
path. Optional one-line hint pointing at this feature instead.

---

## 10. Files to touch (expected)

| File | Change |
|---|---|
| `ptos.py` | Kind A helper (parse/validate/build/append) — stdlib-only |
| `ptos_service.py` | `paste_to_record()` wrapper adding Kind B branch (calls existing `capture`, `suggest_convert_type`, `scrape_convert_fields`); add `validate_record` call inside existing `capture()` (§4) |
| `ptos_cli.py` | `--paste` flag, stdin wiring, help text |
| `ptos_web.py` | `POST /add-paste` (or reuse `/add` with a mode param — implementer's call), `POST /api/paste` |
| `web_templates/add.html` | Clipboard-first button + fallback textarea + error display |
| `tests/…` | Kind A success/failure; Kind B → capture written + suggestions returned + **no structured record written until convert-review saves**; `capture()`'s new validate_record call |
| `CHANGELOG.md` | Entry under Added, referencing this as superseding the earlier "Add from line" draft |
| `README.md` | Windows clipboard examples; vocabulary guidance from §6 |

Avoid new dependencies.

---

## 11. Tests (required)

**Kind A** — unchanged from original spec: valid line appends; missing
required field rejects; unknown field rejects; invalid option value
rejects; date-omitted-but-valid still appends with today's date;
line-shaped-but-invalid never falls back to capture.

**Kind B (revised)**
1. Plain sentence → `capture()` called, anchor record written, **no
   structured record written**.
2. Suggested type + scraped fields returned match what
   `suggest_convert_type`/`scrape_convert_fields` would independently
   produce for the same text (i.e. this feature doesn't reimplement or
   diverge from those functions).
3. Capture type missing from schema → clear error, no write (same
   message `capture()` already raises).
4. Empty/whitespace-only → error, no write.
5. `capture()`'s new `validate_record` call: a schema change that adds a
   required field to `type.capture` causes `capture()` to reject text
   that doesn't satisfy it (regression test for §4's retrofit).

**Shared**
6. Multi-line input → error (v1 single-line).
7. Dry-run (CLI): Kind A prints canonical line, no write; Kind B prints
   suggested type/fields, no write (not even the capture anchor).
8. API Kind A/Kind B response shapes match CLI semantics.

Use existing test isolation (`conftest`/tmp data dir); never touch real
user logs.

---

## 12. Acceptance criteria

- [ ] Kind A: CLI/web accept a full PTOS line → validate → append (or
      problems, no write)
- [ ] Invalid Kind A never silently becomes a capture
- [ ] Kind B: free text writes a capture record via the **existing**
      `capture()` function (not a reimplementation)
- [ ] Kind B: person is redirected into the **existing** convert-review
      screen, pre-filled via the **existing** `suggest_convert_type`/
      `scrape_convert_fields` functions
- [ ] No structured (non-capture) record is ever written without a person
      confirming on the review screen — verified by a test that pastes
      free text and checks only the capture line exists until convert
      explicitly saves
- [ ] `capture()` now calls `validate_record` (both `/api/capture` and
      this new path benefit)
- [ ] CLI `--paste` (argument or stdin) works for both kinds; Kind B on
      CLI writes the capture and prints suggestions but does not
      auto-convert
- [ ] Web `/add` clipboard button is the primary interaction; manual
      textarea is the fallback
- [ ] `POST /api/paste` response shape matches CLI semantics for both
      kinds, including a `review_url` for Kind B
- [ ] Auth still applies to web write routes when enabled
- [ ] Free-text vocabulary guidance (§6) is present in both the web hint
      text and CLI `--help`
- [ ] Log Editor behavior unchanged (still raw), optional hint only
- [ ] All tests in §11 pass

---

## 13. Implementation order

1. Retrofit `validate_record` into existing `capture()` (§4) — small,
   independent, do first
2. Kind A helper in `ptos.py` + tests
3. CLI `--paste` (Kind A working end-to-end; Kind B writes capture +
   prints suggestions, no auto-convert)
4. `ptos_service.py` `paste_to_record()` wrapper (Kind B branch calling
   existing suggest/scrape functions)
5. `POST /api/paste` + `/add` clipboard-first UI, wired to redirect Kind B
   into the existing convert-review screen
6. README/CHANGELOG + vocabulary guidance (§6) + Windows clipboard
   one-liners

---

## 14. Non-goals (v1)

- Bulk import of whole files (unchanged from original spec)
- Changing Log Editor save to schema-validate every line
- GUI native Windows app
- Auto-reading clipboard inside CLI without OS tools (`Get-Clipboard`/
  `pbpaste` stay external)
- New record grammar incompatible with existing logs
- **Silent auto-conversion of Kind B to a structured record without
  review** (§5 — new non-goal this revision adds explicitly)
- A CLI interactive review/convert mode (§8 — Kind B stays
  "write capture, print suggestions, stop" on the CLI in v1)
- Chat bot (Telegram/WhatsApp/SMS) or email-to-record ingestion — deferred
  per §16; revisit only if "no Tailscale connection at capture time"
  becomes a real recurring limitation

---

## 15. Design rationale (for implementers)

- **Two input kinds, one pipeline** — clipboard may be a finished PTOS
  line or messy human text; both are daily realities.
- **Kind A fails closed** — a line that looks like a record but fails
  validation must not be rewritten as capture; that would hide a schema
  mistake.
- **Kind B reuses, not reimplements** — `capture()`,
  `suggest_convert_type()`, and `scrape_convert_fields()` already exist
  and already work; this feature's entire job is calling them in sequence
  and redirecting, not building a parallel path.
- **Review is mandatory for Kind B, not optional** — the scraper is
  advisory-only by its own design; skipping the review screen would trade
  a small convenience for silently-wrong records, which is a worse
  failure mode than the current "sits unconverted in the inbox" state.
- **Clipboard-first web UI** matches how the feature is actually meant to
  be used (scraped from another app, not hand-typed into a box) —
  promoted from the original spec's "optional convenience" status.
- **CLI stays honest about its limits** — no invented interactive-review
  mode; Kind B on the CLI writes the capture and stops, same guarantee as
  the web path (nothing structured without review), just without a UI to
  review in.

---

## 16. Remote clients ("from afar") — v1 recommendation

Every option here is **a different client calling `POST /api/paste`** —
none of them add a new server-side ingestion path. This keeps the "one
shared pipeline" principle intact: `/api/paste` is the only doorway;
everything below is just a more convenient way to reach it.

### Recommended for v1: phone Shortcut (iOS Shortcuts / Android Tasker or
### HTTP Shortcuts)

- Select text in any app (browser, WhatsApp, email) → Share sheet → "Add
  to PTOS" → fires a POST to `/api/paste` over Tailscale.
- Voice variant, same Shortcut: "Hey Siri/Assistant, log expense" →
  dictation → same POST. Not a separate mechanism, just a different
  trigger into the same Shortcut.
- **Zero new server code** — this is purely a client-side configuration
  task once `/api/paste` exists per §9.B.
- Works anywhere Tailscale reaches (i.e., anywhere with internet), which
  satisfies "from afar" without any new infrastructure.

### Also zero-new-server-code, worth wiring if useful, not required for v1
- **Browser bookmarklet** (desktop) — select text on a webpage, click a
  bookmarklet, POSTs the selection. Best fit for the "scraped from another
  app" case specifically when that app is a website.
- **Windows hotkey/tray script** (AHK/PowerShell) — already covered by the
  clipboard examples in §8/§10; same endpoint, no new work beyond what's
  already speced.

### Deferred, not v1: chat bot or email-to-record

- A Telegram/WhatsApp/SMS bot, or a forward-to-an-address email poller,
  are the only options that don't require an active Tailscale connection
  at capture time — genuinely more "from afar" than the Shortcut option.
- Both require real new infrastructure (hosting/running a bot, managing a
  webhook, or polling an inbox) for a narrower problem (no-VPN capture)
  than what the Shortcut option already solves.
- **Decision: build the Shortcut first.** Only revisit a bot/email path if
  "no Tailscale connection at capture time" turns out to be a real,
  recurring limitation in practice — not a speculative one.

### What the Shortcut needs from the API (implementer note)

- The `/api/paste` response shape from §9.B already covers this: Kind A
  returns `ok`/`problems`; Kind B returns `review_url`.
- The Shortcut should show a notification on response — for Kind A,
  success/failure with the problem list if any; for Kind B, a notification
  containing (or linking to) `review_url` so the person can jump straight
  into the convert-review screen later, without having to go find the item
  in the capture inbox themselves.
- No change to `/api/paste` itself is required to support this — it's
  purely a client-side (Shortcut) configuration matter.

### Acceptance criteria addition
- [ ] A documented Shortcut (iOS and/or Android, whichever platform is
      actually used) exists that POSTs clipboard/shared text to
      `/api/paste` and surfaces the response (success/problems for Kind A,
      `review_url` for Kind B) as a notification
- [ ] No new server-side route or ingestion path was added to support
      this — confirms the "one shared pipeline" principle held
