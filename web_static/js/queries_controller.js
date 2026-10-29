// Queries controller — owns chip groups, TimePicker, RecordTable, runQuery, clearOut.
// Extracted from queries.html inline script.
window.QueriesController = (function () {
  var _qNames = [];
  var _mNames = [];
  var _dNames = [];
  var _tNames = [];
  var _fieldTypes = {};
  var _yearMin = 2000;
  var _yearMax = 2100;

  var _qKind = null;
  var _qName = null;
  var tp = null;
  var _rt = null;

  function init(cfg) {
    cfg = cfg || {};
    _qNames = cfg.queries || [];
    _mNames = cfg.metrics || [];
    _dNames = cfg.dashboards || [];
    _tNames = cfg.thresholds || [];
    _fieldTypes = cfg.fieldTypes || {};
    _yearMin = (cfg.yearRange && cfg.yearRange[0]) || 2000;
    _yearMax = (cfg.yearRange && cfg.yearRange[cfg.yearRange.length - 1]) || 2100;

    _rt = new RecordTable({
      containerId: "result-area",
      enableBulk: true,
      fieldTypes: _fieldTypes,
      exportName: "query_results",
      onRefresh: function () { runQuery(); }
    });

    tp = new TimePicker({
      prefix: "q-",
      yearMin: _yearMin,
      yearMax: _yearMax,
      onChange: function (code) { if (_qName) runQuery(); }
    });

    // Restore state from URL params
    (function () {
      var params = new URLSearchParams(window.location.search);
      var time = params.get("time");
      if (time === "range") {
        tp.setTime("range", null, params.get("from_date"), params.get("to_date"));
      } else if (time) {
        tp.setTime(time, params.get("custom_time"));
      }
    })();

    _renderAllChips();

    // Auto-run from URL params
    (function () {
      var params = new URLSearchParams(window.location.search);
      var run = params.get("run");
      var kind = params.get("kind") || "q";
      var time = params.get("time") || "";
      if (!run) return;
      var names;
      if (kind === "m") names = _mNames;
      else if (kind === "d") names = _dNames;
      else names = _qNames;
      if (names.indexOf(run) === -1) return;
      _qKind = kind;
      _qName = run;
      if (time) {
        if (tp) tp.setTime(time, params.get("custom_time"));
      }
      _renderAllChips();
      runQuery();
      setTimeout(function () {
        var area = document.getElementById("result-area");
        if (area) area.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 600);
    })();
  }

  function toggleSection(el) {
    var section = el.parentElement;
    section.classList.toggle("collapsed");
    var t = el.querySelector(".chip-toggle");
    if (t) t.textContent = section.classList.contains("collapsed") ? "+" : "\u2212";
  }

  function _selectChip(kind, name) {
    _qKind = kind;
    _qName = name;
    _renderAllChips();
    runQuery();
    _scrollToResults();
  }

  function _scrollToResults() {
    if (!window.matchMedia || !window.matchMedia("(max-width: 767px)").matches) return;
    var area = document.getElementById("result-area");
    if (area) area.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function _selectThreshold(name) {
    _qKind = "t";
    _qName = name;
    _renderAllChips();
    var area = document.getElementById("result-area");
    if (area) area.innerHTML = '<div class="card" style="color:var(--sub);font-size:13px;">Loading\u2026</div>';
    fetch("/api/thresholds/status")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) { if (area) area.innerHTML = errorCard(d.error || "Failed to load thresholds"); return; }
        var match = (d.thresholds || []).filter(function (t) { return t.name === name; });
        if (area) area.innerHTML = renderThresholdResult(match);
      })
      .catch(function (e) { if (area) area.innerHTML = errorCard(String(e)); });
    var builderLink = document.getElementById("builder-link");
    if (builderLink) builderLink.href = "/query-builder?section=thresholds";
    _scrollToResults();
  }

  function _renderAllChips() {
    var selected = (_qKind === "q") ? _qName : null;
    var el = document.getElementById("q-chip-group");
    if (el) renderChipGroup(el, _qNames, selected, function (n) { _selectChip("q", n); });
    selected = (_qKind === "m") ? _qName : null;
    el = document.getElementById("m-chip-group");
    if (el) renderChipGroup(el, _mNames, selected, function (n) { _selectChip("m", n); });
    selected = (_qKind === "d") ? _qName : null;
    el = document.getElementById("d-chip-group");
    if (el) renderChipGroup(el, _dNames, selected, function (n) { _selectChip("d", n); });
    el = document.getElementById("t-chip-group");
    if (el) renderChipGroup(el, _tNames, (_qKind === "t") ? _qName : null, function (n) { _selectThreshold(n); });
  }

  function onQTimeChange(val) { if (tp) tp.onSelectChange(val); }

  window._qGetTime = function () { return tp ? tp.getTime() : null; };

  function runQuery() {
    var time = window._qGetTime();
    var timeVal = document.getElementById("q-time-select") ? document.getElementById("q-time-select").value : "";
    if (timeVal === "custom" && !time) return;
    var from_date = null, to_date = null;
    if (time === "range" && tp) {
      var r = tp.getRange();
      if (r) { from_date = r.from; to_date = r.to; }
    }
    var area = document.getElementById("result-area");
    var kind = _qKind, name = _qName;
    if (!kind || !name) return;
    var builderLink = document.getElementById("builder-link");
    if (builderLink) {
      if (kind === "q") builderLink.href = "/query-builder?edit=" + encodeURIComponent(name) + "&section=queries";
      else if (kind === "m") builderLink.href = "/query-builder?edit=" + encodeURIComponent(name) + "&section=metrics";
      else if (kind === "d") builderLink.href = "/query-builder?edit=" + encodeURIComponent(name) + "&section=dashboards";
      else builderLink.href = "/query-builder";
    }
    if (area) area.innerHTML = '<div class="card" style="color:var(--sub);font-size:13px;">Loading\u2026</div>';
    fetch("/queries/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: kind, name: name, time: time, from_date: from_date, to_date: to_date })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) { if (area) area.innerHTML = errorCard(d.error); return; }
        var data = d.data;
        if (!data) { if (area) area.innerHTML = errorCard("No data"); return; }
        if (data.kind === "records") {
          renderRecords(data);
        } else {
          if (area) area.innerHTML = renderResult(data);
        }
      })
      .catch(function (e) { if (area) area.innerHTML = errorCard(String(e)); });
  }

  function clearOut() {
    _qKind = null;
    _qName = null;
    var ts = document.getElementById("q-time-select");
    if (ts) ts.value = "";
    if (tp) tp.reset();
    var area = document.getElementById("result-area");
    if (area) area.innerHTML = "";
    _renderAllChips();
  }

  function renderRecords(d) {
    var area = document.getElementById("result-area");
    if (area) area.innerHTML = "";
    if (_rt) _rt.render(d);
    var badge = exprBadge(d);
    if (badge && badge.trim() && area && area.firstChild) {
      var wrap = document.createElement("div");
      wrap.innerHTML = badge;
      area.insertBefore(wrap, area.firstChild);
    }
    return "";
  }

  return {
    init: init,
    run: runQuery,
    clear: clearOut,
    toggleSection: toggleSection,
    onQTimeChange: onQTimeChange,
    _qKind: function () { return _qKind; },
    _qName: function () { return _qName; }
  };
})();

// Back-compat globals
function runQuery() { window.QueriesController.run(); }
function clearOut() { window.QueriesController.clear(); }
function onQTimeChange(val) { window.QueriesController.onQTimeChange(val); }
function toggleSection(el) { window.QueriesController.toggleSection(el); }
var tp = null;
var _rt = null;
var _qKind = null;
var _qName = null;
var _fieldTypes = {};