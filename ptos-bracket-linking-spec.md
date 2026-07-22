# Feature Spec: `[[Bracket]]` Cross-Linking + Generalized Autocomplete

## Design, per your own framing

`[[brackets]]` are the cross-cutting link layer sitting *on top of*
Records/Todo's existing project conventions — not a replacement for
`project=value` (Records) or `+project` (Todo), which stay exactly as
they are since they're load-bearing for filtering. A `[[link]]` in a
note or journal entry is a real cross-reference; if it happens to match
an existing project name, that's a bonus connection, not something
engineered as equivalent. People/contacts fold into this too —
`[[Sam]]` needs no separate feature.

---

## 1. Detecting a `[[` token — needs its own parser, not the existing
whitespace-word one

Todo's current `_getCurrentToken()` splits on whitespace, which is
correct for `+project`/`@context`/`pri:` (none contain spaces) but wrong
for brackets — `[[some project]]` legitimately contains spaces inside
it. Needs a distinct detector:

```javascript
function _getBracketToken(input) {
  var val = input.value;
  var pos = input.selectionStart;
  var before = val.substring(0, pos);
  var openIdx = before.lastIndexOf("[[");
  if (openIdx === -1) return null;
  var closeIdx = before.lastIndexOf("]]");
  if (closeIdx > openIdx) return null;  // already closed, not mid-link
  return {
    query: before.substring(openIdx + 2),
    start: openIdx,
    fullToken: val.substring(openIdx, pos),
  };
}
```

Scans backward for the nearest unclosed `[[` rather than splitting on
whitespace — correctly handles multi-word link targets.

## 2. Shared autocomplete component — generalize, don't duplicate

Extract Todo's existing dropdown rendering (`todo-ac-list` markup +
`onTodoInput`/`pickAC` pattern) into a reusable function taking an input
element and a candidate-fetch function, so it can attach to any text
field:

```javascript
function attachBracketAutocomplete(inputEl, fetchCandidates) {
  inputEl.addEventListener("input", function() {
    var tok = _getBracketToken(inputEl);
    var list = _getOrCreateAcList(inputEl);
    if (!tok) { list.classList.remove("open"); return; }
    fetchCandidates(tok.query).then(function(items) {
      _renderAcList(list, items, function(picked) {
        var before = inputEl.value.substring(0, tok.start);
        var after = inputEl.value.substring(tok.start + tok.fullToken.length);
        inputEl.value = before + "[[" + picked + "]]" + after;
        inputEl.focus();
      });
    });
  });
}
```

Attach this to: Records' free-text fields, Todo's quick-add (alongside
its existing `+`/`@`/`pri:` autocomplete, not replacing it), Journal's
editor, Notes' editor.

### Todo coexistence

Todo's quick-add has its own `_getCurrentToken()` that splits on
whitespace and matches `+`, `@`, `due:`, `t:`, `rec:`, `pri:`, `(`.
The bracket detector runs in parallel: `_getBracketToken()` scans for
an unclosed `[[` regardless of whitespace. Priority logic in
`onTodoInput`:

1. Call `_getBracketToken(input)` first. If it returns non-null, show
   bracket autocomplete dropdown and return — `[[` takes priority since
   it's an explicit user gesture.
2. Otherwise fall through to existing `_getCurrentToken()` logic for
   `+`/`@`/`pri:` etc.

This means typing `[[project name` shows bracket candidates, while
typing `+project` still shows the existing project list. The two
systems never interfere because `[[` is a distinct prefix that
whitespace-splitting would break anyway.

## 3. Backend — one endpoint providing linkable candidates

```python
@app.route("/api/link-candidates")
def link_candidates():
    q = request.args.get("q", "").lower()
    results = []
    # Note titles
    for path in glob.glob(os.path.join(NOTES_DIR, "*", "*.md")):
        title = _extract_title(path)
        if q in title.lower():
            results.append(title)
    # Journal dates (link by date, e.g. [[2026-07-21]])
    for path in glob.glob(os.path.join(JOURNAL_DIR, "*", "*", "*.md")):
        date_str = os.path.basename(path).replace(".md", "")
        if q in date_str:
            results.append(date_str)
    # Existing +project/project= values already in use (bonus overlap,
    # not a merge of the two systems)
    todos, _ = ptos_todo.load_todos(TODO_PATH)
    done, _ = ptos_todo.load_todos(DONE_PATH)
    results.extend(p for p in ptos_todo.get_projects(todos + done) if q in p.lower())
    return jsonify(sorted(set(results))[:20])
```

Same linear-scan philosophy as universal search — no index, fine at
personal scale.

### `_extract_title(path)`

Reads the first line of a note file. If it starts with `# `, returns
the heading text (stripped). Otherwise falls back to the filename slug
with dashes replaced by spaces and title-cased. Mirrors the logic in
`list_notes()` (`ptos.py:3978`).

```python
def _extract_title(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            first = f.readline().strip()
        if first.startswith("# "):
            return first[2:]
    except Exception:
        pass
    slug = os.path.splitext(os.path.basename(path))[0]
    return slug.replace("-", " ").title()
```

## 4. Rendering — `[[link]]` becomes clickable in preview

Wherever `marked.js` already renders markdown (Journal, Notes preview
panes), add a pre-processing step converting `[[Target]]` into a real
link before handing off to `marked.parse()`:

```javascript
function preprocessLinks(src) {
  return src.replace(/\[\[([^\]]+)\]\]/g, function(_, target) {
    return "[" + target + "](/search?q=" + encodeURIComponent(target) + ")";
  });
}
```

Integration: call `preprocessLinks(src)` in `_markdown_editor.html`'s
`renderPreview()` before passing to `marked.parse()`:

```javascript
pane.innerHTML = typeof marked !== "undefined"
  ? marked.parse(preprocessLinks(src))
  : "<pre style='white-space:pre-wrap'>" + ... + "</pre>";
```

Routing through `/search` rather than trying to resolve to one exact
page keeps this simple — a link target might match a note, a journal
date, or a project across multiple domains, and search already shows
all of them grouped, which is the correct behavior here rather than
guessing one destination.

## Testing requirements

- Typing `[[` in any of the four attached fields opens the dropdown;
  typing a multi-word query (`[[atomic hab`) correctly narrows results,
  confirming the whitespace-splitting bug this custom detector avoids
- Picking a candidate correctly replaces just the `[[...` portion being
  typed, preserving text before and after it
- A rendered `[[Target]]` in Journal/Notes preview is a clickable link
  to `/search?q=Target`
- Todo's existing `+project`/`@context`/`pri:` autocomplete is
  unaffected — this is additive, not a replacement
- A `[[link]]` target matching an existing `+project`/`project=` value
  surfaces that connection in search results, without either system
  needing to know about the other's existence
