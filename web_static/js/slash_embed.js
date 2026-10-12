// slash_embed.js — Notion/Logseq-style "/" command for the markdown editor.
//
// Typing "/" at the start of a line or after whitespace opens a filterable
// menu. The top "Format" group holds markdown helpers (headings, lists, task
// checkboxes, quotes, code blocks, tables, inline styling…). Below it, the
// embeddable query / metric / dashboard / threshold groups come from
// GET /api/embed/candidates; picking one inserts a fenced ```ptos block with
// just name (resolve_embed infers the kind). Choosing any item consumes the
// typed "/token" and dispatches an "input" event so the editor re-renders the
// preview and autosaves.
//
// Exposes window.attachSlashEmbed(textareaEl). Loaded after embeds.js.
(function () {
  var _groups = null;        // cached /api/embed/candidates groups
  var _fetching = false;
  var _pending = [];

  function _close(list) {
    list.style.display = "none";
    list.classList.remove("open");
  }

  function _lineStart(val, pos) {
    return val.lastIndexOf("\n", pos - 1) + 1;
  }

  function _lineEnd(val, pos) {
    var i = val.indexOf("\n", pos);
    return i === -1 ? val.length : i;
  }

  function _finish(list, el, caret) {
    _close(list);
    el.focus();
    el.setSelectionRange(caret, caret);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function _stripToken(el, tok) {
    el.value = el.value.slice(0, tok.start) + el.value.slice(tok.end);
    return tok.start;
  }

  function _prefix(pre) {
    return function (el, tok, list) {
      var p = _stripToken(el, tok);
      var val = el.value;
      var ls = _lineStart(val, p);
      var le = _lineEnd(val, p);
      el.value = val.slice(0, ls) + pre + val.slice(ls, le) + val.slice(le);
      _finish(list, el, ls + pre.length);
    };
  }

  function _wrap(open, close) {
    return function (el, tok, list) {
      var p = _stripToken(el, tok);
      var val = el.value;
      el.value = val.slice(0, p) + open + close + val.slice(p);
      _finish(list, el, p + open.length);
    };
  }

  function _block(openText, caretAt) {
    return function (el, tok, list) {
      var p = _stripToken(el, tok);
      var val = el.value;
      var before = val.slice(0, p);
      var after = val.slice(p);
      var lead = (before && !/\n$/.test(before)) ? "\n" : "";
      el.value = before + lead + openText + after;
      _finish(list, el, (before + lead + caretAt).length);
    };
  }

  var _FORMAT_GROUP = {
    kind: "f",
    label: "Format",
    items: [
      { label: "Heading 1", aliases: ["h1", "heading"], run: _prefix("# ") },
      { label: "Heading 2", aliases: ["h2"], run: _prefix("## ") },
      { label: "Heading 3", aliases: ["h3"], run: _prefix("### ") },
      { label: "Bulleted list", aliases: ["ul", "bullet"], run: _prefix("- ") },
      { label: "Numbered list", aliases: ["ol", "numbered"], run: _prefix("1. ") },
      { label: "Task list", aliases: ["todo", "checkbox", "checklist"], run: _prefix("- [ ] ") },
      { label: "Quote", aliases: ["blockquote", "quote"], run: _prefix("> ") },
      { label: "Code block", aliases: ["code", "fence"],
        run: _block("```text\n\n```\n", "```text\n") },
      { label: "Divider", aliases: ["hr", "divider", "line"], run: _block("---\n", "---\n") },
      { label: "Table", aliases: ["table", "grid"],
        run: _block("| Column | Column |\n| ------ | ------ |\n|        |        |\n", "| ") },
      { label: "Bold", aliases: ["b", "strong"], run: _wrap("**", "**") },
      { label: "Italic", aliases: ["i", "em"], run: _wrap("*", "*") },
      { label: "Strikethrough", aliases: ["s", "strike", "del"], run: _wrap("~~", "~~") },
      { label: "Inline code", aliases: ["code-inline"], run: _wrap("`", "`") },
      { label: "Link", aliases: ["link", "url", "hyperlink"], run: _wrap("[", "](url)") },
    ],
  };

  function _getSlashToken(el) {
    var val = el.value;
    var pos = el.selectionStart;
    var before = val.slice(0, pos);
    var m = /(^|\s)\/([A-Za-z0-9_-]*)$/.exec(before);
    if (!m) return null;
    return { start: pos - m[2].length - 1, end: pos, query: m[2] };
  }

  function _getList(el) {
    var id = el.id + "-slash-ac";
    var list = document.getElementById(id);
    if (!list) {
      list = document.createElement("div");
      list.id = id;
      list.className = "slash-ac-list";
      document.body.appendChild(list);
    }
    return list;
  }

  function _position(list, el) {
    var rect = el.getBoundingClientRect();
    var val = el.value.slice(0, el.selectionStart);
    var row = (val.match(/\n/g) || []).length;
    var lh = parseFloat(getComputedStyle(el).lineHeight) || 29;
    var top = rect.top + (row + 1) * lh - el.scrollTop;
    var maxTop = window.innerHeight - 220;
    if (top > maxTop) top = Math.max(rect.top, maxTop);
    list.style.left = Math.min(rect.left + 8, window.innerWidth - 340) + "px";
    list.style.top = top + "px";
  }

  function _filter(groups, q) {
    q = (q || "").toLowerCase();
    var out = [];
    groups.forEach(function (g) {
      var items = [];
      g.items.forEach(function (it) {
        var hay = it.run ? (it.label + " " + (it.aliases || []).join(" "))
                         : it;
        if (!q || hay.toLowerCase().indexOf(q) !== -1) items.push(it);
      });
      if (items.length) out.push({ kind: g.kind, label: g.label, items: items });
    });
    return out;
  }

  function _label(it) {
    return it.run ? it.label : it;
  }

  function _render(el, tok, list) {
    var groups = [_FORMAT_GROUP];
    if (_groups !== null) groups = groups.concat(_groups);
    var matched = _filter(groups, tok.query);
    if (!matched.length) { _close(list); return; }
    var flat = [];
    var html = "";
    matched.forEach(function (g) {
      html += '<div class="slash-ac-group">' + g.label + "</div>";
      g.items.forEach(function (it) {
        html += '<div class="bracket-ac-item slash-ac-item" data-idx="' +
          flat.length + '">' + _label(it) + "</div>";
        flat.push(it);
      });
    });
    if (_groups === null && _fetching) {
      html += '<div class="slash-ac-empty">Loading queries…</div>';
    }
    list.innerHTML = html;
    list._flat = flat;
    list._tok = tok;
    list.style.display = "block";
    list.classList.add("open");
    _position(list, el);

    var idx = -1;
    function _activate(i) {
      idx = i;
      list.querySelectorAll(".slash-ac-item").forEach(function (itemEl, j) {
        itemEl.classList.toggle("active", j === idx);
      });
    }
    list._activate = _activate;
    list.querySelectorAll(".slash-ac-item").forEach(function (itemEl) {
      itemEl.addEventListener("mousedown", function (e) {
        e.preventDefault();
        _commit(el, list, parseInt(itemEl.dataset.idx, 10));
      });
    });
  }

  function _commit(el, list, idx) {
    var it = list._flat[idx];
    if (!it) return;
    if (it.run) it.run(el, list._tok, list);
    else _insert(el, list._tok, it, list);
  }

  function _insert(el, tok, name, list) {
    var before = el.value.slice(0, tok.start);
    var after = el.value.slice(tok.end);
    var lead = (before && !/\n$/.test(before)) ? "\n" : "";
    var fence = '```ptos\nname = "' + name + '"\n```\n';
    el.value = before + lead + fence + after;
    _finish(list, el, (before + lead + fence).length);
  }

  function _load(cb) {
    if (_groups !== null) { cb(); return; }
    _pending.push(cb);
    if (_fetching) return;
    _fetching = true;
    fetch("/api/embed/candidates")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        _groups = (d && d.ok && d.groups) ? d.groups : [];
        _fetching = false;
        _pending.splice(0).forEach(function (f) { f(); });
      })
      .catch(function () {
        _groups = [];
        _fetching = false;
        _pending.splice(0).forEach(function (f) { f(); });
      });
  }

  window.attachSlashEmbed = function (el) {
    if (!el) return;
    var list = _getList(el);

    el.addEventListener("input", function () {
      var tok = _getSlashToken(el);
      if (!tok) { _close(list); return; }
      _load(function () { _render(el, tok, list); });
    });

    el.addEventListener("keydown", function (e) {
      if (!list.classList.contains("open")) return;
      var flat = list._flat || [];
      var active = list.querySelector(".slash-ac-item.active");
      var cur = active ? parseInt(active.dataset.idx, 10) : -1;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (cur === -1) cur = 0;
        list._activate(Math.min(cur + 1, flat.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (cur === -1) cur = 0;
        list._activate(Math.max(cur - 1, 0));
      } else if (e.key === "Enter" || e.key === "Tab") {
        if (cur !== -1) {
          e.preventDefault();
          _commit(el, list, cur);
        }
      } else if (e.key === "Escape") {
        _close(list);
      }
    });

    el.addEventListener("blur", function () {
      setTimeout(function () { _close(list); }, 150);
    });

    el.addEventListener("scroll", function () {
      if (list.classList.contains("open")) _position(list, el);
    });
  };
})();