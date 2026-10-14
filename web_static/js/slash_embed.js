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
// Exposes window.attachSlashEmbed(textareaEl), window.openSlashMenu(el)
// (backing the editor's "Insert view" toolbar button) and
// window.openSlashPicker(anchorEl, onPick) — the programmatic picker Blocks
// mode uses for its "+" and "change" controls. All three share one menu core
// (Format group, candidate groups, time-window step), so they cannot drift.
// onPick receives {kind:"md", seed, xform} for a Format helper (xform says
// how to apply it to a block that already has text) or {kind:"widget",
// source} for an embed (after the time-window step). Loaded after embeds.js.
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

  // `run` mutates the textarea (the "/" path); `seed` is the same helper as a
  // ready-made markdown skeleton, used by Blocks mode's programmatic picker
  // (openSlashPicker) where there is no caret to insert at. Inline helpers
  // pre-wrap their placeholder text so a fresh block isn't empty.
  // `xform` tells Blocks mode how to apply the same helper to a block that
  // already has text, so changing a paragraph into a heading or a bullet
  // keeps the paragraph instead of discarding it for the skeleton. `run`
  // always acts on an empty insertion point; `xform` acts on existing
  // content. Shapes:
  //   { t:"prefix", pre:"# ", first:true }  -> prepend `pre` to the first line
  //   { t:"prefix", pre:"- ", all:true }    -> prepend `pre` to every line
  //   { t:"wrap", open:"**", close:"**" }  -> wrap the existing text
  //   { t:"link" }                          -> "[text](url)"
  //   { t:"fence", lang:"text" }            -> wrap the text in a code fence
  //   { t:"replace" }                       -> discard text, use the skeleton
  var _FORMAT_GROUP = {
    kind: "f",
    label: "Format",
    items: [
      { label: "Heading 1", aliases: ["h1", "heading"], seed: "# ",
        run: _prefix("# "), xform: { t: "prefix", pre: "# ", first: true } },
      { label: "Heading 2", aliases: ["h2"], seed: "## ", run: _prefix("## "),
        xform: { t: "prefix", pre: "## ", first: true } },
      { label: "Heading 3", aliases: ["h3"], seed: "### ",
        run: _prefix("### "), xform: { t: "prefix", pre: "### ", first: true } },
      { label: "Bulleted list", aliases: ["ul", "bullet"], seed: "- ",
        run: _prefix("- "), xform: { t: "prefix", pre: "- ", all: true } },
      { label: "Numbered list", aliases: ["ol", "numbered"], seed: "1. ",
        run: _prefix("1. "), xform: { t: "prefix", pre: "1. ", all: true } },
      { label: "Task list", aliases: ["todo", "checkbox", "checklist"],
        seed: "- [ ] ", run: _prefix("- [ ] "),
        xform: { t: "prefix", pre: "- [ ] ", all: true } },
      { label: "Quote", aliases: ["blockquote", "quote"], seed: "> ",
        run: _prefix("> "), xform: { t: "prefix", pre: "> ", all: true } },
      { label: "Code block", aliases: ["code", "fence"],
        seed: "```text\n\n```",
        run: _block("```text\n\n```\n", "```text\n"),
        xform: { t: "fence", lang: "text" } },
      { label: "Divider", aliases: ["hr", "divider", "line"], seed: "---",
        run: _block("---\n", "---\n"), xform: { t: "replace" } },
      { label: "Table", aliases: ["table", "grid"],
        seed: "| Column | Column |\n| ------ | ------ |\n|        |        |",
        run: _block("| Column | Column |\n| ------ | ------ |\n|        |        |\n", "| "),
        xform: { t: "replace" } },
      { label: "Bold", aliases: ["b", "strong"], seed: "**bold text**",
        run: _wrap("**", "**"), xform: { t: "wrap", open: "**", close: "**" } },
      { label: "Italic", aliases: ["i", "em"], seed: "*italic*",
        run: _wrap("*", "*"), xform: { t: "wrap", open: "*", close: "*" } },
      { label: "Strikethrough", aliases: ["s", "strike", "del"],
        seed: "~~strikethrough~~", run: _wrap("~~", "~~"),
        xform: { t: "wrap", open: "~~", close: "~~" } },
      { label: "Inline code", aliases: ["code-inline"], seed: "`code`",
        run: _wrap("`", "`"), xform: { t: "wrap", open: "`", close: "`" } },
      { label: "Link", aliases: ["link", "url", "hyperlink"],
        seed: "[text](url)", run: _wrap("[", "](url)"), xform: { t: "link" } },
    ],
  };

  var _VIEWS = {
    q: "query",
    m: "metric",
    d: "dashboard",
    t: "threshold",
    b: "board",
    h: "habit",
    c: "calendar",
    u: "due",
    p: "project",
  };

  // Embed kinds whose window is driven by the `time` key. `due` ignores it
  // (its window comes from config) and `project` scans all time, so neither
  // gets a time step.
  var _TIME_CAPABLE = {
    query: 1, metric: 1, dashboard: 1, threshold: 1,
    board: 1, habit: 1, calendar: 1,
  };
  var _timeOptions = [];
  var _TIME_FALLBACK = [
    { label: "Today", value: "td" },
    { label: "This week", value: "tw" },
    { label: "This month", value: "tm" },
    { label: "Last month", value: "lm" },
    { label: "This year", value: "ty" },
    { label: "All time", value: "all" },
  ];

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

  // The ```ptos body for an embed pick (name + explicit view + optional
  // time). Shared by the "/" insert path and the Blocks-mode picker.
  function _embedSource(item, time) {
    var src = 'name = "' + item.name + '"';
    if (item.view) src += "\n" + 'view = "' + item.view + '"';
    if (time) src += "\n" + 'time = "' + time + '"';
    return src;
  }

  // Menu markup for the embed groups filtered by `q` ("" = everything).
  // Returns {html, flat} or null when nothing matches.
  function _buildMenu(q) {
    var groups = [_FORMAT_GROUP];
    if (_groups !== null) groups = groups.concat(_groups);
    var matched = _filter(groups, q);
    if (!matched.length) return null;
    var flat = [];
    var html = "";
    matched.forEach(function (g) {
      html += '<div class="slash-ac-group">' + g.label + "</div>";
      g.items.forEach(function (it) {
        html += '<div class="bracket-ac-item slash-ac-item" data-idx="' +
          flat.length + '">' + _label(it) + "</div>";
        flat.push(it.run ? it : { name: it, view: _VIEWS[g.kind] });
      });
    });
    if (_groups === null && _fetching) {
      html += '<div class="slash-ac-empty">Loading queries…</div>';
    }
    return { html: html, flat: flat };
  }

  // Markup for the time-window step of one pending item.
  function _buildTimeStep(item) {
    var opts = [{ label: "Default (as configured)", value: "" }].concat(_timeOptions);
    var flat = [];
    var html = '<div class="slash-ac-group">Time window — ' + item.name + "</div>";
    opts.forEach(function (o) {
      html += '<div class="bracket-ac-item slash-ac-item" data-idx="' +
        flat.length + '">' + o.label + "</div>";
      flat.push({ _time: o.value, label: o.label });
    });
    html += '<div class="slash-ac-empty">Esc cancels · Enter confirms</div>';
    return { html: html, flat: flat };
  }

  function _activateIn(list, i) {
    list.querySelectorAll(".slash-ac-item").forEach(function (itemEl, j) {
      itemEl.classList.toggle("active", j === i);
    });
  }

  function _wireItems(list, commitFn) {
    list.querySelectorAll(".slash-ac-item").forEach(function (itemEl) {
      itemEl.addEventListener("mousedown", function (e) {
        e.preventDefault();
        commitFn(parseInt(itemEl.dataset.idx, 10));
      });
    });
  }

  function _render(el, tok, list) {
    if (list._blurTimer) { clearTimeout(list._blurTimer); list._blurTimer = null; }
    list._mode = "embed";
    var built = _buildMenu(tok.query);
    if (!built) { _close(list); return; }
    list.innerHTML = built.html;
    list._flat = built.flat;
    list._tok = tok;
    list.style.display = "block";
    list.classList.add("open");
    _position(list, el);
    list._activate = _activateIn.bind(null, list);
    _wireItems(list, function (idx) { _commit(el, list, idx); });
  }

  function _commit(el, list, idx) {
    var it = list._flat[idx];
    if (!it) return;
    if (it.run) { it.run(el, list._tok, list); return; }
    if (list._mode === "time") {
      var item = list._pendingItem;
      _insert(el, list._tok, item, list, it._time);
      return;
    }
    if (_TIME_CAPABLE[it.view]) { _openTimeStep(el, it, list); return; }
    _insert(el, list._tok, it, list);
  }

  function _openTimeStep(el, item, list) {
    list._pendingItem = item;
    list._mode = "time";
    var built = _buildTimeStep(item);
    list.innerHTML = built.html;
    list._flat = built.flat;
    list.style.display = "block";
    list.classList.add("open");
    _position(list, el);
    list._activate(-1);
    _wireItems(list, function (idx) { _commit(el, list, idx); });
  }

  function _insert(el, tok, item, list, time) {
    var before = el.value.slice(0, tok.start);
    var after = el.value.slice(tok.end);
    var lead = (before && !/\n$/.test(before)) ? "\n" : "";
    var fence = '```ptos\n' + _embedSource(item, time) + "\n```\n";
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
        _timeOptions = (d && d.ok && d.time_options) ? d.time_options : _TIME_FALLBACK.slice();
        _fetching = false;
        _pending.splice(0).forEach(function (f) { f(); });
      })
      .catch(function () {
        _groups = [];
        _timeOptions = _TIME_FALLBACK.slice();
        _fetching = false;
        _pending.splice(0).forEach(function (f) { f(); });
      });
  }

  // ── Programmatic picker (Blocks mode) ────────────────────────────────
  // openSlashPicker(anchorEl, onPick) shows the same menu the "/" path uses
  // but anchored to an element rather than a caret, and hands the choice to
  // onPick: {kind:"md", seed} for a Format helper, {kind:"widget", source}
  // for an embed (after the time-window step when the kind honours time).

  var _picker = null;

  function _positionAnchor(list, anchor) {
    var rect = anchor.getBoundingClientRect();
    var top = rect.bottom + 6;
    if (top > window.innerHeight - 220) top = Math.max(rect.top - 6, 8);
    list.style.left = Math.min(rect.left, window.innerWidth - 340) + "px";
    list.style.top = top + "px";
  }

  function _closePicker() {
    if (!_picker) return;
    if (_picker.onKey) document.removeEventListener("keydown", _picker.onKey, true);
    if (_picker.onDown) document.removeEventListener("mousedown", _picker.onDown, true);
    _close(_picker.list);
    _picker = null;
  }

  function _renderPicker() {
    var built = _buildMenu("");
    if (!built) return false;
    var list = _picker.list;
    list._mode = "embed";
    list.innerHTML = built.html;
    list._flat = built.flat;
    list.style.display = "block";
    list.classList.add("open");
    _positionAnchor(list, _picker.anchor);
    _activateIn(list, -1);
    _wireItems(list, _commitPick);
    return true;
  }

  function _openTimeStepPick(list, item) {
    list._pendingItem = item;
    list._mode = "time";
    var built = _buildTimeStep(item);
    list.innerHTML = built.html;
    list._flat = built.flat;
    list.style.display = "block";
    list.classList.add("open");
    _activateIn(list, -1);
    _wireItems(list, _commitPick);
  }

  function _commitPick(idx) {
    if (!_picker) return;
    var list = _picker.list;
    var onPick = _picker.onPick;
    var it = list._flat[idx];
    if (!it) return;
    if (it.run) {
      _closePicker();
      if (onPick) onPick({
        kind: "md",
        seed: it.seed != null ? it.seed : "",
        xform: it.xform || null
      });
      return;
    }
    if (list._mode === "time") {
      var pending = list._pendingItem;
      _closePicker();
      if (onPick) onPick({ kind: "widget", source: _embedSource(pending, it._time) });
      return;
    }
    if (_TIME_CAPABLE[it.view]) { _openTimeStepPick(list, it); return; }
    _closePicker();
    if (onPick) onPick({ kind: "widget", source: _embedSource(it, "") });
  }

  window.openSlashPicker = function (anchor, onPick) {
    if (!anchor) return;
    _closePicker();
    var list = document.getElementById("slash-picker-ac");
    if (!list) {
      list = document.createElement("div");
      list.id = "slash-picker-ac";
      list.className = "slash-ac-list";
      document.body.appendChild(list);
    }
    _picker = { anchor: anchor, list: list, onPick: onPick };
    _load(function () {
      if (!_picker || _picker.list !== list) return;
      if (!_renderPicker()) { _picker = null; return; }
      _picker.onKey = function (e) {
        if (!_picker || !_picker.list.classList.contains("open")) { _closePicker(); return; }
        var flat = list._flat || [];
        var active = list.querySelector(".slash-ac-item.active");
        var cur = active ? parseInt(active.dataset.idx, 10) : -1;
        if (e.key === "ArrowDown") {
          e.preventDefault();
          if (cur === -1) cur = 0;
          _activateIn(list, Math.min(cur + 1, flat.length - 1));
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          if (cur === -1) cur = 0;
          _activateIn(list, Math.max(cur - 1, 0));
        } else if (e.key === "Enter" || e.key === "Tab" || e.key === " ") {
          // Swallow these while the menu owns the keyboard: the anchor is
          // often a focused <button>, so an unhandled Enter/Space would
          // immediately re-open the menu it just committed into.
          e.preventDefault();
          if (cur !== -1 && e.key !== " ") _commitPick(cur);
        } else if (e.key === "Escape") {
          e.preventDefault();
          _closePicker();
        }
      };
      _picker.onDown = function (e) {
        if (!_picker) return;
        if (list.contains(e.target) || _picker.anchor.contains(e.target)) return;
        _closePicker();
      };
      document.addEventListener("keydown", _picker.onKey, true);
      document.addEventListener("mousedown", _picker.onDown, true);
      try { _picker.anchor.focus(); } catch (err) {}
    });
  };

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
      list._blurTimer = setTimeout(function () {
        list._blurTimer = null;
        if (document.activeElement === el) return;
        _close(list);
      }, 150);
    });

    el.addEventListener("scroll", function () {
      if (list.classList.contains("open")) _position(list, el);
    });
  };

  // Toolbar "Insert view" button: drop a "/" at the caret and let the
  // attached slash menu take over (candidates, filtering, insertion). A
  // safe anchor is guaranteed — the menu only opens when "/" is at the
  // line start or after whitespace.
  window.openSlashMenu = function (el) {
    if (!el) return;
    if (el.offsetParent === null && typeof window.setMode === "function") {
      window.setMode("edit");
    }
    el.focus();
    var pos = el.selectionStart;
    var val = el.value;
    var before = val.slice(0, pos);
    var prefix = (pos === 0 || /\s$/.test(before)) ? "" : "\n";
    el.value = before + prefix + "/" + val.slice(pos);
    var caret = pos + prefix.length + 1;
    el.setSelectionRange(caret, caret);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  };
})();