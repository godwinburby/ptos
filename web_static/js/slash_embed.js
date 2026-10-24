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
  function _formatRun(item) {
    if (item.run === "prefix") return _prefix(item.prefix);
    if (item.run === "wrap") return _wrap(item.open, item.close);
    if (item.run === "link") return _wrap("[", "](url)");
    var caret = Math.max(0, Math.min(item.seed.length, item.caret || 0));
    return _block(item.seed + "\n", item.seed.slice(0, caret));
  }

  var _formatGroup = {
    kind: "f",
    label: "Format",
    items: (window.PtosTextBlocks || []).map(function (item) {
      return Object.assign({}, item, { run: _formatRun(item) });
    }),
  };

  // The gallery (widget_picker.js). Format stays first; this entry leads
  // the widget choices so the full catalog is one pick away without
  // losing the named-item quick lists below it.
  var _GALLERY_GROUP = {
    kind: "g",
    label: "Widgets",
    items: [
      { label: "All widgets…", _gallery: true,
        aliases: ["gallery", "widgets", "all widgets"] },
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
    v: "todo",
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
        var hay = (it && (it.run || it._gallery))
          ? (it.label + " " + (it.aliases || []).join(" "))
          : it;
        if (!q || hay.toLowerCase().indexOf(q) !== -1) items.push(it);
      });
      if (items.length) out.push({ kind: g.kind, label: g.label, items: items });
    });
    return out;
  }

  function _label(it) {
    return (it.run || it._gallery) ? it.label : it;
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
    var groups = [_formatGroup, _GALLERY_GROUP];
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
        flat.push(it.run || it._gallery
          ? it : { name: it, view: _VIEWS[g.kind] });
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
    var items = list.querySelectorAll(".slash-ac-item");
    items.forEach(function (itemEl, j) {
      itemEl.classList.toggle("active", j === i);
    });
    var active = i >= 0 ? items[i] : null;
    if (!active) return;
    var top = active.offsetTop;
    var bottom = top + active.offsetHeight;
    if (top < list.scrollTop) list.scrollTop = top;
    else if (bottom > list.scrollTop + list.clientHeight) {
      list.scrollTop = bottom - list.clientHeight;
    }
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
    list._mode = "nav";
    list._tok = tok;
    list._flat = [];
    list.style.display = "block";
    list.classList.add("open");
    _position(list, el);
    list._activate = _activateIn.bind(null, list);
    _wireItems(list, function (idx) { _commit(el, list, idx); });
    if (tok.query && !list._catalog) {
      window.PtosWidgetPicker.catalog(function (catalog) {
        if (!list.classList.contains("open") || list._tok.start !== tok.start ||
            list._tok.query !== tok.query) return;
        list._catalog = catalog;
        _render(el, list._tok, list);
      });
      list._navPath = [];
      list._flat = [{_gallerySearch: tok.query}];
      list.innerHTML = '<div class="slash-ac-group">Search</div>' +
        '<div class="bracket-ac-item slash-ac-item" data-idx="0">Search all for “' +
        _escape(tok.query) + '” in gallery…</div>';
      _wireItems(list, function (idx) { _commit(el, list, idx); });
      return;
    }
    if (!window.PtosWidgetPicker || !window.PtosWidgetPicker.catalog) {
      _close(list);
      return;
    }
    window.PtosWidgetPicker.catalog(function (catalog) {
      if (!list.classList.contains("open") || list._tok.start !== tok.start ||
          list._tok.query !== tok.query) return;
      list._catalog = catalog;
      var path = list._navPath || [];
      var flat = [];
      var html = "";
      if (tok.query) {
        var q = tok.query.toLowerCase();
        function matches(label, description) {
          return (String(label || "") + " " + String(description || ""))
            .toLowerCase().indexOf(q) !== -1;
        }
        html = '<div class="slash-ac-group">Matches for "' + _escape(tok.query) + '"</div>';
        if (!path.length) {
          (catalog.categories || []).forEach(function (c) {
            if (!matches(c.label, c.description)) return;
            html += _navRow(flat.length, c.label, c.count + " items", c.description || "Category");
            flat.push({_navCategory:c.id});
          });
          (catalog.kinds || []).forEach(function (kind) {
            if (!matches(kind.label, kind.description)) return;
            if (window.PtosWidgetPicker.allowsKind &&
                !window.PtosWidgetPicker.allowsKind(kind.kind)) return;
            html += _navRow(flat.length, kind.label, kind.named ? "Saved items" : "", kind.description);
            flat.push({_navKind:kind});
          });
          (window.PtosTextBlocks || []).filter(function (it) {
            return it && it.gallery && matches(it.label, it.description);
          }).forEach(function (item) {
            html += _navRow(flat.length, item.label, "Text", item.description);
            flat.push({_navText:item});
          });
        } else if (path[0] === "text") {
          (window.PtosTextBlocks || []).filter(function (it) {
            return it && it.gallery && matches(it.label, it.description);
          }).forEach(function (item) {
            html += _navRow(flat.length, item.label, "Text", item.description);
            flat.push({_navText:item});
          });
        } else if (path.length === 1) {
          (catalog.kinds || []).filter(function (kind) {
            return kind.category === path[0] && matches(kind.label, kind.description) &&
              (!window.PtosWidgetPicker.allowsKind ||
               window.PtosWidgetPicker.allowsKind(kind.kind));
          }).forEach(function (kind) {
            html += _navRow(flat.length, kind.label, kind.named ? "Saved items" : "", kind.description);
            flat.push({_navKind:kind});
          });
        } else if (list._navItems) {
          list._navItems.filter(function (item) {
            return matches(item.name, item.tag + " " + item.description);
          }).forEach(function (item) {
            html += _navRow(flat.length, item.name, item.tag || "", item.description);
            flat.push({_navItem:item, kind:path[1]});
          });
        }
        if (!flat.length) html += '<div class="slash-ac-empty">No matches here.</div>';
        flat.push({_gallerySearch:tok.query});
        html += '<div class="bracket-ac-item slash-ac-item slash-nav-row" data-idx="' +
          (flat.length - 1) + '">Search all for “' + _escape(tok.query) + '” in gallery…</div>';
      } else if (!path.length) {
        var categories = [{id:"text",label:"Text",count:(window.PtosTextBlocks || []).length}]
          .concat(catalog.categories || []);
        html = '<div class="slash-ac-group">Add to page</div>';
        categories.forEach(function (c) {
          html += _navRow(flat.length, c.label, c.count + " items", "");
          flat.push({_navCategory:c.id});
        });
        var recent = window.PtosWidgetPicker.recent
          ? window.PtosWidgetPicker.recent().slice(0, 3) : [];
        if (recent.length) html += '<div class="slash-ac-group">Recent</div>';
        recent.forEach(function (r) {
          html += _navRow(flat.length, r.label || "Recent widget", "", "");
          flat.push({_galleryRecent:r});
        });
      } else if (path[0] === "text") {
        html = '<div class="slash-ac-group">Add to page › Text</div>';
        (window.PtosTextBlocks || []).filter(function (it) { return it && it.gallery; })
          .forEach(function (item) {
            html += _navRow(flat.length, item.label, "", item.description);
            flat.push({_navText:item});
          });
      } else if (path.length === 1) {
        var category = null;
        (catalog.categories || []).forEach(function (c) {
          if (c.id === path[0]) category = c;
        });
        html = '<div class="slash-ac-group">Add to page › ' +
          _escape(category ? category.label : path[0]) + '</div>';
        (catalog.kinds || []).filter(function (k) {
          return k.category === path[0];
        }).forEach(function (kind) {
          if (window.PtosWidgetPicker.allowsKind &&
              !window.PtosWidgetPicker.allowsKind(kind.kind)) return;
          html += _navRow(flat.length, kind.label, kind.named ? "Saved items" : "",
                          kind.description);
          flat.push({_navKind:kind});
        });
      } else {
        var kindEntry = null;
        (catalog.kinds || []).forEach(function (k) {
          if (k.kind === path[1]) kindEntry = k;
        });
        html = '<div class="slash-ac-group">Add to page › ' +
          _escape(kindEntry ? kindEntry.label : path[1]) + '</div>';
        if (list._navLoading) {
          html += '<div class="slash-ac-empty">Loading saved items…</div>';
        } else if (list._navItems) {
          list._navItems.forEach(function (item) {
            html += _navRow(flat.length, item.name, item.tag || "", item.description);
            flat.push({_navItem:item, kind:path[1]});
          });
          if (!list._navItems.length) html += '<div class="slash-ac-empty">No saved items. Browse in gallery…</div>';
        }
      }
      if (path.length === 2 && !list._navItems && !list._navLoading) {
        list._navLoading = true;
        fetch("/api/widgets/options?detail=1&source=" +
          encodeURIComponent("saved." + path[1]))
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (list._navPath !== path) return;
            list._navLoading = false;
            list._navItems = d && d.ok && Array.isArray(d.items) ? d.items : [];
            _render(el, list._tok, list);
          }).catch(function () {
            if (list._navPath !== path) return;
            list._navLoading = false;
            list._navItems = [];
            _render(el, list._tok, list);
          });
      }
      list.innerHTML = html;
      list._flat = flat;
      list._activate(-1);
      _wireItems(list, function (idx) { _commit(el, list, idx); });
    });
  }

  function _navRow(index, label, meta, description) {
    return '<div class="bracket-ac-item slash-ac-item slash-nav-row" data-idx="' +
      index + '"><span class="slash-nav-main"><span>' + _escape(label) +
      '</span>' + (description ? '<small>' + _escape(description) + '</small>' : '') +
      '</span>' + (meta ? '<span class="slash-ac-count">' + _escape(meta) + '</span>' : '') +
      '</div>';
  }

  function _escape(text) {
    return String(text == null ? "" : text).replace(/&/g, "&amp;")
      .replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function _commit(el, list, idx) {
    var it = list._flat[idx];
    if (!it) return;
    if (it._navCategory) {
      list._navPath = [it._navCategory];
      list._navItems = null;
      list._navLoading = false;
      _render(el, list._tok, list);
      return;
    }
    if (it._navKind) {
      var kind = it._navKind;
      if (kind.named) {
        list._navPath = [kind.category, kind.kind];
        list._navItems = null;
        list._navLoading = false;
        _render(el, list._tok, list);
      } else {
        _openGallerySlash(el, list, null, "", _widgetBody(kind.kind), kind.label);
      }
      return;
    }
    if (it._navText) {
      _insertSlashText(el, list, it._navText);
      return;
    }
    if (it._navItem) {
      _openGallerySlash(el, list, null, "",
        _widgetBody(it.kind, it._navItem.name), it._navItem.name);
      return;
    }
    if (it._gallerySearch) {
      _openGallerySlash(el, list, null, it._gallerySearch);
      return;
    }
    if (it._galleryRecent) {
      _openGallerySlash(el, list, null, "", it._galleryRecent.body,
                        it._galleryRecent.label);
      return;
    }
    if (it._gallery) { _openGallerySlash(el, list); return; }
    if (it.run) { it.run(el, list._tok, list); return; }
    if (list._mode === "time") {
      var item = list._pendingItem;
      _insert(el, list._tok, item, list, it._time);
      return;
    }
    if (_TIME_CAPABLE[it.view]) { _openTimeStep(el, it, list); return; }
    _insert(el, list._tok, it, list);
  }

  function _widgetBody(kind, name) {
    var spec = {view:kind};
    if (name) spec.name = name;
    if (window.PtosToml && window.PtosToml.serialize) return window.PtosToml.serialize(spec);
    var escaped = String(name || "").replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    return 'view = "' + kind + '"' + (name ? '\nname = "' + escaped + '"' : "");
  }

  function _insertSlashText(el, list, item) {
    var tok = list._tok;
    var before = el.value.slice(0, tok.start);
    var after = el.value.slice(tok.end);
    var seed = item.seed == null ? "" : String(item.seed);
    var lead = (seed && before && !/\n$/.test(before)) ? "\n" : "";
    el.value = before + lead + seed + after;
    _finish(list, el, (before + lead).length + (Number(item.caret) || 0));
  }

  // Gallery from the "/" path: the typed token stays put until a pick
  // lands, then the fence replaces it exactly like a named-item insert.
  // A Text-category pick replaces the token with the markdown seed
  // instead (empty seed = just drop the token).
  function _openGallerySlash(el, list, category, query, startBody, startLabel) {
    if (!window.PtosWidgetPicker) return;
    window.PtosWidgetPicker.open({
      mode: "add",
      category: category || undefined,
      query: query || "",
      startBody: startBody,
      startLabel: startLabel,
      onPick: function (p) {
        var tok = list._tok;
        if (!tok) { _close(list); return; }
        var before = el.value.slice(0, tok.start);
        var after = el.value.slice(tok.end);
        if (p && typeof p !== "string" && p.kind === "md") {
          var seed = p.seed != null ? p.seed : "";
          if (!seed) {
            el.value = before + after;
            _finish(list, el, before.length);
            return;
          }
          var slead = (before && !/\n$/.test(before)) ? "\n" : "";
          el.value = before + slead + seed + after;
          var caret = Number.isFinite(Number(p.caret))
            ? Number(p.caret) : seed.length;
          _finish(list, el, (before + slead).length + caret);
          return;
        }
        var source = typeof p === "string" ? p : (p && p.source) || "";
        var lead = (before && !/\n$/.test(before)) ? "\n" : "";
        var fence = "```ptos\n" + source + "\n```\n";
        el.value = before + lead + fence + after;
        _finish(list, el, (before + lead + fence).length);
      }
    });
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
    if (it._gallery) {
      window.PtosWidgetPicker.open({
        mode: "add",
        onPick: function (p) {
          _closePicker();
          if (!onPick) return;
          onPick(typeof p === "string" ? { kind: "widget", source: p }
            : p && p.kind === "md" ? p : { kind: "widget", source: p.source });
        }
      });
      return;
    }
    if (it.run) {
      _closePicker();
      if (onPick) onPick({
        kind: "md",
        seed: it.seed != null ? it.seed : "",
        caret: Number(it.caret) || 0,
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
      if (!list.classList.contains("open") || !list._tok ||
          list._tok.start !== tok.start || list._tok.query !== tok.query) {
        list._navPath = [];
        list._navItems = null;
        list._navLoading = false;
      }
      _render(el, tok, list);
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
        if (list._mode === "nav" && list._navPath && list._navPath.length) {
          e.preventDefault();
          list._navPath.pop();
          list._navItems = null;
          list._navLoading = false;
          _render(el, list._tok, list);
        } else _close(list);
      } else if ((e.key === "ArrowLeft" || e.key === "Backspace") &&
                 list._mode === "nav" && !list._tok.query &&
                 list._navPath && list._navPath.length) {
        e.preventDefault();
        list._navPath.pop();
        list._navItems = null;
        list._navLoading = false;
        _render(el, list._tok, list);
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
