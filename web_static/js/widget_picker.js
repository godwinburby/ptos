// widget_picker.js — the widget gallery (spec Part C1) for the editor.
//
// window.PtosWidgetPicker.open({mode, spec, anchor, onPick(body),
// onFormat()}) shows a bottom sheet on phones and a popover on desktop:
// Starters first (ready-made bodies from the catalog), then the six
// categories, then Recent picks (localStorage, try/catch, capped at 8).
// Search filters starters, kinds and aliases live. A named kind opens a
// second step listing its saved items (GET /api/widgets/options
// ?source=saved.<kind>) before onPick fires with the final body —
// `view = "kind"` plus `name = "item"` (or just the view for
// threshold/todo, which render fine nameless). mode:"change" merges the
// pick with the current spec via merge(): keys the target kind does not
// allow are dropped, everything else carries over, and the picked body
// wins on conflicts. The **Text** category reads window.PtosTextBlocks,
// the same definitions used to build the slash menu's Format group.
// Picking a card hands {kind:"md", seed, caret, xform} straight to
// onPick (no TOML merge, never pushed to Recent — a markdown seed is
// not a widget body). Change mode keeps its "Markdown & text…" card
// handing back to onFormat instead, so widget⇄ text conversion stays
// on the slash Format picker. Requires slash_embed.js to have loaded
// by render time (it loads after this file — the export is read
// lazily, never at module load).
// Loaded after widget_form.js (which it uses for PtosToml.serialize via
// merge); requires widget_toml.js.
(function () {
  var _RECENT_KEY = "ptos.widgetRecent";
  var _MAX_RECENT = 8;
  var _MAX_ITEMS = 300;

  var _cat = null;
  var _fetching = false;
  var _pending = [];
  var _overlay = null;
  var _S = null;

  var _ALIASES = {
    todo: "tasks task list checklist",
    query: "table chart graph",
    records: "table log entries",
    metric: "number stat kpi",
    dashboard: "stats overview numbers",
    threshold: "budget target limit",
    board: "kanban columns",
    habit: "streak heatmap tracker",
    calendar: "month schedule",
    due: "overdue deadlines",
    project: "projects folder",
    todo_summary: "counts summary",
    journal: "diary entries",
    capture: "inbox quick note",
    quick_add: "presets templates",
    quick_add_multi: "presets multi",
  };

  // Tiny inline SVGs (stroke, currentColor) keyed by the catalog icon.
  var _ICONS = {
    "layout": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "hash": '<path d="M9 3 7 21M17 3l-2 18M4 8h16M4 16h16"/>',
    "gauge": '<path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l4-6"/>',
    "columns": '<rect x="3" y="4" width="5" height="16" rx="1"/><rect x="10" y="4" width="5" height="16" rx="1"/><rect x="17" y="4" width="4" height="16" rx="1"/>',
    "calendar-check": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 10h18M9 15l2 2 4-4"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 10h18"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "check-square": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 12l3 3 6-6"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    "table": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M9 4v16M15 4v16"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "book": '<path d="M4 5a2 2 0 0 1 2-2h14v18H6a2 2 0 0 0-2 2z"/><path d="M4 19a2 2 0 0 1 2-2h14"/>',
    "inbox": '<path d="M3 13h5l2 3h4l2-3h5"/><path d="M5 5h14l2 8v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5z"/>',
    "zap": '<path d="M13 2 4 14h6l-1 8 9-12h-6z"/>',
    "layers": '<path d="M12 3 3 8l9 5 9-5z"/><path d="M3 13l9 5 9-5"/>',
    "heading": '<path d="M6 4v16M18 4v16M6 12h12"/>',
    "pilcrow": '<path d="M14 4h-4a4 4 0 0 0 0 8h4"/><path d="M14 4v16"/>',
    "list-ordered": '<path d="M10 6h11M10 12h11M10 18h11"/><path d="M4 6h1v4M4 10h2M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"/>',
    "code": '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "quote": '<path d="M10 11H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v6a4 4 0 0 1-4 4"/><path d="M20 11h-4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v6a4 4 0 0 1-4 4"/>',
    "minus": '<path d="M5 12h14"/>',
    "message-square": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  };

  function _esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function _iconHtml(name) {
    var body = _ICONS[name] || _ICONS["layers"];
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ' +
      'aria-hidden="true">' + body + "</svg>";
  }

  function _load(cb) {
    if (_cat !== null) { cb(); return; }
    _pending.push(cb);
    if (_fetching) return;
    _fetching = true;
    fetch("/api/widgets/catalog")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        _cat = (d && d.ok)
          ? { kinds: d.kinds || [], starters: d.starters || [],
              categories: d.categories || [] }
          : { kinds: [], starters: [], categories: [] };
        _flush();
      })
      .catch(function () {
        _cat = { kinds: [], starters: [], categories: [] };
        _flush();
      });
  }

  function _flush() {
    _fetching = false;
    _pending.splice(0).forEach(function (f) { f(); });
  }

  function _recent() {
    try {
      var v = JSON.parse(localStorage.getItem(_RECENT_KEY));
      return Array.isArray(v) ? v : [];
    } catch (e) { return []; }
  }

  function _pushRecent(label, body) {
    try {
      var list = _recent().filter(function (r) { return r.body !== body; });
      list.unshift({ label: label, body: body });
      localStorage.setItem(_RECENT_KEY,
        JSON.stringify(list.slice(0, _MAX_RECENT)));
    } catch (e) {}
  }

  // ── change-mode merge ────────────────────────────────────────────────
  // Keep current keys the target kind allows, drop the rest, then overlay
  // the picked body (its view/name/time win). Needs the catalog for the
  // target's field list — when it is not loaded yet (rare: slash-menu
  // pick before any gallery use) return the pick unchanged.

  function merge(currentSpec, newBody) {
    if (typeof PtosToml === "undefined") return newBody;
    var nb;
    try { nb = PtosToml.parse(newBody || "") || {}; }
    catch (e) { return newBody; }
    var view = String(nb.view || "").toLowerCase().trim();
    var entry = null;
    ((_cat && _cat.kinds) || []).forEach(function (k) {
      if (k.kind === view) entry = k;
    });
    if (!entry || !currentSpec) return newBody;
    var allowed = {};
    (entry.fields || []).forEach(function (f) { allowed[f.key] = 1; });
    var out = {};
    Object.keys(currentSpec).forEach(function (k) {
      if (allowed[k]) out[k] = currentSpec[k];
    });
    Object.keys(nb).forEach(function (k) { out[k] = nb[k]; });
    try { return PtosToml.serialize(out); } catch (e) { return newBody; }
  }

  // ── open / close ─────────────────────────────────────────────────────

  function open(opts) {
    close();
    opts = opts || {};
    _S = {
      mode: opts.mode === "change" ? "change" : "add",
      spec: opts.spec || null,
      onPick: opts.onPick || null,
      onFormat: opts.onFormat || null,
      anchor: opts.anchor || null,
      step: "home",
      cat: null,
      kind: null,
      query: "",
      items: null,
      loading: true,
      itemsLoading: false,
    };
    _buildOverlay();
    _load(function () {
      if (!_S) return;
      _S.loading = false;
      _render();
    });
  }

  function close() {
    if (!_overlay) { _S = null; return; }
    var s = _S;
    if (_overlay.parentNode) _overlay.parentNode.removeChild(_overlay);
    _overlay = null;
    _S = null;
    if (s && s.anchor) { try { s.anchor.focus(); } catch (e) {} }
    if (s && s.onClose) { try { s.onClose(); } catch (e) {} }
  }

  function _buildOverlay() {
    var ov = document.createElement("div");
    ov.className = "wp-overlay";
    ov.innerHTML =
      '<div class="wp-sheet" role="dialog" aria-modal="true" ' +
        'aria-label="Widget gallery">' +
        '<div class="wp-head">' +
          '<button type="button" class="wp-back" aria-label="Back" ' +
            'style="display:none">←</button>' +
          '<span class="wp-title">Add a widget</span>' +
          '<button type="button" class="wp-close" aria-label="Close">✕</button>' +
        "</div>" +
        '<input class="wp-search" type="search" ' +
          'placeholder="Search…" autocomplete="off">' +
        '<div class="wp-body"></div>' +
      "</div>";
    document.body.appendChild(ov);
    _overlay = ov;

    ov.querySelector(".wp-close").addEventListener("click", close);
    var back = ov.querySelector(".wp-back");
    back.addEventListener("click", function () {
      if (!_S) return;
      if (_S.step === "kind" || _S.step === "items") {
        _S.step = _S.kind ? "cat" : "home";
        _S.kind = null;
        _S.items = null;
      } else {
        _S.step = "home";
        _S.cat = null;
      }
      _render();
    });
    var search = ov.querySelector(".wp-search");
    search.addEventListener("input", function () {
      if (!_S) return;
      _S.query = search.value;
      _render();
    });
    ov.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.preventDefault(); close(); }
    });
    ov.addEventListener("mousedown", function (e) {
      if (e.target === ov) close();
    });
    if (!window.matchMedia("(max-width: 767px)").matches) {
      try { search.focus(); } catch (e) {}
    }
  }

  // ── render ───────────────────────────────────────────────────────────

  function _render() {
    if (!_S || !_overlay) return;
    var body = _overlay.querySelector(".wp-body");
    var back = _overlay.querySelector(".wp-back");
    var title = _overlay.querySelector(".wp-title");
    var search = _overlay.querySelector(".wp-search");
    if (!body) return;

    back.style.display = _S.step === "home" ? "none" : "";
    search.style.display = _S.step === "items" ? "none" : "";
    title.textContent = _S.mode === "change" ? "Change widget"
      : _S.step === "home" ? "Add a widget"
      : _S.step === "cat" ? _catLabel(_S.cat)
      : _S.kind ? _kindLabel(_S.kind) : "Add a widget";

    if (_S.loading) {
      body.innerHTML = '<div class="wp-empty">Loading…</div>';
      return;
    }
    if (_S.step === "items") { _renderItems(body); return; }
    if (_S.step === "cat") { _renderCat(body); return; }
    _renderHome(body);
  }

  function _catLabel(id) {
    if (id === "text") return "Text";
    var hit = "Browse";
    ((_cat && _cat.categories) || []).forEach(function (c) {
      if (c.id === id) hit = c.label || c.id;
    });
    return hit;
  }

  function _kindLabel(kind) {
    var hit = kind;
    ((_cat && _cat.kinds) || []).forEach(function (k) {
      if (k.kind === kind) hit = k.label || k.kind;
    });
    return hit;
  }

  function _card(attr, val, icon, label, desc) {
    return '<button type="button" class="wp-card" data-' + attr + '="' +
      _esc(val) + '">' +
      '<span class="wp-card-ico">' + _iconHtml(icon) + "</span>" +
      '<span class="wp-card-txt">' +
        '<span class="wp-card-label">' + _esc(label) + "</span>" +
        (desc ? '<span class="wp-card-desc">' + _esc(desc) + "</span>" : "") +
      "</span></button>";
  }

  function _hay(o) {
    return ((o.label || "") + " " + (o.description || "") + " " +
            (o.kind || "") + " " + (_ALIASES[o.kind] || "")).toLowerCase();
  }

  function _renderHome(body) {
    var q = (_S.query || "").toLowerCase().trim();
    var html = "";
    if (_S.mode === "change" && _S.onFormat) {
      html += '<div class="wp-sec-label">Convert</div><div class="wp-grid">' +
        '<button type="button" class="wp-card" data-format="1">' +
          '<span class="wp-card-ico">' + _iconHtml("book") + "</span>" +
          '<span class="wp-card-txt"><span class="wp-card-label">' +
            "Markdown &amp; text…</span>" +
            '<span class="wp-card-desc">Headings, lists, tables, styling.' +
            "</span></span></button></div>";
    }
    var starters = (_cat && _cat.starters || []).filter(function (s) {
      return !q || _hay(s).indexOf(q) !== -1;
    });
    var kinds = (_cat && _cat.kinds || []).filter(function (k) {
      return !q || _hay(k).indexOf(q) !== -1;
    });
    var texts = _S.mode === "add"
      ? _textItems().filter(function (t) {
          return !q || _textHay(t).indexOf(q) !== -1;
        })
      : [];
    if (q) {
      html += '<div class="wp-sec-label">Matching</div>';
      html += '<div class="wp-grid">';
      starters.forEach(function (s) {
        html += _card("starter", s.id, _kindIcon(s.kind), s.label, s.description);
      });
      kinds.forEach(function (k) {
        html += _card("kind", k.kind, k.icon, k.label, k.description);
      });
      texts.forEach(function (t) { html += _textCard(t); });
      html += "</div>";
      if (!starters.length && !kinds.length && !texts.length) {
        html += '<div class="wp-empty">Nothing matches “' +
          _esc(_S.query) + "”.</div>";
      }
    } else {
      if (starters.length) {
        html += '<div class="wp-sec-label">Starters</div><div class="wp-grid">';
        starters.forEach(function (s) {
          html += _card("starter", s.id, _kindIcon(s.kind), s.label,
                        s.description);
        });
        html += "</div>";
      }
      var showText = _S.mode === "add" && _textItems().length > 0;
      if (showText || (_cat && _cat.categories || []).length) {
        html += '<div class="wp-sec-label">Categories</div><div class="wp-grid">';
        if (showText) {
          html += _card("cat", "text", "pilcrow", "Text",
                        "Headings, lists, quotes, tables");
        }
        (_cat.categories).forEach(function (c) {
          html += _card("cat", c.id, _catIcon(c.id), c.label, "");
        });
        html += "</div>";
      }
      var rec = _recent();
      if (rec.length) {
        html += '<div class="wp-sec-label">Recent</div><div class="wp-grid">';
        rec.forEach(function (r, i) {
          html += _card("recent", i, "layers", r.label, "");
        });
        html += "</div>";
      }
    }
    body.innerHTML = html;
    _wire(body);
  }

  function _kindIcon(kind) {
    var hit = "layers";
    ((_cat && _cat.kinds) || []).forEach(function (k) {
      if (k.kind === kind && k.icon) hit = k.icon;
    });
    return hit;
  }

  function _catIcon(id) {
    return ({
      text: "pilcrow",
      tasks: "check-square", tables: "table", numbers: "hash",
      goals: "gauge", capture: "inbox", projects: "folder",
    })[id] || "layers";
  }

  // ── Text category (reads the slash Format group — one definition) ──

  function _textItems() {
    var items = window.PtosTextBlocks;
    if (!Array.isArray(items)) return [];
    return items.filter(function (it) { return it && it.gallery; });
  }

  function _textHay(t) {
    return ((t.label || "") + " " + (t.description || "") + " " +
            (t.aliases || []).join(" ")).toLowerCase();
  }

  function _textCard(t) {
    return _card("text", _textItems().indexOf(t), t.icon || "pilcrow",
                 t.label, t.description);
  }

  function _kindsIn(catId) {
    return ((_cat && _cat.kinds) || []).filter(function (k) {
      return k.category === catId;
    });
  }

  function _renderCat(body) {
    var q = (_S.query || "").toLowerCase().trim();
    var html;
    if (_S.cat === "text") {
      var texts = _textItems().filter(function (t) {
        return !q || _textHay(t).indexOf(q) !== -1;
      });
      html = '<div class="wp-grid">';
      texts.forEach(function (t) { html += _textCard(t); });
      html += "</div>";
      if (!texts.length) {
        html = '<div class="wp-empty">Nothing matches “' +
          _esc(_S.query) + "”.</div>" + html;
      }
      body.innerHTML = html;
      _wire(body);
      return;
    }
    var kinds = _kindsIn(_S.cat);
    if (q) kinds = kinds.filter(function (k) { return _hay(k).indexOf(q) !== -1; });
    html = '<div class="wp-grid">';
    kinds.forEach(function (k) {
      html += _card("kind", k.kind, k.icon, k.label, k.description);
    });
    html += "</div>";
    if (!kinds.length) html = '<div class="wp-empty">No widgets here.</div>' + html;
    body.innerHTML = html;
    _wire(body);
  }

  function _renderItems(body) {
    if (_S.itemsLoading || _S.items === null) {
      body.innerHTML = '<div class="wp-empty">Loading…</div>';
      return;
    }
    var q = (_S.query || "").toLowerCase().trim();
    var items = _S.items.filter(function (n) {
      return !q || String(n).toLowerCase().indexOf(q) !== -1;
    });
    var html = "";
    var entry = null;
    ((_cat && _cat.kinds) || []).forEach(function (k) {
      if (k.kind === _S.kind) entry = k;
    });
    if (entry && entry.needs_name === false) {
      html += '<button type="button" class="wp-item" data-name="">' +
        (_S.kind === "threshold" ? "All thresholds"
         : _S.kind === "todo" ? "Default task list"
         : "Default") + "</button>";
    }
    items.slice(0, _MAX_ITEMS).forEach(function (n) {
      html += '<button type="button" class="wp-item" data-name="' +
        _esc(n) + '">' + _esc(n) + "</button>";
    });
    if (!items.length && !(entry && entry.needs_name === false)) {
      html = '<div class="wp-empty">No saved ' + _esc(_kindLabel(_S.kind)) +
        " items yet — create one in the Query Builder.</div>" + html;
    }
    body.innerHTML = html;
    _wire(body);
  }

  function _wire(body) {
    body.querySelectorAll(".wp-card").forEach(function (el) {
      el.addEventListener("click", function () {
        if (!_S) return;
        if (el.dataset.format != null) {
          var cb = _S.onFormat;
          close();
          if (cb) cb();
          return;
        }
        if (el.dataset.cat != null) {
          _S.cat = el.dataset.cat;
          _S.step = "cat";
          _render();
          return;
        }
        if (el.dataset.kind != null) { _pickKind(el.dataset.kind); return; }
        if (el.dataset.text != null) {
          _pickText(parseInt(el.dataset.text, 10));
          return;
        }
        if (el.dataset.starter != null) { _pickStarter(el.dataset.starter); return; }
        if (el.dataset.recent != null) { _pickRecent(parseInt(el.dataset.recent, 10)); }
      });
    });
    body.querySelectorAll(".wp-item").forEach(function (el) {
      el.addEventListener("click", function () {
        if (!_S || _S.step !== "items") return;
        _finish(_kindSource(_S.kind, el.dataset.name), _kindLabel(_S.kind));
      });
    });
  }

  // ── picks ────────────────────────────────────────────────────────────

  function _pickKind(kind) {
    if (!_S) return;
    var entry = null;
    ((_cat && _cat.kinds) || []).forEach(function (k) {
      if (k.kind === kind) entry = k;
    });
    if (!entry) return;
    if (!entry.named) { _finish(_kindSource(kind, ""), entry.label || kind); return; }
    _S.kind = kind;
    _S.step = "items";
    _S.items = null;
    _S.itemsLoading = true;
    _render();
    fetch("/api/widgets/options?source=" +
         encodeURIComponent("saved." + kind))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!_S || _S.kind !== kind || _S.step !== "items") return;
        _S.itemsLoading = false;
        _S.items = (d && d.ok && Array.isArray(d.values)) ? d.values : [];
        _render();
      })
      .catch(function () {
        if (!_S || _S.kind !== kind || _S.step !== "items") return;
        _S.itemsLoading = false;
        _S.items = [];
        _render();
      });
  }

  // A Text-category pick: markdown, not a widget body — so it skips the
  // TOML merge (change mode never shows this category anyway) and never
  // enters Recent, which would feed a seed back as a widget body.
  function _pickText(i) {
    if (!_S) return;
    var t = _textItems()[i];
    if (!t) return;
    var cb = _S.onPick;
    close();
    if (cb) cb({
      kind: "md",
      seed: t.seed != null ? t.seed : "",
      caret: Number(t.caret) || 0,
      xform: t.xform || null,
      label: t.label,
    });
  }

  function _pickStarter(id) {
    if (!_S) return;
    var st = null;
    ((_cat && _cat.starters) || []).forEach(function (s) {
      if (s.id === id) st = s;
    });
    if (!st) return;
    _finish(st.body, st.label || st.id);
  }

  function _pickRecent(i) {
    if (!_S) return;
    var r = _recent()[i];
    if (!r) return;
    _finish(r.body, r.label || "Recent");
  }

  function _kindSource(kind, name) {
    var src = 'view = "' + kind + '"';
    if (name) src += '\nname = "' + String(name).replace(/\\/g, "\\\\")
      .replace(/"/g, '\\"') + '"';
    return src;
  }

  function _finish(body, label) {
    if (!_S) return;
    if (_S.mode === "change") body = merge(_S.spec, body);
    _pushRecent(label || "Widget", body);
    var cb = _S.onPick;
    close();
    if (cb) cb(body);
  }

  window.PtosWidgetPicker = { open: open, close: close, merge: merge };
})();
