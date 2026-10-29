// Browse controller — owns FilterBuilder + TimePicker + RecordTable + group/sort + search + save-as-query.
// Extracted from browse.html inline script. Template inlines BROWSE_DATA and calls BrowseController.init().
window.BrowseController = (function () {
  var _types = [];
  var _fieldTypes = {};
  var _globalDims = ["date"];
  var _yearMin = 2000;
  var _yearMax = 2100;

  var _fb = null;
  var _rt = null;
  var tp = null;

  var _browse = { type: null, chips: [], exprManual: "", search: "", _activeField: null };
  var _fieldCache = {};
  var _exprVisible = false;
  var _typeDimsCache = {};
  var _curGroupType = null;
  var _searchTimer = null;

  function init(cfg) {
    cfg = cfg || {};
    _types = cfg.types || [];
    _fieldTypes = cfg.fieldTypes || {};
    _globalDims = cfg.globalDims || ["date"];
    _yearMin = (cfg.yearRange && cfg.yearRange[0]) || 2000;
    _yearMax = (cfg.yearRange && cfg.yearRange[cfg.yearRange.length - 1]) || 2100;

    _fb = new FilterBuilder({
      containerId: "browse-filter",
      types: _types,
      onRun: function (expr) { runBrowse(); },
      onTypeFields: function (t, e) { _refreshGroupSortForType(t, e ? e.dimensions : null); }
    });
    _fb.init();

    _rt = new RecordTable({
      containerId: "result-area",
      returnTo: "/browse",
      enableBulk: true,
      quickEdit: true,
      fieldTypes: _fieldTypes,
      exportName: "browse_results",
      onRefresh: function () { runBrowse(); }
    });

    _populateGroupSort(true);

    tp = new TimePicker({
      prefix: "b-",
      yearMin: _yearMin,
      yearMax: _yearMax,
      onChange: function (code) { runBrowse(); }
    });

    // Restore state from URL params
    (function () {
      var params = new URLSearchParams(window.location.search);
      var run = params.get("run");
      var time = params.get("time");
      var file = params.get("file");
      var search = params.get("search");
      if (time === "range") {
        tp.setTime("range", null, params.get("from_date"), params.get("to_date"));
      } else if (time) {
        tp.setTime(time, params.get("custom_time"));
      } else if (file) {
        var base = file.split("/").pop();
        var year = base.replace(".log", "");
        if (/^\d{4}$/.test(year)) {
          tp.setTime("year", year);
        }
      }
      if (search) {
        var si = document.getElementById("b-search");
        if (si) si.value = search;
      }
      if (run && run.startsWith("q:")) {
        // Load from query - for now just show chip builder
      }
      setTimeout(function () { runBrowse(); }, 100);
    })();

    window.addEventListener("pageshow", function (e) {
      if (e.persisted) window.location.reload();
    });
  }

  // ── Legacy stubs (called by remaining browse code) ──
  function renderTypeChips() { }
  function renderActiveChips() { }
  function renderFieldChips() { }
  function renderTagsSection() { }
  function fetchFields() { }
  function toggleChip(f, v) { if (_fb) _fb._toggleChip(f, "=", v); }
  function closeValueRow() { if (_fb) _fb.closeValueRow(); }
  function addTextFilter() { if (_fb) _fb.addTextValue(); }
  function syncExprFromChips() { if (_fb) _fb._syncExprFromChips(); }
  function chipsToExpr(chips) { return _fb ? _fb._chipsToExpr() : ""; }
  function updateWherePreview() { if (_fb) _fb._syncExprFromChips(); }
  function parseExprToChips(e) { return _fb ? _fb._parseExpr(e) : []; }
  function onExprInput() { if (_fb) _fb._onExprInput(); }
  window.toggleAdvancedMode = function () { };
  window.applyAdvancedExpr = function () { };
  window.cancelAdvancedExpr = function () { };
  window.toggleExprMode = function () { };

  function _groupSortOptions(dims) {
    var placeholder = '<option value="">— select —</option>';
    return placeholder + (dims || []).map(function (f) {
      return '<option value="' + f + '">' + f + '</option>';
    }).join("");
  }

  function _populateGroupSort(fromUrl, dims) {
    var grp = document.getElementById("b-group");
    var sort = document.getElementById("b-sort");
    if (!grp || !sort) return;
    var prevG = grp.value, prevS = sort.value;
    if (!dims) {
      if (_fb && _fb._type) {
        dims = [];
      } else {
        dims = _globalDims || ["date"];
      }
    }
    var opts = _groupSortOptions(dims);
    grp.innerHTML = opts;
    sort.innerHTML = opts;
    var g = prevG, s = prevS;
    if (fromUrl) {
      var params = new URLSearchParams(window.location.search);
      g = params.get("group") || "";
      s = params.get("sort") || "";
    }
    if (g && grp.querySelector('option[value="' + g + '"]')) grp.value = g;
    if (s && sort.querySelector('option[value="' + s + '"]')) sort.value = s;
  }

  var _typeDimsCache = {};
  var _curGroupTypeLocal = null;

  function _refreshGroupSortForType(t, dims) {
    if (!t) t = _fb && _fb._type;
    if (!t) {
      _curGroupTypeLocal = null;
      _populateGroupSort(false);
      return;
    }
    if (t !== _curGroupTypeLocal) {
      _curGroupTypeLocal = t;
      _populateGroupSort(false, []);
    }
    if (dims) { _typeDimsCache[t] = dims; _populateGroupSort(false, dims); return; }
    if (_typeDimsCache[t]) { _populateGroupSort(false, _typeDimsCache[t]); return; }
    if (_typeDimsCache[t] === null) return;
    _typeDimsCache[t] = null;
    var url = "/api/type_fields/" + encodeURIComponent(t);
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        _typeDimsCache[t] = data.dimensions || [];
        if (_fb && _fb._type === t) _populateGroupSort(false, _typeDimsCache[t]);
      })
      .catch(function () { _typeDimsCache[t] = ["date"]; if (_fb && _fb._type === t) _populateGroupSort(false, _typeDimsCache[t]); });
  }

  function _params() {
    var time = tp ? (tp.getTime() || "tm") : "tm";
    var searchEl = document.getElementById("b-search");
    var groupEl = document.getElementById("b-group");
    var sortEl = document.getElementById("b-sort");
    var search = searchEl ? searchEl.value.trim() : "";
    var group = groupEl ? groupEl.value : "";
    var sort = sortEl ? sortEl.value : "";
    var expr = _fb ? _fb.getExpr() : "";
    var from_date = null, to_date = null;
    if (time === "range" && tp) {
      var r = tp.getRange();
      if (r) { from_date = r.from; to_date = r.to; }
    }
    return { where: [], expr: expr, time: time, search: search, group: group, sort: sort, from_date: from_date, to_date: to_date };
  }

  function runBrowse() {
    _refreshGroupSortForType();
    var area = document.getElementById("result-area");
    if (area) area.innerHTML = '<div class="card" style="color:var(--sub);font-size:13px;">Loading…</div>';
    fetch("/browse/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(_params())
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) { if (area) area.innerHTML = errorCard(d.error); return; }
        var data = d.data;
        if (!data) { if (area) area.innerHTML = errorCard("No data"); return; }
        if (data.kind === "group") {
          if (area) area.innerHTML = renderGroup(data);
        } else {
          if (area) area.innerHTML = "";
          if (_rt) _rt.render(data);
        }
      })
      .catch(function (e) { if (area) area.innerHTML = errorCard(String(e)); });
  }

  function clearBrowse() {
    if (_fb) _fb.clear();
    if (_rt) _rt.clear();
    _fieldCache = {};
    var si = document.getElementById("b-search");
    if (si) si.value = "";
    var ts = document.getElementById("b-time-select");
    if (ts) ts.value = "tm";
    if (tp) tp.reset();
    var g = document.getElementById("b-group");
    var s = document.getElementById("b-sort");
    if (g) g.value = "";
    if (s) s.value = "";
  }

  function onBTimeChange(val) { if (tp) tp.onSelectChange(val); }

  function errorCard(msg) {
    return '<div class="card"><div class="msg msg-error">' + msg + '</div></div>';
  }

  function summaryBar(d) {
    var parts = [];
    if (d.count !== undefined) parts.push('<span>' + d.count + ' records</span>');
    if (d.total_fmt) parts.push('<span>Total: <strong>' + d.total_fmt + '</strong></span>');
    if (d.avg_fmt) parts.push('<span>Avg: <strong>' + d.avg_fmt + '</strong></span>');
    if (d.time_label) parts.push('<span style="color:var(--sub)">' + d.time_label + '</span>');
    return parts.length
      ? '<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--sub);margin-bottom:10px;">' + parts.join("") + '</div>'
      : "";
  }

  function renderGroup(d) {
    var hasTot = d.has_amount;
    var heads = hasTot
      ? '<th>Group</th><th class="numeric">Count</th><th class="numeric">Total</th>'
      : '<th>Group</th><th class="numeric">Count</th>';
    var rows = (d.rows || []).map(function (r) {
      return hasTot
        ? '<tr><td>' + r.key + '</td><td class="numeric">' + r.count + '</td><td class="numeric">' + r.total_fmt + '</td></tr>'
        : '<tr><td>' + r.key + '</td><td class="numeric">' + r.count + '</td></tr>';
    }).join("");
    var foot = hasTot
      ? '<tr class="total-row"><td>Total</td><td class="numeric">' + d.grand_count + '</td><td class="numeric">' + d.grand_total_fmt + '</td></tr>'
      : '<tr class="total-row"><td>Total</td><td class="numeric">' + d.grand_count + '</td></tr>';
    return '<div class="card">' +
      '<div class="card-title">Grouped by ' + (d.fields || []).join(", ") + ' · ' + d.time_label + '</div>' +
      summaryBar(d) +
      '<div style="overflow-x:auto;"><table class="data-table"><thead><tr>' + heads + '</tr></thead><tbody>' + rows + foot + '</tbody></table></div>' +
      '</div>';
  }

  // Save as Query dialog
  function showSaveQuery() {
    var p = _params();
    var msg = document.getElementById("query-msg");
    if (msg) msg.style.display = "none";
    var inp = document.getElementById("query-name-input");
    if (inp) inp.value = "";
    var exprPreview = p.expr || "";
    var previewLines = [];
    if (exprPreview) previewLines.push('where = "' + exprPreview + '"');
    previewLines.push('time  = "' + p.time + '"');
    if (p.group) previewLines.push('group = ["' + p.group + '"]');
    if (p.sort) previewLines.push('sort = "' + p.sort + '"');
    if (p.search) previewLines.push('search = "' + p.search + '"');
    var qp = document.getElementById("query-preview");
    if (qp) qp.textContent = previewLines.join("\n");
    var dlg = document.getElementById("query-dialog");
    if (dlg) dlg.style.display = "flex";
    if (inp) inp.focus();
  }

  function hideQueryDialog() {
    var dlg = document.getElementById("query-dialog");
    if (dlg) dlg.style.display = "none";
  }

  function doSaveQuery() {
    var inp = document.getElementById("query-name-input");
    var msg = document.getElementById("query-msg");
    var name = inp ? inp.value.trim() : "";
    if (!name) { if (msg) { msg.textContent = "Enter a name."; msg.style.display = "block"; } return; }
    var p = _params();
    fetch("/api/save_query", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name, where: p.where, expr: p.expr, time: p.time,
        group: p.group, search: p.search, sort: p.sort })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.ok) {
          hideQueryDialog();
          var btn = document.querySelector('[onclick="showSaveQuery()"]');
          if (btn) { btn.textContent = "✔ Saved as '" + d.name + "'"; btn.style.background = "var(--success)"; }
          setTimeout(function () { if (btn) { btn.textContent = "💾 Save as Query"; btn.style.background = ""; } }, 3000);
        } else {
          if (msg) { msg.textContent = d.error; msg.style.display = "block"; }
        }
      })
      .catch(function (e) { if (msg) { msg.textContent = String(e); msg.style.display = "block"; } });
  }

  function debouncedBrowse() {
    updateWherePreview();
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(runBrowse, 500);
  }

  // Public API
  return {
    init: init,
    run: runBrowse,
    clear: clearBrowse,
    params: _params,
    onBTimeChange: onBTimeChange,
    showSaveQuery: showSaveQuery,
    hideQueryDialog: hideQueryDialog,
    doSaveQuery: doSaveQuery,
    debouncedBrowse: debouncedBrowse,
    // expose for legacy global access
    _fb: function () { return _fb; },
    _rt: function () { return _rt; },
    tp: function () { return tp; }
  };
})();

// Back-compat globals used by template onclick handlers and FilterBuilder
function runBrowse() { window.BrowseController.run(); }
function clearBrowse() { window.BrowseController.clear(); }
function onBTimeChange(val) { window.BrowseController.onBTimeChange(val); }
function showSaveQuery() { window.BrowseController.showSaveQuery(); }
function hideQueryDialog() { window.BrowseController.hideQueryDialog(); }
function doSaveQuery() { window.BrowseController.doSaveQuery(); }
function debouncedBrowse() { window.BrowseController.debouncedBrowse(); }
var _browse = { get type() { var f = window.BrowseController._fb(); return f ? f._type : null; },
  get chips() { var f = window.BrowseController._fb(); return f ? f._chips : []; },
  exprManual: "", search: "", _activeField: null };
var _fieldCache = {};
var _exprVisible = false;
var tp = null; // alias set in init via window; keep for compat
