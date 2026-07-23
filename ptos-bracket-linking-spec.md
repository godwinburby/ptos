# Feature Spec: `[[Bracket]]` Cross-Linking + Generalized Autocomplete

## Design

`[[brackets]]` are the cross-cutting link layer sitting *on top of*
Records/Todo's existing project conventions — not a replacement for
`project=value` (Records) or `+project` (Todo), which stay exactly as
they are since they're load-bearing for filtering. A `[[link]]` in a
note or journal entry is a real cross-reference; if it happens to match
an existing project name, that's a bonus connection, not something
engineered as equivalent. People/contacts fold into this too —
`[[Sam]]` needs no separate feature.

---

## 1. Detecting a `[[` token

Todo's current `_getCurrentToken()` splits on whitespace, which is
correct for `+project`/`@context`/`pri:` (none contain spaces) but wrong
for brackets — `[[some project]]` legitimately contains spaces inside
it. A distinct detector scans backward for the nearest unclosed `[[`:

```javascript
function _getBracketToken(input) {
  var val = input.value;
  var pos = input.selectionStart;
  var before = val.substring(0, pos);
  var openIdx = before.lastIndexOf("[[");
  if (openIdx === -1) return null;
  var closeIdx = before.lastIndexOf("]]");
  if (closeIdx > openIdx) return null;
  return {
    query: before.substring(openIdx + 2),
    start: openIdx,
    fullToken: val.substring(openIdx, pos),
  };
}
```

## 2. Shared autocomplete component

`attachBracketAutocomplete(inputEl)` is a self-contained function
defined in `base.html`. It adds an `input` event listener that:
1. Calls `_getBracketToken(inputEl)` — if null, closes any open dropdown
2. Fetches from `/api/link-candidates?q=...`
3. Renders a dropdown list below the input
4. Handles Arrow/Enter/Escape keyboard navigation
5. On pick: replaces the `[[...` span with `[[Selected]]`, re-focuses input
6. On blur: closes dropdown after 150ms delay (allows click events)

### Todo coexistence

In `todo.html`'s `onTodoInput()`, `_getBracketToken()` is checked first.
If it returns non-null, the bracket autocomplete handles the input — `[[`
takes priority over `+`/`@`/`pri:`. Otherwise falls through to existing
whitespace-splitting autocomplete logic.

## 3. Backend — `/api/link-candidates`

```python
@app.route("/api/link-candidates")
def api_link_candidates():
```

Returns up to 20 sorted candidates matching the query prefix.

**Sources scanned:**
| Source | What's indexed |
|---|---|
| Journal, Notes, Todo files | All text inside `[[ ]]` brackets (multi-word phrases like `[[buy house]]` work) |
| Record log files | `project=` and `context=` values from key=value lines |
| Todo projects | Project names from `get_projects()`, stripped of `+` prefix |

**How it works:**
- `\[\[([^\]]+)\]\]` regex extracts everything between `[[` and `]]` from all text files
- `\b(project|context)=(\S+)` regex extracts project/context values from record `.log` files
- `get_projects(todos + done)` provides todo project names (stripped of `+`)
- Deduplication via `seen` set (case-insistent)
- Results sorted alphabetically, capped at 20

## 4. Rendering — `[[link]]` becomes clickable in preview

`preprocessLinks(src)` converts `[[Target]]` into a search link:

```javascript
function preprocessLinks(src) {
  return src.replace(/\[\[([^\]]+)\]\]/g, function(_, target) {
    return "[" + target + "](/search?q=" + encodeURIComponent(target) + ")";
  });
}
```

Called in `_markdown_editor.html`'s `renderPreview()` before
`marked.parse()`. Only affects Journal and Notes preview — todo
textarea shows raw `[[text]]`.

Routing through `/search` rather than resolving to one exact page
keeps this simple — a link target might match a note, a journal
date, or a project, and search already shows all of them grouped.

## 5. Integration points

| Location | Element | How attached |
|---|---|---|
| Todo quick-add | `#todo-input` | Checked first in `onTodoInput()` |
| Journal editor | `#md-editor` | `setTimeout` in `_markdown_editor.html` IIFE |
| Notes editor | `#md-editor` | `setTimeout` in `_markdown_editor.html` IIFE |
| Add Record note | `input[name="note"]` | `DOMContentLoaded` in `add.html` |
| Edit Record note | `input[name="note"]` | `DOMContentLoaded` in `edit.html` |
| Sidebar search | `#sidebar-search` | Inline `<script>` in `base.html` |
| Search page | `#search-input` | Inline `<script>` in `search.html` |

## 6. Tests

- `TestLinkCandidates` — bracket links in notes, journal, multi-word phrases, todo projects, record project/context, no noise from pure numbers
- All in `tests/test_notes.py`
