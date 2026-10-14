// md_blocks.js — Blocks mode for the shared note/journal markdown editor.
//
// Blocks mode is the editable twin of Preview: the same document rendered as
// a vertical list of top-level blocks (one markdown element or one ```ptos
// widget each), each with its own controls. The textarea stays the single
// source of truth — every action mutates the block array, re-serializes the
// whole document and writes it back through an "input" event, so autosave,
// dirty tracking and backlinks behave exactly like typing. Serialization is
// canonical (blocks joined by a blank line), which is the accepted trade-off
// for having no span math to keep in sync.
//
// Reuses three things so nothing drifts: embedRegions() (embeds.js) for
// cutting fences, embedFetch()/embedRenderBody() (embeds.js) for widget
// bodies, and openSlashPicker() (slash_embed.js) for both the "+" add flow
// and the "⇄" change flow. The preview is read-only, so this file owns
// every edit / move control.
//
// Exposes window.mdBlocks = {init, parse, serialize, enter, exit} plus
// window.blockParse / window.blockSerialize for tests.
(function () {
  var _eid = null;
  var _ta = null;
  var _pane = null;
  var _blocks = [];
  var _cards = [];
  var _active = false;
  var _syncing = false;

  // ── parse / serialize ────────────────────────────────────────────────

  function _norm(s) {
    return String(s == null ? "" : s)
      .replace(/\r\n|\n/g, "\n")
      .replace(/^\n+/, "")
      .replace(/\s+$/, "");
  }

  // Markdown blocks keep one trailing space when the block is only a starter
  // ("#", "-", ">", "1."), otherwise "_norm" would turn "# " into "#" and
  // typing a title would produce "#Title".
  function _normMd(s) {
    var out = _norm(s);
    if (/^(#{1,6}|>|1\.|-)$/.test(out)) return out + " ";
    return out;
  }

  // Split one markdown chunk into top-level blocks. marked.lexer gives each
  // top-level token's `raw`, so a list/table/fence stays one block. Space
  // tokens are separators and never become blocks.
  function _segments(text) {
    if (typeof marked === "undefined" || typeof marked.lexer !== "function") {
      return text ? [text] : [];
    }
    var tokens;
    try { tokens = marked.lexer(text); } catch (e) { return text ? [text] : []; }
    var out = [];
    tokens.forEach(function (t) {
      if (t.type === "space") return;
      var raw = t.raw == null ? "" : _normMd(String(t.raw));
      if (raw) out.push(raw);
    });
    return out;
  }

  function _pushMd(out, text) {
    var norm = _normMd(text);
    if (!norm) return;
    var pieces = [];
    _segments(norm).forEach(function (p) {
      p = _normMd(p);
      if (p) pieces.push(p);
    });
    // Safety net: segmentation must be a partition of the source (up to
    // whitespace). If the lexer ever returns something lossy, keep the whole
    // chunk as one block rather than silently dropping content.
    if (norm.replace(/\s+/g, "") !== pieces.join("").replace(/\s+/g, "")) {
      out.push({ kind: "md", source: norm });
      return;
    }
    pieces.forEach(function (p) { out.push({ kind: "md", source: p }); });
  }

  function parse(src) {
    src = String(src == null ? "" : src);
    var lines = src.split(/\r\n|\n/);
    var regions = (typeof embedRegions === "function") ? embedRegions(src) : [];
    var out = [];
    var cursor = 0;
    regions.forEach(function (r) {
      if (r.start > cursor) {
        _pushMd(out, lines.slice(cursor, r.start).join("\n"));
      }
      out.push({ kind: "widget", source: _norm(lines.slice(r.start + 1, r.end).join("\n")) });
      cursor = r.end + 1;
    });
    if (cursor < lines.length) {
      _pushMd(out, lines.slice(cursor).join("\n"));
    }
    return out;
  }

  function serialize(blocks) {
    var parts = [];
    (blocks || []).forEach(function (b) {
      var src = b.kind === "widget" ? _norm(b.source) : _normMd(b.source);
      if (!src) return;
      parts.push(b.kind === "widget" ? "```ptos\n" + src + "\n```" : src);
    });
    return parts.length ? parts.join("\n\n") + "\n" : "";
  }

  // ── state ────────────────────────────────────────────────────────────

  function _sync() {
    if (!_ta) return;
    _syncing = true;
    try {
      _ta.value = serialize(_blocks);
      _ta.dispatchEvent(new Event("input", { bubbles: true }));
    } finally {
      _syncing = false;
    }
  }

  function _onInput() {
    if (!_active || _syncing) return;
    _blocks = parse(_ta.value);
    render();
  }

  function init(eid) {
    _eid = eid;
    _ta = document.getElementById(_eid);
    _pane = document.getElementById("blocks-pane");
    if (_ta) _ta.addEventListener("input", _onInput);
  }

  function enter() {
    _active = true;
    if (!_ta) _ta = document.getElementById(_eid);
    if (!_pane) _pane = document.getElementById("blocks-pane");
    if (!_ta || !_pane) return;
    _blocks = parse(_ta.value);
    render();
  }

  function exit() { _active = false; }

  // ── rendering ────────────────────────────────────────────────────────

  function _esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function _mdHtml(src) {
    if (typeof marked !== "undefined") {
      var body = (typeof preprocessLinks === "function") ? preprocessLinks(src) : src;
      try { return marked.parse(body); } catch (e) {}
    }
    return "<pre style='white-space:pre-wrap'>" + _esc(src) + "</pre>";
  }

  function _btn(label, title, onClick) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "md-block-btn";
    b.textContent = label;
    b.title = title;
    b.addEventListener("click", function (e) { e.preventDefault(); onClick(); });
    return b;
  }

  function _paintWidget(body, source) {
    body.innerHTML = '<div class="md-embed-loading">Loading widget…</div>';
    if (typeof embedFetch !== "function") {
      body.innerHTML = '<div class="msg msg-error">embeds.js is not loaded</div>';
      return;
    }
    embedFetch(source, false).then(function (res) {
      if (!res.ok) {
        body.innerHTML = '<div class="msg msg-error">' + _esc(res.error) + "</div>";
        return;
      }
      var data = res.data || {};
      var link = data.link
        ? '<a class="md-embed-link" href="' + _esc(data.link) + '">Open →</a>'
        : "";
      body.innerHTML =
        '<div class="md-embed-head">' +
          '<span class="md-embed-title">' +
            _esc(data.title || data.name || "Widget") + "</span>" + link +
        "</div>" +
        '<div class="md-embed-body"></div>';
      var be = body.querySelector(".md-embed-body");
      if (be && typeof embedRenderBody === "function") embedRenderBody(be, data);
    });
  }

  function _toolbar(i) {
    var bar = document.createElement("span");
    bar.className = "md-block-actions";
    bar.appendChild(_btn("＋", "Add block after this one", function () {
      _pickerAt(bar, i + 1);
    }));
    bar.appendChild(_btn("✎", "Edit this block", function () { _edit(i); }));
    bar.appendChild(_btn("⇄", "Change this block's type or content",
      function () { _change(_blocks[i], bar); }));
    bar.appendChild(_btn("▲", "Move block up", function () { _move(i, -1); }));
    bar.appendChild(_btn("▼", "Move block down", function () { _move(i, 1); }));
    bar.appendChild(_btn("✕", "Delete block", function () { _remove(i); }));
    return bar;
  }

  function _card(blk, i) {
    var el = document.createElement("div");
    el.className = "md-block md-block-" + blk.kind;
    el.dataset.idx = String(i);
    el.draggable = true;

    var head = document.createElement("div");
    head.className = "md-block-head";
    var kind = document.createElement("span");
    kind.className = "md-block-kind";
    kind.textContent = blk.kind === "widget" ? "Widget" : "Text";
    head.appendChild(kind);
    head.appendChild(_toolbar(i));
    el.appendChild(head);

    var body = document.createElement("div");
    body.className = "md-block-body";
    el.appendChild(body);
    if (blk.kind === "widget") _paintWidget(body, blk.source);
    else body.innerHTML = _mdHtml(blk.source);

    _wireDrag(el);
    return el;
  }

  function render() {
    if (!_pane) return;
    _pane.innerHTML = "";
    _cards = [];
    _blocks.forEach(function (blk, i) {
      var el = _card(blk, i);
      _cards.push(el);
      _pane.appendChild(el);
    });
    var row = document.createElement("button");
    row.type = "button";
    row.className = "md-block-add-row";
    row.textContent = "＋ Add block";
    row.addEventListener("click", function () {
      _pickerAt(row, _blocks.length);
    });
    _pane.appendChild(row);
  }

  function _renderCard(i) {
    var old = _cards[i];
    if (!old || !old.parentNode) { render(); return; }
    var fresh = _card(_blocks[i], i);
    old.parentNode.replaceChild(fresh, old);
    _cards[i] = fresh;
  }

  // ── actions ──────────────────────────────────────────────────────────

  function _move(i, d) {
    var j = i + d;
    if (j < 0 || j >= _blocks.length) return;
    var tmp = _blocks[i];
    _blocks[i] = _blocks[j];
    _blocks[j] = tmp;
    _sync();
    render();
  }

  function _remove(i) {
    _blocks.splice(i, 1);
    _sync();
    render();
  }

  function _caretFor(seed) {
    if (seed.length === 0) return 0;
    var inline = [
      /\*\*([^*]+)\*\*/g, /\*([^*]+)\*/g, /~~([^~]+)~~/g,
      /`([^`]+)`/g, /\[([^\]]*)\]\([^)]*\)/g
    ];
    for (var k = 0; k < inline.length; k++) {
      inline[k].lastIndex = 0;
      var m = inline[k].exec(seed);
      if (m && m.index + m[0].length === seed.length) {
        return { start: m.index + 1, end: m.index + 1 + m[1].length };
      }
    }
    return seed.length;
  }

  function _insertBlock(picked, at) {
    var blk = picked && picked.kind === "widget"
      ? { kind: "widget", source: _norm(picked.source) }
      : { kind: "md", source: _normMd(picked && picked.seed) };
    _blocks.splice(at, 0, blk);
    _sync();
    render();
    if (blk.kind === "md" && blk.source) _edit(at, true);
  }

  function _pickerAt(anchor, at) {
    if (typeof openSlashPicker === "function") {
      openSlashPicker(anchor, function (picked) { _insertBlock(picked, at); });
      return;
    }
    // Picker unavailable — fall back to a blank text block so the button
    // still does something useful.
    _insertBlock({ kind: "md", seed: "" }, at);
  }

  // ── change a block's type / content via the same picker ──────────────
  // "⇄" re-opens the slash menu and applies the choice to this block
  // rather than adding a new one. A widget pick replaces the block; a
  // Format pick re-styles the block's existing text (see _convert), so
  // turning a paragraph into a heading or a bullet keeps the paragraph.

  // One leading markdown block marker per pass, so "# Title" and "1. item"
  // and "- [ ] task" all reduce to their plain text before re-styling.
  var _MD_MARKER =
    /^(#{1,6}\s+|>\s+|[-*+]\s\[[ xX]\]\s+|[-*+]\s+|\d+\.\s+)/;

  function _stripMdMarker(line) {
    var out = String(line == null ? "" : line);
    var guard = 0;
    while (_MD_MARKER.test(out) && guard < 12) { out = out.replace(_MD_MARKER, ""); guard++; }
    return out;
  }

  // Peel a covering inline wrapper so re-styling never stacks up marks.
  // "**Hello**" -> "Hello" (longest first, so "**" wins over "*"), then the
  // new marks wrap the bare text.
  var _WRAPS = [
    ["**", "**"], ["__", "__"], ["~~", "~~"], ["``", "``"],
    ["*", "*"], ["_", "_"], ["`", "`"]
  ];

  function _stripWrap(text) {
    var s = String(text == null ? "" : text);
    for (var k = 0; k < _WRAPS.length; k++) {
      var open = _WRAPS[k][0], close = _WRAPS[k][1];
      if (s.length > open.length + close.length &&
          s.indexOf(open) === 0 &&
          s.lastIndexOf(close) === s.length - close.length) {
        return s.slice(open.length, s.length - close.length);
      }
    }
    return s;
  }

  // Apply a Format choice to a block that may already hold text. Returns
  // {source, edit} — `edit` is true when the result is a fresh skeleton the
  // caller should open in the inline editor with the caret in place.
  function _convert(text, xform, seed) {
    var body = String(text == null ? "" : text).replace(/\r\n|\n/g, "\n").trim();
    if (!xform) return { source: _normMd(seed), edit: true };
    if (xform.t === "prefix") {
      if (!body) return { source: _normMd(seed), edit: true };
      var lines = body.split("\n");
      var out = [];
      lines.forEach(function (ln, i) {
        var plain = _stripMdMarker(ln);
        var prefixable = xform.first ? (i === 0) : (plain !== "");
        out.push(prefixable ? xform.pre + plain : plain);
      });
      return { source: _normMd(out.join("\n")), edit: false };
    }
    if (xform.t === "wrap") {
      if (!body) return { source: _normMd(seed), edit: true };
      return {
        source: _normMd(xform.open + _stripWrap(body) + xform.close),
        edit: false
      };
    }
    if (xform.t === "link") {
      if (!body) return { source: "[text](url)", edit: true };
      return { source: "[" + body.replace(/\n/g, " ") + "](url)", edit: false };
    }
    if (xform.t === "fence") {
      var lang = xform.lang || "text";
      if (!body) return { source: "```" + lang + "\n\n```", edit: true };
      return { source: "```" + lang + "\n" + body + "\n```", edit: false };
    }
    // "replace" (table, divider) — no sensible way to carry text over.
    return { source: _normMd(seed), edit: !body };
  }

  function _change(blk, anchor) {
    if (!blk || typeof openSlashPicker !== "function") return;
    openSlashPicker(anchor, function (picked) {
      // Re-resolve by identity: the block may have moved while the picker
      // was open, and a shifted index would restyle the wrong block.
      var i = _blocks.indexOf(blk);
      if (i === -1 || !picked) return;
      if (picked.kind === "widget") {
        _blocks[i] = { kind: "widget", source: _norm(picked.source) };
        _sync();
        _renderCard(i);
        return;
      }
      var conv = _convert(blk.kind === "widget" ? "" : blk.source,
                          picked.xform, picked.seed);
      _blocks[i] = { kind: "md", source: _normMd(conv.source) };
      _sync();
      render();
      if (conv.edit && _blocks[i].source) _edit(i, true);
    });
  }

  function _edit(i, focus) {
    var card = _cards[i];
    var blk = _blocks[i];
    if (!card || !blk) return;
    card.classList.add("md-block-editing");
    var body = card.querySelector(".md-block-body");
    if (!body) return;
    body.innerHTML = "";

    var box = document.createElement("textarea");
    box.className = "md-block-edit-box";
    box.setAttribute("spellcheck", "false");
    box.value = blk.source;
    body.appendChild(box);

    if (blk.kind === "widget") {
      var hint = document.createElement("div");
      hint.className = "md-embed-edit-hint";
      hint.textContent = "view · name · time · from_date · to_date · limit · title";
      body.appendChild(hint);
    }

    var actions = document.createElement("div");
    actions.className = "md-block-edit-actions";
    var save = document.createElement("button");
    save.type = "button";
    save.className = "md-embed-edit-save";
    save.textContent = "Save";
    var cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "md-embed-edit-cancel";
    cancel.textContent = "Cancel";
    actions.appendChild(save);
    actions.appendChild(cancel);
    body.appendChild(actions);

    save.addEventListener("click", function () { _applyEdit(i, box.value); });
    cancel.addEventListener("click", function () { _renderCard(i); });
    box.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.preventDefault(); _renderCard(i); }
      else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        _applyEdit(i, box.value);
      }
    });

    box.focus();
    var caret = focus ? _caretFor(blk.source) : blk.source.length;
    if (typeof caret === "object") box.setSelectionRange(caret.start, caret.end);
    else box.setSelectionRange(caret, caret);
  }

  function _applyEdit(i, text) {
    var blk = _blocks[i];
    var next = blk.kind === "widget" ? _norm(text) : _normMd(text);
    if (next === blk.source) { _renderCard(i); return; }
    blk.source = next;
    _sync();
    _renderCard(i);
  }

  // ── drag to reorder ──────────────────────────────────────────────────

  function _wireDrag(el) {
    el.addEventListener("dragstart", function (e) {
      if (e.target.closest && e.target.closest(
          ".md-block-btn,.md-block-edit-box,.md-block-edit-actions,.md-embed-link")) {
        e.preventDefault();
        return;
      }
      window._mdBlockDrag = el;
      el.classList.add("dragging");
      try { e.dataTransfer.effectAllowed = "move"; } catch (err) {}
    });
    el.addEventListener("dragend", function () {
      if (window._mdBlockDrag === el) window._mdBlockDrag = null;
      el.classList.remove("dragging");
    });
    el.addEventListener("dragenter", function () {
      if (!window._mdBlockDrag || window._mdBlockDrag === el) return;
      el.classList.add("drag-over");
    });
    el.addEventListener("dragleave", function () { el.classList.remove("drag-over"); });
    el.addEventListener("dragover", function (e) {
      if (window._mdBlockDrag && window._mdBlockDrag !== el) {
        e.preventDefault();
        try { e.dataTransfer.dropEffect = "move"; } catch (err) {}
      }
    });
    el.addEventListener("drop", function (e) {
      e.preventDefault();
      el.classList.remove("drag-over");
      var drag = window._mdBlockDrag;
      if (!drag || drag === el) return;
      window._mdBlockDrag = null;
      drag.classList.remove("dragging");
      var from = parseInt(drag.dataset.idx, 10);
      var to = parseInt(el.dataset.idx, 10);
      if (isNaN(from) || isNaN(to) || from === to) return;
      var moved = _blocks.splice(from, 1)[0];
      _blocks.splice(from < to ? to - 1 : to, 0, moved);
      _sync();
      render();
    });
  }

  window.blockParse = parse;
  window.blockSerialize = serialize;
  window.mdBlocks = {
    init: init,
    enter: enter,
    exit: exit,
    parse: parse,
    serialize: serialize,
    render: render
  };
})();
