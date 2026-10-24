// widget_form.js — the gallery widget form (spec Part C2).
//
// window.PtosWidgetForm.mount(container, {body, onSave(text), onCancel()})
// renders a metadata-driven editor for one ```ptos body: controls per key
// come from the server catalog (GET /api/widgets/catalog — the same field
// metadata the registry pins to each kind's whitelist), the body is parsed
// and re-serialized with PtosToml so unknown keys and the user's key order
// survive, and a debounced 400ms tick both validates the spec
// (POST /api/widgets/validate — inline errors, Save stays disabled while
// any error is showing) and refreshes a live preview through the same
// embedFetch/embedRenderBody path the note preview uses. An "Edit as
// text" toggle swaps in the generated TOML; switching back re-parses.
//
// When spec.view is missing or unknown the form first offers a kind
// select (and infers the kind from /api/embed/candidates when a unique
// owner is found), so a hand-written `name`-only embed is still editable.
// Loaded before slash_embed.js; requires widget_toml.js + embeds.js.
(function () {
  var _DEBOUNCE = 400;

  var _cat = null;
  var _catFetching = false;
  var _optCache = {};        // source -> Promise<values[]>
  var _cand = null;
  var _candFetching = false;
  var _timeOpts = null;      // [{label, value}]
  var _TIME_FALLBACK = [
    { label: "Today", value: "td" },
    { label: "This week", value: "tw" },
    { label: "This month", value: "tm" },
    { label: "Last month", value: "lm" },
    { label: "This year", value: "ty" },
    { label: "All time", value: "all" },
  ];

  // Inference order mirrors ptos_widgets.infer_kinds: dashboard → metric →
  // threshold → board → habit → calendar → due → project → query (+ todo).
  var _INFER = [
    ["d", "dashboard"], ["m", "metric"], ["t", "threshold"], ["b", "board"],
    ["h", "habit"], ["c", "calendar"], ["u", "due"], ["p", "project"],
    ["q", "query"], ["v", "todo"],
  ];

  function _esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function _loadCatalog() {
    if (_cat) return Promise.resolve(_cat);
    if (_catFetching) return new Promise(function (res) {
      var iv = setInterval(function () {
        if (_cat) { clearInterval(iv); res(_cat); }
      }, 30);
    });
    _catFetching = true;
    return fetch("/api/widgets/catalog")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        _cat = (d && d.ok)
          ? { kinds: d.kinds || [], starters: d.starters || [],
              categories: d.categories || [] }
          : { kinds: [], starters: [], categories: [] };
        _catFetching = false;
        return _cat;
      })
      .catch(function () {
        _cat = { kinds: [], starters: [], categories: [] };
        _catFetching = false;
        return _cat;
      });
  }

  function _loadOptions(source) {
    if (_optCache[source]) return _optCache[source];
    _optCache[source] = fetch(
      "/api/widgets/options?source=" + encodeURIComponent(source)
    ).then(function (r) { return r.json(); }).then(function (d) {
      return (d && d.ok && d.values) ? d.values : [];
    }).catch(function () { return []; });
    return _optCache[source];
  }

  function _loadCandidates() {
    if (_cand) return Promise.resolve(_cand);
    if (_candFetching) return new Promise(function (res) {
      var iv = setInterval(function () {
        if (_cand) { clearInterval(iv); res(_cand); }
      }, 30);
    });
    _candFetching = true;
    return fetch("/api/embed/candidates")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        _cand = {
          groups: (d && d.ok && d.groups) ? d.groups : [],
          time_options: (d && d.ok && d.time_options) ? d.time_options : null,
        };
        _timeOpts = _cand.time_options;
        _candFetching = false;
        return _cand;
      })
      .catch(function () {
        _cand = { groups: [], time_options: null };
        _candFetching = false;
        return _cand;
      });
  }

  function _kindEntry(view) {
    var hit = null;
    ((_cat && _cat.kinds) || []).forEach(function (k) {
      if (k.kind === view) hit = k;
    });
    return hit;
  }

  function _inferKinds(spec) {
    // Kinds whose candidate group owns spec.name, in inference order.
    var name = String(spec.name || "").trim();
    var out = [];
    if (!name || !_cand) return out;
    _INFER.forEach(function (pair) {
      var g = null;
      _cand.groups.forEach(function (gg) { if (gg.kind === pair[0]) g = gg; });
      if (g && (g.items || []).indexOf(name) !== -1) out.push(pair[1]);
    });
    return out;
  }

  function _toArr(v) {
    if (v == null || v === "") return [];
    return Array.isArray(v) ? v.slice() : [v];
  }

  function _chipsValue(arr) {
    if (!arr.length) return null;
    return arr.length === 1 ? arr[0] : arr;
  }

  // ── mount ────────────────────────────────────────────────────────────

  function mount(container, opts) {
    opts = opts || {};
    if (!container) return;
    container.innerHTML = "";

    var S = {
      el: container,
      opts: opts,
      spec: {},
      entry: null,
      parseError: "",
      textMode: false,
      textBuf: "",
      errors: [],
      seq: 0,
      timer: null,
      saveBtn: null,
      kindSel: null,
      errEls: {},
      topErr: null,
      preview: null,
      bodyEl: null,
      fieldsEl: null,
      textEl: null,
      toggleBtn: null,
      datalistSeq: 0,
    };

    try {
      S.spec = (typeof PtosToml !== "undefined")
        ? (PtosToml.parse(opts.body || "") || {}) : {};
    } catch (e) {
      S.parseError = String(e && e.message || e);
      S.textMode = true;
      S.textBuf = String(opts.body || "");
    }

    _loadCatalog().then(function () {
      return _loadCandidates();
    }).then(function () {
      _resolveEntry(S);
      _build(S);
      _schedule(S);
    });
  }

  function _resolveEntry(S) {
    var view = String(S.spec.view || "").toLowerCase().trim();
    S.entry = view ? _kindEntry(view) : null;
    if (S.entry) return;
    var owners = _inferKinds(S.spec);
    if (owners.length === 1) {
      S.entry = _kindEntry(owners[0]);
      if (S.entry && !S.spec.view) S.spec.view = owners[0];
    }
  }

  // ── DOM ──────────────────────────────────────────────────────────────

  function _btn(label, cls) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = cls;
    b.textContent = label;
    return b;
  }

  function _build(S) {
    var root = S.el;
    root.className = "wf-form";

    S.topErr = document.createElement("div");
    S.topErr.className = "wf-err wf-top-err";
    S.topErr.style.display = "none";
    root.appendChild(S.topErr);

    var head = document.createElement("div");
    head.className = "wf-head";
    var hl = document.createElement("span");
    hl.className = "wf-head-label";
    hl.textContent = S.entry
      ? (S.entry.label || S.entry.kind) : "Widget";
    head.appendChild(hl);
    root.appendChild(head);

    S.kindSel = document.createElement("select");
    S.kindSel.className = "wf-kind";
    S.kindSel.style.display = "none";
    S.kindSel.addEventListener("change", function () {
      S.spec.view = S.kindSel.value;
      S.entry = _kindEntry(S.kindSel.value);
      _renderFields(S);
      hl.textContent = S.entry ? (S.entry.label || S.entry.kind) : "Widget";
      _schedule(S);
    });
    root.appendChild(S.kindSel);

    S.fieldsEl = document.createElement("div");
    S.fieldsEl.className = "wf-fields";
    root.appendChild(S.fieldsEl);

    S.textEl = document.createElement("textarea");
    S.textEl.className = "wf-textbox md-block-edit-box";
    S.textEl.setAttribute("spellcheck", "false");
    S.textEl.rows = 10;
    S.textEl.style.display = "none";
    S.textEl.addEventListener("input", function () {
      S.textBuf = S.textEl.value;
      _schedule(S);
    });
    S.textEl.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.preventDefault(); _cancel(S); }
    });
    root.appendChild(S.textEl);

    S.preview = document.createElement("div");
    S.preview.className = "wf-preview";
    var pvLabel = document.createElement("div");
    pvLabel.className = "wf-label";
    pvLabel.textContent = "Preview";
    S.preview.appendChild(pvLabel);
    S.bodyEl = document.createElement("div");
    S.bodyEl.className = "wf-preview-frame md-embed";
    S.bodyEl.innerHTML = '<div class="md-embed-loading">…</div>';
    S.preview.appendChild(S.bodyEl);
    root.appendChild(S.preview);

    var actions = document.createElement("div");
    actions.className = "wf-actions";
    S.saveBtn = _btn("Save", "wf-save md-embed-edit-save");
    var cancel = _btn("Cancel", "wf-cancel md-embed-edit-cancel");
    S.toggleBtn = _btn("Edit as text", "wf-textlink");
    actions.appendChild(S.saveBtn);
    actions.appendChild(cancel);
    var sp = document.createElement("span");
    sp.className = "wf-spacer";
    actions.appendChild(sp);
    actions.appendChild(S.toggleBtn);
    root.appendChild(actions);

    S.saveBtn.addEventListener("click", function () { _save(S); });
    cancel.addEventListener("click", function () { _cancel(S); });
    S.toggleBtn.addEventListener("click", function () { _toggleText(S); });
    root.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !S.textMode) { e.preventDefault(); _cancel(S); }
    });

    if (S.textMode) _showText(S);
    else _renderFields(S);

    var focusable = root.querySelector(".wf-fields input, .wf-fields select, .wf-textbox");
    if (focusable) { try { focusable.focus(); } catch (e) {} }
  }

  function _showText(S) {
    S.textMode = true;
    S.textEl.style.display = "";
    S.fieldsEl.style.display = "none";
    S.preview.style.display = "none";
    S.kindSel.style.display = "none";
    S.toggleBtn.textContent = "Edit as form";
    if (!S.textBuf) {
      try { S.textBuf = PtosToml.serialize(S.spec); } catch (e) { S.textBuf = ""; }
    }
    S.textEl.value = S.textBuf;
    try { S.textEl.focus(); } catch (e) {}
  }

  function _toggleText(S) {
    if (!S.textMode) { _showText(S); return; }
    var next = {};
    try {
      next = (typeof PtosToml !== "undefined")
        ? (PtosToml.parse(S.textBuf || "") || {}) : {};
    } catch (e) {
      _topError(S, "TOML error — " + String(e && e.message || e));
      return;
    }
    _topError(S, "");
    S.textMode = false;
    S.textBuf = "";
    S.spec = next;
    S.textEl.style.display = "none";
    S.fieldsEl.style.display = "";
    S.preview.style.display = "";
    S.toggleBtn.textContent = "Edit as text";
    _resolveEntry(S);
    var hl = S.el.querySelector(".wf-head-label");
    if (hl) hl.textContent = S.entry ? (S.entry.label || S.entry.kind) : "Widget";
    _renderFields(S);
    _schedule(S);
  }

  function _topError(S, msg) {
    if (!S.topErr) return;
    S.topErr.textContent = msg || "";
    S.topErr.style.display = msg ? "" : "none";
  }

  // ── fields ───────────────────────────────────────────────────────────

  function _renderFields(S) {
    var box = S.fieldsEl;
    box.innerHTML = "";
    S.errEls = {};
    if (S.kindSel) {
      if (!S.entry) {
        S.kindSel.style.display = "";
        S.kindSel.innerHTML = "";
        var ph = document.createElement("option");
        ph.value = "";
        ph.textContent = "Show as — pick a widget kind";
        S.kindSel.appendChild(ph);
        ((_cat && _cat.kinds) || []).forEach(function (k) {
          var o = document.createElement("option");
          o.value = k.kind;
          o.textContent = k.label || k.kind;
          if (S.spec.view === k.kind) o.selected = true;
          S.kindSel.appendChild(o);
        });
      } else {
        S.kindSel.style.display = "none";
      }
    }
    if (!S.entry) {
      var hint = document.createElement("div");
      hint.className = "wf-help";
      hint.textContent = "Pick a kind, then fill in its fields.";
      box.appendChild(hint);
      return;
    }
    var basic = document.createElement("div");
    basic.className = "wf-basic";
    box.appendChild(basic);
    var adv = document.createElement("details");
    adv.className = "wf-more";
    var sum = document.createElement("summary");
    sum.textContent = "More options";
    adv.appendChild(sum);
    var advBox = document.createElement("div");
    advBox.className = "wf-more-body";
    adv.appendChild(advBox);
    var known = {};
    (S.entry.fields || []).forEach(function (f) {
      known[f.key] = 1;
      if (f.show_if === false) return;
      (f.advanced ? advBox : basic).appendChild(_field(S, f));
    });
    var unknown = Object.keys(S.spec).filter(function (k) { return !known[k]; });
    if (unknown.length) {
      var unk = document.createElement("div");
      unk.className = "wf-unknown";
      unk.textContent = "Other keys kept as-is: " + unknown.join(", ") +
        " (use Edit as text to change them).";
      advBox.appendChild(unk);
    }
    box.appendChild(adv);
  }

  function _field(S, f) {
    var wrap = document.createElement("div");
    wrap.className = "wf-field";
    wrap.dataset.key = f.key;

    var label = document.createElement("label");
    label.className = "wf-label";
    label.textContent = f.label || f.key;
    if (f.required) {
      var req = document.createElement("span");
      req.className = "wf-req";
      req.textContent = " *";
      label.appendChild(req);
    }
    wrap.appendChild(label);

    var ctl;
    var t = f.type;
    if (t === "bool") ctl = _ctlBool(S, f);
    else if (t === "number") ctl = _ctlNumber(S, f);
    else if (t === "select") ctl = _ctlSelect(S, f);
    else if (t === "chips" || t === "multiselect") ctl = _ctlChips(S, f);
    else if (t === "saved_item") ctl = _ctlSaved(S, f);
    else if (t === "time_window") ctl = _ctlTime(S, f);
    else if (t === "field_filter") ctl = _ctlWhere(S, f);
    else if (t === "record_type") ctl = _ctlRecordType(S, f);
    else ctl = _ctlText(S, f);
    wrap.appendChild(ctl);

    if (f.help) {
      var help = document.createElement("div");
      help.className = "wf-help";
      help.textContent = f.help;
      wrap.appendChild(help);
    }
    var err = document.createElement("div");
    err.className = "wf-err";
    err.style.display = "none";
    wrap.appendChild(err);
    S.errEls[f.key] = err;
    return wrap;
  }

  function _onInput(S, key, fn) {
    return function (e) {
      fn(e.target);
      _schedule(S);
    };
  }

  function _set(S, key, value) {
    if (value === null || value === undefined || value === "") {
      delete S.spec[key];
    } else {
      S.spec[key] = value;
    }
  }

  function _ctlText(S, f) {
    var inp = document.createElement("input");
    inp.type = "text";
    inp.className = "wf-input";
    inp.value = S.spec[f.key] == null ? "" : String(S.spec[f.key]);
    inp.addEventListener("input", _onInput(S, f.key, function (el) {
      _set(S, f.key, el.value.trim());
    }));
    return inp;
  }

  function _ctlNumber(S, f) {
    var inp = document.createElement("input");
    inp.type = "number";
    inp.step = "1";
    inp.className = "wf-input";
    inp.value = S.spec[f.key] == null ? "" : String(S.spec[f.key]);
    inp.addEventListener("input", _onInput(S, f.key, function (el) {
      var raw = el.value.trim();
      if (!raw) { _set(S, f.key, null); return; }
      var n = Number(raw);
      S.spec[f.key] = isNaN(n) ? raw : n;
    }));
    return inp;
  }

  function _ctlBool(S, f) {
    var lab = document.createElement("label");
    lab.className = "wf-bool";
    var inp = document.createElement("input");
    inp.type = "checkbox";
    inp.className = "wf-check";
    inp.checked = S.spec[f.key] === true ||
      (S.spec[f.key] == null && f.default === true);
    inp.addEventListener("change", function () {
      S.spec[f.key] = inp.checked;
      _schedule(S);
    });
    lab.appendChild(inp);
    var txt = document.createElement("span");
    txt.textContent = " Yes";
    lab.appendChild(txt);
    return lab;
  }

  function _ctlSelect(S, f) {
    var sel = document.createElement("select");
    sel.className = "wf-input";
    var cur = S.spec[f.key];
    var vals = (f.options || []).slice();
    if (cur != null && cur !== "" && vals.indexOf(cur) === -1) vals.unshift(cur);
    var ph = document.createElement("option");
    ph.value = "";
    ph.textContent = "— none —";
    sel.appendChild(ph);
    vals.forEach(function (v) {
      var o = document.createElement("option");
      o.value = String(v);
      o.textContent = String(v);
      if (String(cur) === String(v)) o.selected = true;
      sel.appendChild(o);
    });
    sel.addEventListener("change", _onInput(S, f.key, function (el) {
      _set(S, f.key, el.value);
    }));
    return sel;
  }

  function _ctlChips(S, f) {
    var box = document.createElement("div");
    box.className = "wf-chips-wrap";
    var chips = document.createElement("div");
    chips.className = "wf-chips";
    box.appendChild(chips);
    var sel = new Set(_toArr(S.spec[f.key]).map(String));

    function repaint(values) {
      chips.innerHTML = "";
      values.forEach(function (v) {
        var b = _btn(String(v), "wf-chip" + (sel.has(String(v)) ? " on" : ""));
        b.setAttribute("aria-pressed", sel.has(String(v)) ? "true" : "false");
        b.addEventListener("click", function () {
          if (sel.has(String(v))) sel.delete(String(v));
          else sel.add(String(v));
          _set(S, f.key, _chipsValue(Array.from(sel)));
          b.classList.toggle("on", sel.has(String(v)));
          b.setAttribute("aria-pressed", sel.has(String(v)) ? "true" : "false");
          _schedule(S);
        });
        chips.appendChild(b);
      });
    }

    var staticOpts = (f.options || []).map(String);
    if (staticOpts.length) repaint(staticOpts);
    else {
      chips.innerHTML = '<span class="wf-help">Loading…</span>';
      _loadOptions(f.options_from || "").then(function (vals) {
        var out = vals.map(String);
        _toArr(S.spec[f.key]).forEach(function (v) {
          if (out.indexOf(String(v)) === -1) out.push(String(v));
        });
        repaint(out);
      });
    }
    return box;
  }

  function _ctlSaved(S, f) {
    if (!f.options_from) return _ctlText(S, f);
    var sel = document.createElement("select");
    sel.className = "wf-input";
    var cur = S.spec[f.key] == null ? "" : String(S.spec[f.key]);
    var ph = document.createElement("option");
    ph.value = "";
    ph.textContent = f.required ? "— choose —" : "— none —";
    sel.appendChild(ph);
    if (cur) {
      var co = document.createElement("option");
      co.value = cur;
      co.textContent = cur;
      co.selected = true;
      sel.appendChild(co);
    }
    sel.addEventListener("change", _onInput(S, f.key, function (el) {
      _set(S, f.key, el.value);
    }));
    _loadOptions(f.options_from).then(function (vals) {
      vals.forEach(function (v) {
        if (String(v) === cur) return;
        var o = document.createElement("option");
        o.value = String(v);
        o.textContent = String(v);
        sel.appendChild(o);
      });
    });
    return sel;
  }

  function _ctlTime(S, f) {
    var sel = document.createElement("select");
    sel.className = "wf-input";
    var cur = S.spec.time == null ? "" : String(S.spec.time);
    var opts = [{ label: "Default (as configured)", value: "" }]
      .concat(_timeOpts || _TIME_FALLBACK);
    if (cur && !opts.some(function (o) { return o.value === cur; })) {
      opts.push({ label: cur, value: cur });
    }
    opts.forEach(function (o) {
      var el = document.createElement("option");
      el.value = o.value;
      el.textContent = o.label;
      if (String(cur) === String(o.value)) el.selected = true;
      sel.appendChild(el);
    });
    sel.addEventListener("change", function () {
      _set(S, "time", sel.value);
      _schedule(S);
    });
    return sel;
  }

  function _ctlWhere(S, f) {
    var wrap = document.createElement("div");
    var inp = document.createElement("input");
    inp.type = "text";
    inp.className = "wf-input";
    inp.placeholder = "type=expense AND amount>100";
    inp.value = S.spec[f.key] == null ? "" : String(S.spec[f.key]);
    S.datalistSeq += 1;
    var dlId = "wf-fields-" + S.datalistSeq;
    var dl = document.createElement("datalist");
    dl.id = dlId;
    inp.setAttribute("list", dlId);
    inp.addEventListener("input", _onInput(S, f.key, function (el) {
      _set(S, f.key, el.value.trim());
    }));
    _loadOptions("schema.fields").then(function (vals) {
      vals.forEach(function (v) {
        var o = document.createElement("option");
        o.value = String(v);
        dl.appendChild(o);
      });
    });
    wrap.appendChild(inp);
    wrap.appendChild(dl);
    return wrap;
  }

  function _ctlRecordType(S, f) {
    var sel = document.createElement("select");
    sel.className = "wf-input";
    var cur = S.spec[f.key] == null ? "" : String(S.spec[f.key]);
    var ph = document.createElement("option");
    ph.value = "";
    ph.textContent = "— none —";
    sel.appendChild(ph);
    sel.addEventListener("change", _onInput(S, f.key, function (el) {
      _set(S, f.key, el.value);
    }));
    _loadOptions("schema.types").then(function (vals) {
      vals.forEach(function (v) {
        var o = document.createElement("option");
        o.value = String(v);
        o.textContent = String(v);
        if (String(cur) === String(v)) o.selected = true;
        sel.appendChild(o);
      });
    });
    return sel;
  }

  // ── debounced refresh: validate + preview ────────────────────────────

  function _schedule(S) {
    if (S.timer) clearTimeout(S.timer);
    S.timer = setTimeout(function () { S.timer = null; _refresh(S); },
                          _DEBOUNCE);
  }

  function _body(S) {
    if (S.textMode) return S.textBuf;
    try { return PtosToml.serialize(S.spec); } catch (e) { return null; }
  }

  function _refresh(S) {
    var body = _body(S);
    if (body === null) {
      _topError(S, "Widget body could not be serialized.");
      if (S.saveBtn) S.saveBtn.disabled = true;
      return;
    }
    if (!body.trim()) {
      _applyErrors(S, []);
      _paintPreview(S, null, "Empty widget body — pick fields above.");
      if (S.saveBtn) S.saveBtn.disabled = false;
      return;
    }
    var seq = ++S.seq;
    fetch("/api/widgets/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: body }),
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (seq !== S.seq) return;
      var errs = (d && d.ok && Array.isArray(d.errors)) ? d.errors : [];
      if (d && !d.ok && d.error) errs = [{ field: "body", message: d.error }];
      _applyErrors(S, errs);
      var blocking = errs.length > 0;
      if (S.saveBtn) S.saveBtn.disabled = blocking;
      if (blocking) _paintPreview(S, null, "Fix the errors above to preview.");
    }).catch(function () {
      if (seq !== S.seq) return;
      _applyErrors(S, []);
      if (S.saveBtn) S.saveBtn.disabled = false;
    });

    if (typeof embedFetch !== "function") return;
    embedFetch(body, false).then(function (res) {
      if (seq !== S.seq) return;
      if (S.saveBtn && S.saveBtn.disabled) return;
      if (!res.ok) _paintPreview(S, null, res.error || "Failed to load widget");
      else _paintPreview(S, res.data, "");
    });
  }

  function _applyErrors(S, errs) {
    S.errors = errs || [];
    Object.keys(S.errEls).forEach(function (k) { S.errEls[k].style.display = "none"; });
    _topError(S, "");
    var extra = [];
    S.errors.forEach(function (e) {
      var el = e && S.errEls[e.field];
      if (el) {
        el.textContent = e.message || "";
        el.style.display = "";
      } else {
        extra.push((e.field ? e.field + ": " : "") + (e.message || ""));
      }
    });
    if (extra.length) _topError(S, extra.join(" · "));
  }

  function _paintPreview(S, data, errMsg) {
    if (!S.bodyEl) return;
    if (errMsg) {
      S.bodyEl.innerHTML = '<div class="msg msg-error">' + _esc(errMsg) + "</div>";
      return;
    }
    if (!data) {
      S.bodyEl.innerHTML = '<div class="md-embed-loading">…</div>';
      return;
    }
    var link = data.link
      ? '<a class="md-embed-link" href="' + _esc(data.link) + '">Open →</a>' : "";
    S.bodyEl.innerHTML =
      '<div class="md-embed-head">' +
        '<span class="md-embed-title">' +
          _esc(data.title || data.name || "Widget") + "</span>" + link +
      "</div>" +
      '<div class="md-embed-body"></div>';
    var be = S.bodyEl.querySelector(".md-embed-body");
    if (be && typeof embedRenderBody === "function") embedRenderBody(be, data);
  }

  function _save(S) {
    if (S.saveBtn && S.saveBtn.disabled) return;
    var text = _body(S);
    if (text == null) return;
    if (S.textMode) {
      try { PtosToml.parse(text || ""); }
      catch (e) {
        _topError(S, "TOML error — " + String(e && e.message || e));
        return;
      }
    }
    if (S.opts.onSave) S.opts.onSave(text);
  }

  function _cancel(S) {
    if (S.timer) { clearTimeout(S.timer); S.timer = null; }
    if (S.opts.onCancel) S.opts.onCancel();
  }

  window.PtosWidgetForm = { mount: mount };
})();
