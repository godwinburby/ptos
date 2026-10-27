// widgets.js — shared query/dashboard render helpers.
// Extracted from queries.html so both the Queries page and the markdown
// embed mounter (embeds.js) render results identically.

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function errorCard(msg) {
  return '<div class="card"><div class="msg msg-error">' + esc(msg) + '</div></div>';
}

function renderResult(d) {
  if (!d) return errorCard("No data");
  switch (d.kind) {
    case "dashboard":    return renderDashboard(d);
    case "metric":       return renderMetric(d);
    case "group":        return renderGroup(d);
    case "pivot":        return renderPivot(d);
    case "trend":        return renderTrend(d);
    case "threshold":    return renderThresholdResult(d.thresholds || []);
    case "records":      return renderRecordsStatic(d);
    case "board":        return renderBoard(d);
    case "habit":        return renderHabit(d);
    case "calendar":     return renderCalendar(d);
    case "due":          return renderDue(d);
    case "project":      return renderProject(d);
    case "todo":         return renderTodo(d);
    case "todo_summary": return renderTodoSummary(d);
    case "journal":      return renderJournal(d);
    case "capture":      return renderCapture(d);
    case "quick_add":    return renderQuickAdd(d);
    case "quick_add_multi": return renderQuickAddMulti(d);
    case "time_picker": return '<div class="card" style="color:var(--sub);font-size:13px;">' +
      'Time window picker — available on Home or in a live preview.</div>';
    default:             return errorCard("Unknown result type");
  }
}

function renderCapture(d) {
  return '<div class="card"><div style="display:flex;gap:8px;flex-wrap:wrap;">' +
    '<input type="text" class="cap-input" placeholder="Quick record… (Enter to capture)" disabled ' +
    'style="flex:1;min-width:180px;padding:8px 12px;border-radius:8px;border:1.5px solid var(--border);background:var(--bg);color:var(--text);font-size:14px;">' +
    '<button type="button" class="btn btn-primary" disabled>Capture</button>' +
    '<button type="button" class="btn btn-ghost" disabled>Convert</button></div></div>';
}

function renderQuickAdd(d) {
  var names = (d.frequent || []).concat(d.remaining || []);
  if (!names.length) return '<div class="card" style="color:var(--sub);font-size:13px;">No quick-add presets.</div>';
  return '<div class="chip-group">' + names.map(function (name) {
    return '<a class="preset-chip" href="/add?preset=' +
      encodeURIComponent(name) + '">+ ' + esc(name) + '</a>';
  }).join("") + '</div>';
}

function renderQuickAddMulti(d) {
  var presets = d.presets || {};
  var names = Object.keys(presets);
  if (!names.length) return '<div class="card" style="color:var(--sub);font-size:13px;">No multi-record presets.</div>';
  return '<div class="chip-group">' + names.map(function (name) {
    var detail = presets[name] ? ' <span style="opacity:.6;font-size:11px;">(' + esc(presets[name]) + ')</span>' : '';
    return '<span class="preset-chip">+ ' + esc(name) + detail + '</span>';
  }).join("") + '</div>';
}

function exprBadge(d) {
  if (!d.where_expr && !d.query_name) return "";
  const name = d.query_name ? '<strong>' + esc(d.query_name) + '</strong>' : "";
  const expr = d.where_expr
    ? '<code style="font-size:11px;background:var(--bg);padding:2px 8px;border-radius:4px;color:var(--sub);word-break:break-all;">' + esc(d.where_expr) + '</code>'
    : "";

  const parts = [];
  if (d.query_group) parts.push('<span style="color:var(--accent);">⬇ ' + esc(Array.isArray(d.query_group) ? d.query_group.join(", ") : d.query_group) + '</span>');
  if (d.query_sort) parts.push('<span style="color:var(--warn);">⬆ ' + esc(d.query_sort) + '</span>');
  if (d.query_sum) parts.push('<span>∑</span>');
  if (d.query_search) parts.push('<span>🔍 "' + esc(d.query_search) + '"</span>');
  if (d.query_pivot) parts.push('<span>⊞</span>');
  if (d.query_trend) parts.push('<span>↗ ' + esc(d.query_trend) + '</span>');

  return '<div style="font-size:13px;color:var(--sub);margin-bottom:10px;">' +
    '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">' +
      name + expr +
    '</div>' +
    (parts.length ? '<div style="margin-top:6px;font-size:12px;display:flex;gap:10px;flex-wrap:wrap;">' + parts.join("") + '</div>' : "") +
  '</div>';
}

function _dashboardStatCard(i, bare) {
  var card = '<div class="stat-card' + (i.highlight ? ' c-' + esc(i.highlight) : '') + '">';
  var inner =
    '<div class="stat-label">' + esc((i.name || '').replace(/_/g, ' ')) + '</div>' +
    '<div class="stat-value" style="font-size:20px;">' + esc(i.value) + '</div>' +
    '<div class="stat-sub">' + esc(i.sub || '') + '</div>';
  if (i.query_url) {
    return '<a href="' + esc(i.query_url) + '" style="text-decoration:none;">' +
      card + inner + '</div></a>';
  }
  return card + inner + '</div>';
}

function renderDashboard(d, opts) {
  opts = opts || {};
  var groups = d.groups && d.groups.length
    ? d.groups
    : [{ name: '', items: d.items || [] }];
  var html = groups.map(function (g) {
    var label = g.name
      ? '<div class="stat-group-label">' + esc(g.name) + '</div>' : '';
    var cards = (g.items || []).map(function (i) {
      return _dashboardStatCard(i, opts.bare);
    }).join('');
    return label + '<div class="stat-grid">' + cards + '</div>';
  }).join('');
  if (opts.bare) return html;
  return '<div class="card"><div class="card-title">Dashboard · ' + esc(d.name) + '</div>' +
    exprBadge(d) + html + '</div>';
}

function renderMetric(d) {
  return '<div class="card">' +
    '<div class="card-title">Metric</div>' +
    exprBadge(d) +
    '<div style="font-size:28px;font-weight:800;color:var(--accent);">' + esc(d.value) + '</div>' +
    '<div style="font-size:13px;color:var(--sub);margin-top:4px;">' + esc(d.name.replace(/_/g, " ")) + '</div>' +
  '</div>';
}

function renderGroup(d) {
  const hasTot = d.has_amount;
  const heads = hasTot
    ? '<th>Group</th><th class="numeric">Count</th><th class="numeric">Total</th>'
    : '<th>Group</th><th class="numeric">Count</th>';
  const rows = (d.rows || []).map(r => hasTot
    ? '<tr><td>' + esc(r.key) + '</td><td class="numeric">' + esc(r.count) + '</td><td class="numeric">' + esc(r.total_fmt) + '</td></tr>'
    : '<tr><td>' + esc(r.key) + '</td><td class="numeric">' + esc(r.count) + '</td></tr>').join("");
  const foot = hasTot
    ? '<tr class="total-row"><td>Total</td><td class="numeric">' + esc(d.grand_count) + '</td><td class="numeric">' + esc(d.grand_total_fmt) + '</td></tr>'
    : '<tr class="total-row"><td>Total</td><td class="numeric">' + esc(d.grand_count) + '</td></tr>';
  const table = '<div style="overflow-x:auto;"><table class="data-table"><thead><tr>' + heads + '</tr></thead><tbody>' + rows + foot + '</tbody></table></div>';
  const body = d.chart
    ? qtWrap(renderChart(d.chart, _groupChartData(d),
        { label: "Grouped by " + (d.fields || []).join(", ") }), table)
    : table;
  return '<div class="card">' +
    '<div class="card-title">Grouped by ' + esc((d.fields || []).join(", ")) + ' · ' + esc(d.time_label) + '</div>' +
    exprBadge(d) +
    body +
    summaryBar(d) +
  '</div>';
}

function renderPivot(d) {
  const cols  = d.cols || [];
  const heads = '<th>' + esc(d.row_field) + '</th>' + cols.map(c => '<th class="numeric">' + esc(c) + '</th>').join("") + '<th class="numeric">Total</th>';
  const rows  = (d.rows || []).map(r => {
    const cells = cols.map(c => '<td class="numeric">' + esc(r[c] || 0) + '</td>').join("");
    return '<tr><td>' + esc(r.label) + '</td>' + cells + '<td class="numeric" style="font-weight:700">' + esc(r.total) + '</td></tr>';
  }).join("");
  const totCells = cols.map(c => '<td class="numeric" style="font-weight:700">' + esc((d.col_totals || {})[c] || 0) + '</td>').join("");
  const foot = '<tr class="total-row"><td>Total</td>' + totCells + '<td class="numeric">' + esc(d.grand) + '</td></tr>';
  const table = '<div style="overflow-x:auto;"><table class="data-table"><thead><tr>' + heads + '</tr></thead><tbody>' + rows + foot + '</tbody></table></div>';
  const label = "Pivot · " + d.row_field + " × " + d.col_field;
  let body = table;
  if (d.chart === "stacked") {
    body = qtWrap(chartStacked(_pivotStackedData(d), { label: label }), table);
  } else if (d.chart === "bar") {
    body = qtWrap(renderChart("bar", _pivotBarData(d), { label: label }), table);
  }
  return '<div class="card">' +
    '<div class="card-title">Pivot · ' + esc(d.row_field) + ' × ' + esc(d.col_field) + ' · ' + esc(d.time_label) + '</div>' +
    exprBadge(d) +
    body +
  '</div>';
}

function renderTrend(d) {
  const has  = d.has_amount;
  const head = has
    ? '<th>Period</th><th class="numeric">Count</th><th class="numeric">Total</th><th class="numeric">Avg</th>'
    : '<th>Period</th><th class="numeric">Count</th>';
  const rows = (d.periods || []).map(p => has
    ? '<tr><td>' + esc(p.label) + '</td><td class="numeric">' + esc(p.count) + '</td><td class="numeric">' + esc(p.total_fmt) + '</td><td class="numeric">' + esc(p.avg_fmt) + '</td></tr>'
    : '<tr><td>' + esc(p.label) + '</td><td class="numeric">' + esc(p.count) + '</td></tr>').join("");
  const table = '<div style="overflow-x:auto;"><table class="data-table"><thead><tr>' + head + '</tr></thead><tbody>' + rows + '</tbody></table></div>';
  const body = d.chart
    ? qtWrap(renderChart(d.chart, _trendChartData(d),
        { label: "Trend " + (d.filter_str || "") }), table)
    : table;
  return '<div class="card">' +
    '<div class="card-title">Trend · ' + esc(d.filter_str) + '</div>' +
    exprBadge(d) +
    body +
  '</div>';
}

function renderThresholdResult(thresholds, opts) {
  opts = opts || {};
  if (!thresholds || !thresholds.length) {
    return opts.bare
      ? '<div style="color:var(--sub);font-size:13px;">No thresholds configured.</div>'
      : '<div class="card" style="color:var(--sub);">No thresholds configured.</div>';
  }
  var statusLabel = function(t) {
    if (t.direction === "max") {
      return t.status === "over" ? "OVER" : t.status === "warning" ? "WARN" : "OK";
    } else {
      return t.status === "met" ? "MET" : t.status === "warning" ? "WARN" : "OK";
    }
  };
  var bars = thresholds.map(function(t) {
    var pct = Math.min(t.pct || 0, 100);
    var inner = '<div class="thr-card" style="margin-bottom:8px;">' +
      '<div class="thr-row">' +
        '<span class="thr-name">' + esc((t.name || '').replace(/_/g, ' ')) + '</span>' +
        '<div class="thr-bar-wrap">' +
          '<div class="thr-bar-bg">' +
            '<div class="thr-bar-fill ' + esc(t.status || '') + '" style="width:' + pct + '%"></div>' +
          '</div>' +
        '</div>' +
        '<span class="thr-vals">' +
          pct.toFixed(0) + '% &nbsp; ' + esc(t.raw || 0) + ' / ' + esc(t.target || 0) +
          (t.unit ? ' (' + esc(t.unit) + ')' : '') +
          (t.direction === 'max' ? ' max' : ' min') +
        '</span>' +
        '<span class="thr-status ' + esc(t.status || '') + '">' + statusLabel(t) + '</span>' +
      '</div>' +
    '</div>';
    // Clickable like the home /thresholds rows: opens the referenced
    // query on /queries in the same window the status was computed over.
    return t.query_url
      ? '<a class="thr-link" href="' + esc(t.query_url) + '" ' +
        'style="text-decoration:none;color:inherit;display:block;">' + inner + '</a>'
      : inner;
  }).join("");
  if (opts.bare) return bars;
  return '<div class="card"><div class="card-title">Thresholds</div>' + bars + '</div>';
}

function summaryBar(d) {
  const parts = [];
  if (d.count !== undefined) parts.push('<span>' + esc(d.count) + ' records</span>');
  if (d.total_fmt) parts.push('<span>Total: <strong>' + esc(d.total_fmt) + '</strong></span>');
  if (d.avg_fmt)   parts.push('<span>Avg: <strong>' + esc(d.avg_fmt) + '</strong></span>');
  if (d.time_label) parts.push('<span style="color:var(--sub)">' + esc(d.time_label) + '</span>');
  return parts.length
    ? '<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--sub);margin-bottom:8px;">' + parts.join("") + '</div>'
    : "";
}

// ── Charts (inline SVG over group/trend/pivot results) ────────────────────────
// Pure string builders over the payload run_query already returns; no new
// dependencies, no canvas. Colors come from the --chart-N CSS variables so a
// theme change only touches base.css. Every label is esc()'d; every svg
// carries role="img" + an aria-label summary, and each bar/point gets a
// <title> tooltip.

var CHART_MAX_BARS = 12;

function _chartNum(x) {
  var n = Number(x);
  return isFinite(n) ? n : 0;
}

function _chartTick(v) {
  var a = Math.abs(v);
  if (a >= 1e9) return (v / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
  if (a >= 1e6) return (v / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  if (a >= 1e4) return (v / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(a < 10 ? 1 : 0);
}

function _chartDomain(values) {
  var lo = Math.min.apply(null, values.concat([0]));
  var hi = Math.max.apply(null, values.concat([0]));
  if (lo === hi) hi = lo + 1;
  var span = hi - lo;
  var raw = span / 3 || 1;
  var step = Math.pow(10, Math.floor(Math.log10(raw)));
  var r = raw / step;
  step *= r > 5 ? 10 : r > 2 ? 5 : r > 1 ? 2 : 1;
  return { lo: Math.floor(lo / step) * step, hi: Math.ceil(hi / step) * step, step: step };
}

function _chartY(dom, v, h) {
  return (dom.hi - v) / (dom.hi - dom.lo) * h;
}

function _chartX(dom, v, w) {
  return (v - dom.lo) / (dom.hi - dom.lo) * w;
}

function _chartTrunc(s, n) {
  s = String(s == null ? "" : s);
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function _chartFill(i, other) {
  if (other) return "var(--chart-other)";
  return "var(--chart-" + ((i % 8) + 1) + ")";
}

function _chartCap(items) {
  if (items.length <= CHART_MAX_BARS) return items;
  var sorted = items.slice().sort(function (a, b) { return Math.abs(b.value) - Math.abs(a.value); });
  var top = sorted.slice(0, CHART_MAX_BARS - 1);
  var rest = sorted.slice(CHART_MAX_BARS - 1);
  var sum = rest.reduce(function (s, it) { return s + it.value; }, 0);
  top.push({ label: "Other (" + rest.length + ")", value: sum, other: true });
  return top;
}

function _chartGrid(W, ml, mr, dom, ph, mt) {
  var svg = "";
  for (var t = dom.lo; t <= dom.hi + 1e-9; t += dom.step) {
    var gy = Math.round(_chartY(dom, t, ph) * 100) / 100 + mt;
    svg += '<line x1="' + ml + '" y1="' + gy + '" x2="' + (W - mr) + '" y2="' + gy +
      '" stroke="var(--border)" stroke-width="1"/>' +
      '<text x="' + (ml - 6) + '" y="' + (gy + 3.5) + '" text-anchor="end" font-size="10" fill="var(--sub)">' +
      esc(_chartTick(t)) + '</text>';
  }
  return svg;
}

function _svgWrap(W, H, label, inner, maxH) {
  return '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto' +
    (maxH ? ";max-height:" + maxH + "px" : "") +
    ';" role="img" aria-label="' + esc(label) + '">' + inner + '</svg>';
}

function chartBar(data, opts) {
  opts = opts || {};
  var W = 640, H = 240, ml = 52, mr = 8, mt = 10, mb = 34;
  var pw = W - ml - mr, ph = H - mt - mb;
  var vals = data.map(function (d) { return _chartNum(d.value); });
  var dom = _chartDomain(vals);
  var step = pw / Math.max(1, data.length);
  var bw = Math.max(2, Math.min(48, step * 0.65));
  var svg = _chartGrid(W, ml, mr, dom, ph, mt);
  var y0 = _chartY(dom, 0, ph) + mt;
  data.forEach(function (d, i) {
    var v = _chartNum(d.value);
    var x = ml + i * step + (step - bw) / 2;
    var y1 = _chartY(dom, v, ph) + mt;
    svg += '<rect x="' + x + '" y="' + Math.min(y0, y1) + '" width="' + bw +
      '" height="' + Math.max(1, Math.abs(y1 - y0)) +
      '" rx="2" fill="' + _chartFill(i, d.other) + '">' +
      '<title>' + esc(d.label) + ': ' + esc(_chartNum(v).toLocaleString()) + '</title></rect>';
    if (step >= 26 || i % 2 === 0) {
      svg += '<text x="' + (x + bw / 2) + '" y="' + (H - 10) +
        '" text-anchor="middle" font-size="10" fill="var(--sub)">' +
        esc(_chartTrunc(d.label, step >= 40 ? 12 : 8)) + '</text>';
    }
  });
  return _svgWrap(W, H, opts.label || "Bar chart", svg, 280);
}

function chartHBar(data, opts) {
  opts = opts || {};
  var rowH = 26, ml = 132, mr = 60, mt = 8, mb = 8;
  var W = 640;
  var pw = W - ml - mr;
  var H = mt + mb + data.length * rowH;
  var vals = data.map(function (d) { return _chartNum(d.value); });
  var dom = _chartDomain(vals);
  var svg = "";
  for (var t = dom.lo; t <= dom.hi + 1e-9; t += dom.step) {
    var gx = Math.round((ml + _chartX(dom, t, pw)) * 100) / 100;
    svg += '<line x1="' + gx + '" y1="' + mt + '" x2="' + gx + '" y2="' + (H - mb) +
      '" stroke="var(--border)" stroke-width="1"/>' +
      '<text x="' + gx + '" y="' + (H - 1) + '" text-anchor="middle" font-size="9" fill="var(--sub)">' +
      esc(_chartTick(t)) + '</text>';
  }
  var x0 = ml + _chartX(dom, 0, pw);
  data.forEach(function (d, i) {
    var v = _chartNum(d.value);
    var y = mt + i * rowH + 3;
    var bh = rowH - 8;
    var x1 = ml + _chartX(dom, v, pw);
    svg += '<text x="' + (ml - 8) + '" y="' + (y + bh / 2 + 3.5) +
      '" text-anchor="end" font-size="11" fill="var(--text)">' +
      esc(_chartTrunc(d.label, 16)) + '</text>' +
      '<rect x="' + Math.min(x0, x1) + '" y="' + y + '" width="' + Math.max(1, Math.abs(x1 - x0)) +
      '" height="' + bh + '" rx="2" fill="' + _chartFill(i, d.other) + '">' +
      '<title>' + esc(d.label) + ': ' + esc(v.toLocaleString()) + '</title></rect>' +
      '<text x="' + (Math.max(x0, x1) + 6) + '" y="' + (y + bh / 2 + 3.5) +
      '" font-size="10" fill="var(--sub)">' + esc(_chartTick(v)) + '</text>';
  });
  return _svgWrap(W, H, opts.label || "Horizontal bar chart", svg, Math.min(400, H + 12));
}

function chartLine(data, opts) {
  opts = opts || {};
  var W = 640, H = 240, ml = 52, mr = 12, mt = 10, mb = 34;
  var pw = W - ml - mr, ph = H - mt - mb;
  var vals = data.map(function (d) { return _chartNum(d.value); });
  var dom = _chartDomain(vals);
  var svg = _chartGrid(W, ml, mr, dom, ph, mt);
  var step = data.length > 1 ? pw / (data.length - 1) : 0;
  var pts = data.map(function (d, i) {
    return [ml + (data.length > 1 ? i * step : pw / 2),
            _chartY(dom, _chartNum(d.value), ph) + mt];
  });
  if (data.length > 1) {
    svg += '<polyline fill="none" stroke="var(--chart-1)" stroke-width="2" stroke-linejoin="round" points="' +
      pts.map(function (p) { return p[0] + "," + p[1]; }).join(" ") + '"/>';
  }
  data.forEach(function (d, i) {
    var p = pts[i];
    svg += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="3.5" fill="var(--chart-1)">' +
      '<title>' + esc(d.label) + ': ' + esc(_chartNum(d.value).toLocaleString()) + '</title></circle>';
    if (step >= 26 || i % 2 === 0 || data.length <= 2) {
      svg += '<text x="' + p[0] + '" y="' + (H - 10) +
        '" text-anchor="middle" font-size="10" fill="var(--sub)">' +
        esc(_chartTrunc(d.label, step >= 40 ? 12 : 10)) + '</text>';
    }
  });
  return _svgWrap(W, H, opts.label || "Line chart", svg, 280);
}

function _stackLegend(series) {
  return '<div class="qt-legend">' + series.map(function (s, i) {
    return '<span class="qt-leg"><span class="qt-swatch" style="background:' +
      _chartFill(i, s.other) + '"></span>' + esc(s.label) + '</span>';
  }).join("") + '</div>';
}

function chartStacked(pd, opts) {
  opts = opts || {};
  var cols = pd.cols || [], series = pd.series || [];
  var W = 640, H = 240, ml = 52, mr = 8, mt = 10, mb = 34;
  var pw = W - ml - mr, ph = H - mt - mb;
  var totals = cols.map(function (c, ci) {
    return series.reduce(function (s, ser) { return s + _chartNum(ser.values[ci]); }, 0);
  });
  var dom = _chartDomain(totals);
  var step = pw / Math.max(1, cols.length);
  var bw = Math.max(2, Math.min(56, step * 0.7));
  var svg = _chartGrid(W, ml, mr, dom, ph, mt);
  cols.forEach(function (c, ci) {
    var acc = 0;
    var x = ml + ci * step + (step - bw) / 2;
    series.forEach(function (ser, si) {
      var v = _chartNum(ser.values[ci]);
      if (!v) return;
      var yTop = _chartY(dom, acc + v, ph) + mt;
      var hgt = Math.abs(_chartY(dom, 0, ph) - _chartY(dom, v, ph));
      svg += '<rect x="' + x + '" y="' + yTop + '" width="' + bw + '" height="' + Math.max(1, hgt) +
        '" fill="' + _chartFill(si, ser.other) + '">' +
        '<title>' + esc(ser.label) + ' · ' + esc(c) + ': ' + esc(v.toLocaleString()) + '</title></rect>';
      acc += v;
    });
    if (step >= 26 || ci % 2 === 0) {
      svg += '<text x="' + (x + bw / 2) + '" y="' + (H - 10) +
        '" text-anchor="middle" font-size="10" fill="var(--sub)">' +
        esc(_chartTrunc(c, step >= 40 ? 12 : 8)) + '</text>';
    }
  });
  return _svgWrap(W, H, opts.label || "Stacked chart", svg, 280) + _stackLegend(series);
}

function renderChart(kind, data, opts) {
  opts = opts || {};
  if (!data || !data.length) {
    return '<div class="qt-empty">No data to chart.</div>';
  }
  if (kind === "bar" && data.length > 8) kind = "hbar";
  if (kind === "bar") return chartBar(data, opts);
  if (kind === "hbar") return chartHBar(data, opts);
  if (kind === "line") return chartLine(data, opts);
  if (kind === "stacked") return chartStacked({ cols: data.map(function (d) { return d.label; }),
    series: [{ label: "Value", values: data.map(function (d) { return d.value; }) }] }, opts);
  return "";
}

function qtWrap(chartHtml, tableHtml) {
  return '<div class="view-toggle qt-toggle">' +
    '<button type="button" class="qt-btn active" data-view="chart">Chart</button>' +
    '<button type="button" class="qt-btn" data-view="table">Table</button></div>' +
    '<div class="qt-body" data-qt-body="chart">' + chartHtml + '</div>' +
    '<div class="qt-body" data-qt-body="table" style="display:none;">' + tableHtml + '</div>';
}

function _groupChartData(d) {
  return _chartCap((d.rows || []).map(function (r) {
    return {
      label: String(r.key),
      value: d.has_amount ? _chartNum(r.total) : _chartNum(r.count)
    };
  }));
}

function _trendChartData(d, y) {
  y = y || d.y || (d.has_amount ? "total" : "count");
  return (d.periods || []).map(function (p) {
    var v;
    if (y === "total") v = _chartNum(p.total);
    else if (y === "avg") {
      var c = _chartNum(p.count);
      v = c ? _chartNum(p.total) / c : 0;
    } else v = _chartNum(p.count);
    return { label: String(p.label), value: v };
  });
}

function _pivotStackedData(d) {
  var cols = d.cols || [];
  var rows = (d.rows || []).slice().sort(function (a, b) {
    return _chartNum(b.total) - _chartNum(a.total);
  });
  var top = rows.slice(0, CHART_MAX_BARS - 1);
  var rest = rows.slice(CHART_MAX_BARS - 1);
  var series = top.map(function (r) {
    return { label: String(r.label), values: cols.map(function (c) { return _chartNum(r[c]); }) };
  });
  if (rest.length) {
    series.push({
      label: "Other (" + rest.length + ")",
      values: cols.map(function (c) {
        return rest.reduce(function (s, r) { return s + _chartNum(r[c]); }, 0);
      }),
      other: true
    });
  }
  return { cols: cols, series: series };
}

function _pivotBarData(d) {
  return (d.cols || []).map(function (c) {
    return { label: String(c), value: _chartNum((d.col_totals || {})[c]) };
  });
}

document.addEventListener("click", function (e) {
  var btn = e.target && e.target.closest ? e.target.closest(".qt-btn") : null;
  if (!btn) return;
  var toggle = btn.closest(".qt-toggle");
  if (!toggle || !toggle.parentElement) return;
  var view = btn.getAttribute("data-view");
  var btns = toggle.querySelectorAll(".qt-btn");
  for (var i = 0; i < btns.length; i++) btns[i].classList.toggle("active", btns[i] === btn);
  var bodies = toggle.parentElement.querySelectorAll(".qt-body");
  for (var j = 0; j < bodies.length; j++) {
    bodies[j].style.display = bodies[j].getAttribute("data-qt-body") === view ? "" : "none";
  }
});

function renderRecordsStatic(d) {
  var cols = d.columns || [];
  var recs = d.records || [];
  if (!recs.length) return '<div class="card"><div class="msg" style="color:var(--sub);">No records.</div></div>';
  var heads = cols.map(function(c) { return '<th>' + esc(c) + '</th>'; }).join('');
  var rows = recs.map(function(r) {
    var cells = cols.map(function(c) {
      var v = r[c];
      if (v === undefined || v === null) v = '';
      if (Array.isArray(v)) v = v.join(', ');
      return '<td>' + esc(String(v)) + '</td>';
    }).join('');
    return '<tr>' + cells + '</tr>';
  }).join('');
  var title = d.query_name ? ('Query · ' + d.query_name) : 'Records';
  return '<div class="card">' +
    '<div class="card-title">' + esc(title) + ' · ' + esc(d.time_label || '') + '</div>' +
    exprBadge(d) + summaryBar(d) +
    '<div style="overflow-x:auto;max-height:420px;">' +
      '<table class="data-table"><thead><tr>' + heads + '</tr></thead><tbody>' + rows + '</tbody></table>' +
    '</div>' +
  '</div>';
}

function _fmt(n) {
  var x = Number(n);
  if (isNaN(x)) return String(n == null ? "" : n);
  return Number.isInteger(x) ? x.toLocaleString() : x.toFixed(2);
}

function _monthName(m) {
  return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][(m || 1) - 1] || "";
}

function _pad2(n) {
  n = Number(n);
  return (n < 10 ? "0" : "") + n;
}

// ── Phase 2 embed kinds (board / habit / calendar / due / project) ─────────────
// Read-only compact renderers. Lane chips, mini month grids and stat rows
// reuse the .emb-* classes defined in the markdown-editor partial.

function renderBoard(d) {
  var cols = d.columns || [];
  var chips = cols.map(function (col) {
    var lane = (d.lanes && d.lanes[col]) || {};
    var label = lane.label || String(col).replace(/_/g, " ");
    var count = (d.counts || {})[col] || 0;
    var rollup = "";
    var rv = (d.rollups || {})[col];
    if (rv !== undefined && rv !== null) {
      var op = d.rollup_op || "count";
      var txt = op === "avg" ? "avg " + _fmt(rv) : op === "sum" ? _fmt(rv) : "count " + _fmt(rv);
      rollup = '<div class="emb-chip-sub">' + esc(txt) + '</div>';
    }
    return '<div class="emb-chip"><div class="emb-chip-name">' + esc(label) + '</div>' +
      '<div class="emb-chip-count">' + _fmt(count) + '</div>' + rollup + '</div>';
  }).join("");
  var matched = (d.match_field && d.grid_rows) ? d.grid_rows.length : null;
  return '<div class="card">' +
    '<div class="card-title">Board · ' + esc(String(d.board_name || "").replace(/_/g, " ")) + '</div>' +
    '<div class="emb-chip-row">' + chips + '</div>' +
    (matched !== null ? '<div class="emb-kicker" style="margin-top:8px;">' + _fmt(matched) + ' matched across columns</div>' : '') +
  '</div>';
}

function renderHabit(d) {
  var blk = (d.months && d.months.length) ? d.months[d.months.length - 1] : null;
  var wd = ["M", "T", "W", "T", "F", "S", "S"];
  var now = new Date();
  var today = now.getFullYear() + "-" + _pad2(now.getMonth() + 1) + "-" + _pad2(now.getDate());
  var monthHtml = "";
  if (blk) {
    var cells = (blk.days || []).map(function (day) {
      if (!day || !day.date) return '<td class="emb-cal-cell"></td>';
      var dnum = parseInt(day.date.slice(8, 10), 10);
      var on = day.present ? " cnt" : "";
      var out = day.is_today ? " today" : "";
      // data-* attrs let the interactive mount toggle a day without the
      // page's global ids; static embeds ignore them.
      var canToggle = !!d.toggleable && day.date <= today;
      return '<td class="emb-cal-cell' + on + out + (canToggle ? ' clickable' : '') + '"' +
        (canToggle ? ' data-date="' + esc(day.date) + '" data-present="' + (day.present ? 1 : 0) +
          '" data-today="' + (day.is_today ? 1 : 0) + '" tabindex="0" role="button"' : '') +
        ' title="' + esc(day.date) + '">' + dnum + '</td>';
    });
    var rows = [];
    for (var i = 0; i < cells.length; i += 7) rows.push("<tr>" + cells.slice(i, i + 7).join("") + "</tr>");
    monthHtml = '<div style="margin-top:8px;">' +
      '<div class="emb-kicker">' + esc(blk.name) + '</div>' +
      '<table class="emb-cal"><thead><tr>' + wd.map(function (w) { return '<th class="emb-cal-wd">' + w + '</th>'; }).join("") +
      '</tr></thead><tbody>' + rows.join("") + '</tbody></table></div>';
  }
  return '<div class="card" data-toggleable="' + (d.toggleable ? 1 : 0) + '" data-habit="' + esc(d.habit_name || "") + '">' +
    '<div class="card-title">Habit · ' + esc(String(d.habit_name || "").replace(/_/g, " ")) + '</div>' +
    '<div class="emb-stat">' +
      '<span><b data-stat="streak">' + _fmt(d.streak || 0) + '</b>-day streak</span>' +
      '<span data-stat="days">' + esc((d.days_done || 0) + " of " + (d.total_days || 0) + " days") + '</span>' +
      (d.range_label ? '<span>' + esc(d.range_label) + '</span>' : '') +
    '</div>' + monthHtml +
  '</div>';
}

function renderCalendar(d, opts) {
  opts = opts || {};
  var interactive = !!opts.interactive;
  var weeks = d.weeks || [];
  var wd = ["M", "T", "W", "T", "F", "S", "S"];
  var today = new Date();
  var t = { y: today.getFullYear(), m: today.getMonth() + 1, d: today.getDate() };
  var rows = weeks.map(function (week) {
    var cells = (week || []).map(function (cell) {
      if (!cell) return '<td class="emb-calc-cell empty"></td>';
      var cls = "emb-calc-cell";
      if (cell.count > 0) cls += " cnt";
      if (cell.day === t.d && d.year === t.y && d.month === t.m) cls += " today";
      var inner = '<div class="emb-calc-day">' + cell.day + '</div>';
      var recs = cell.records || [];
      recs.slice(0, 3).forEach(function (r) {
        var label = [r.type].concat(r.fields || []).filter(function (x) { return x; }).join(" · ");
        inner += '<div class="emb-calc-chip" title="' + esc(label) + '">' + esc(label) + '</div>';
      });
      if (recs.length > 3) inner += '<div class="emb-calc-more">+' + (recs.length - 3) + ' more</div>';
      return '<td class="' + cls + '"' + (interactive && cell.count > 0 ? ' data-calendar-day="' + cell.day + '" tabindex="0" role="button"' : '') + '>' + inner + '</td>';
    }).join("");
    return "<tr>" + cells + "</tr>";
  }).join("");
  var detailDays = [];
  weeks.forEach(function (week) {
    (week || []).forEach(function (cell) {
      if (cell && cell.records && cell.records.length) detailDays.push(cell);
    });
  });
  var details = detailDays.map(function (cell) {
    var iso = d.year + "-" + _pad2(d.month) + "-" + _pad2(cell.day);
    var recs = cell.records.map(function (r) {
      var label = [r.type].concat(r.fields || []).filter(function (x) { return x; }).join(" · ");
      var note = r.note ? '<div class="emb-cal-rec-note">' + esc(r.note) + '</div>' : "";
      return '<div class="emb-cal-rec"><span class="emb-cal-rec-label">' + esc(label) + '</span>' + note + '</div>';
    }).join("");
    return '<div class="emb-cal-day"' + (interactive ? ' data-calendar-detail="' + cell.day + '" style="display:none;"' : '') + '>' +
      '<div class="emb-cal-day-head">' +
        '<span>' + esc(iso) + '</span>' +
        '<a class="emb-cal-browse" href="/browse?time=range&from_date=' + encodeURIComponent(iso) + '&to_date=' + encodeURIComponent(iso) + '">Browse →</a>' +
      '</div>' + recs + '</div>';
  }).join("");
  var label = d.calendar_name === "__all__" ? "All records" : String(d.calendar_name || "");
  var detailBlock = detailDays.length
    ? '<div class="emb-cal-day-list">' + details + '</div>'
    : '<div class="msg emb-cal-empty" style="color:var(--sub);">No records this month.</div>';
  return '<div class="card">' +
    '<div class="card-title">Calendar · ' + esc(label) + '</div>' +
    '<div class="emb-kicker">' + esc(_monthName(d.month) + " " + d.year) + '</div>' +
    '<table class="emb-cal emb-cal-rec-grid"><thead><tr>' + wd.map(function (w) { return '<th class="emb-cal-wd">' + w + '</th>'; }).join("") +
    '</tr></thead><tbody>' + rows + '</tbody></table>' +
    detailBlock +
    '<div class="emb-stat"><span><b>' + _fmt(d.total_records || 0) + '</b> records</span></div>' +
  '</div>';
}

function renderDue(d, opts) {
  opts = opts || {};
  var rows = d.rows || [];
  if (!rows.length) {
    var empty = '<div class="msg" style="color:var(--sub);">Nothing outstanding.</div>';
    if (opts.bare) return empty;
    return '<div class="card"><div class="card-title">' + esc(d.title || "Due") + '</div>' + empty + '</div>';
  }
  var heatColor = { hot: "var(--error)", warm: "var(--warn)", cool: "var(--accent)" };
  // Same link the /due page rows use (open the located record, return to
  // the widget's own page) — always an anchor, static or interactive.
  var list = rows.map(function (r) {
    var hc = heatColor[r.heat] || "var(--sub)";
    var note = r.note ? '<span style="color:var(--sub);">— ' + esc(r.note) + '</span>' : "";
    var href = "/edit?filepath=" + encodeURIComponent(r.filepath || "") +
      "&lineno=" + encodeURIComponent(String(r.lineno == null ? "" : r.lineno)) +
      "&line=" + encodeURIComponent(r.line || "") +
      "&return_to=" + encodeURIComponent(d.link || "/due");
    return '<a class="emb-due-row" href="' + href + '" ' +
      'style="text-decoration:none;color:inherit;">' +
      '<span class="emb-heat" style="background:' + hc + ';"></span>' +
      '<span class="emb-name">' + esc(r.name) + '</span>' +
      '<span class="emb-due-gap">' + _fmt(r.days) + 'd</span>' + note +
      '<span class="emb-due-open" style="margin-left:auto;font-size:11px;color:var(--accent);">Open â†’</span>' +
    '</a>';
  }).join("");
  var count = d.full_count != null ? d.full_count
    : (d.count == null ? rows.length : d.count);
  if (opts.bare) {
    return list +
      '<div class="emb-stat" style="margin-top:8px;"><span><b>' + _fmt(count) + '</b> overdue</span></div>';
  }
  return '<div class="card"><div class="card-title">' + esc(d.title || "Due") + '</div>' + list +
    '<div class="emb-stat" style="margin-top:8px;"><span><b>' + _fmt(count) + '</b> overdue</span></div>' +
  '</div>';
}

function renderTodoSummary(d) {
  var parts = [];
  if (d.overdue) parts.push('<span style="color:var(--error);">' + _fmt(d.overdue) + ' overdue</span>');
  if (d.overdue && d.due_today) parts.push('<span style="color:var(--sub);"> · </span>');
  if (d.due_today) parts.push('<span style="color:var(--accent);">' + _fmt(d.due_today) + ' due today</span>');
  if (!parts.length) parts.push('<span style="color:var(--sub);">No todos due today</span>');
  return '<a href="' + esc(d.link || "/todo") + '" style="display:flex;align-items:center;gap:12px;text-decoration:none;">' +
    '<span style="font-size:14px;font-weight:600;color:var(--text);">' + parts.join("") + '</span>' +
    '<span style="margin-left:auto;color:var(--sub);font-size:13px;">→</span>' +
  '</a>';
}

function renderJournal(d) {
  return '<a href="' + esc(d.link || "/journal") + '" style="display:block;text-decoration:none;">' +
    '<span style="font-size:14px;font-weight:600;color:var(--text);">' +
    esc(d.preview || "No entry yet") + '</span>' +
  '</a>';
}

function renderProject(d, opts) {
  opts = opts || {};
  var heatColor = { hot: "var(--error)", warm: "var(--warn)", cool: "var(--accent)" };
  var hc = heatColor[d.heat] || "var(--sub)";
  if (opts.full) {
    var label = esc(d.label || d.name || "");
    var stats = [];
    if (d.todo_project) {
      stats.push("<span>Open: <b>" + _fmt(d.open_todos || 0) + "</b></span>");
      stats.push("<span>Done: <b>" + _fmt(d.done_todos || 0) + "</b></span>");
      if (d.overdue_todos) stats.push('<span style="color:var(--error)">Overdue: <b>' + _fmt(d.overdue_todos) + "</b></span>");
      stats.push("<span>Added/Done (month): <b>" + _fmt(d.todo_added || 0) + "/" + _fmt(d.todo_done || 0) + "</b></span>");
      if (d.todo_delta > 0) stats.push('<span style="color:var(--warn)">+' + _fmt(d.todo_delta) + " backlog</span>");
    }
    if (d.record_count) stats.push("<span>Records: <b>" + _fmt(d.record_count) + "</b></span>");
    if ((d.notes || []).length) stats.push("<span>Notes: <b>" + _fmt(d.notes.length) + "</b></span>");
    if ((d.journals || []).length) stats.push("<span>Journal: <b>" + _fmt(d.journals.length) + "</b></span>");
    function details(title, count, html) {
      return html ? '<details class="page-project-section"><summary>' + title + ' <span>(' + count + ')</span></summary><div>' + html + '</div></details>' : "";
    }
    var open = (d.open_items || []).map(function (t) {
      return '<div class="page-project-row"><b>' + esc(t.priority || "—") + '</b><span>' + esc(t.description || "") + '</span>' +
        (t.due ? '<small>Due ' + esc(t.due) + '</small>' : '') + '</div>';
    }).join("");
    var done = (d.done_items || []).map(function (t) {
      return '<div class="page-project-row"><b>✓</b><span>' + esc(t.description || "") + '</span>' +
        (t.completed_date ? '<small>' + esc(t.completed_date) + '</small>' : '') + '</div>';
    }).join("");
    var records = (d.record_items || []).slice(0, 20).map(function (r) {
      var fields = Object.keys(r || {}).filter(function (k) { return ["date", "type", "note", "_filepath", "_lineno"].indexOf(k) < 0; })
        .map(function (k) { return '<span><small>' + esc(k) + ':</small> ' + esc(r[k]) + '</span>'; }).join(" ");
      return '<div class="page-project-row"><b>' + esc(r.date || "") + '</b><span>' + esc(r.type || "") + ' ' + fields + (r.note ? ' <small>| ' + esc(r.note) + '</small>' : '') + '</span></div>';
    }).join("");
    var notes = (d.notes || []).map(function (n) {
      return '<div class="page-project-ref"><a href="/notes/edit/' + encodeURIComponent(n.path || "") + '">📝 ' + esc(n.display_name || String(n.path || "").replace(/\.md$/, "")) + '</a>' + (n.snippet ? '<small>' + esc(n.snippet) + '</small>' : '') + '</div>';
    }).join("");
    var journals = (d.journals || []).map(function (j) {
      var datePath = String(j.path || "").replace(/\.md$/, "");
      return '<div class="page-project-ref"><a href="/journal?date=' + encodeURIComponent(datePath) + '">' + esc(j.path || "") + '</a>' + (j.snippet ? '<small>' + esc(j.snippet) + '</small>' : '') + '</div>';
    }).join("");
    var stalls = (d.board_stalls || []).map(function (b) {
      return '<span class="page-project-stall">' + esc(b.column || b.label || "") + ': ' + _fmt(b.oldest_days || 0) + 'd</span>';
    }).join("");
    var links = [];
    if (d.todo_project) links.push('<a href="/todo?project=' + encodeURIComponent(d.todo_project) + '">Todos</a>');
    if (d.has_board) links.push('<a href="/board?board=' + encodeURIComponent(d.board_name || "") + '">Board</a>');
    if (d.record_count) links.push('<a href="/browse?where=' + encodeURIComponent("project=" + d.name) + '">Records</a>');
    return '<article class="page-project-card ' + esc(d.drift || "ok") + '">' +
      '<header><strong>' + label + '</strong><span class="page-project-badge">' + _fmt(d.stale_days || 0) + 'd ago · ' + esc(d.drift || "ok") + '</span>' +
      '<nav><a href="/projects/' + encodeURIComponent(d.name || "") + '/edit">Edit</a><a href="/projects/' + encodeURIComponent(d.name || "") + '/delete">Delete</a></nav></header>' +
      '<div class="page-project-stats">' + stats.join("") + '</div>' +
      (stalls ? '<div class="page-project-stalls">Board stalls: ' + stalls + '</div>' : '') +
      '<div class="page-project-sections">' +
      details("Todos", d.open_todos || 0, open) + details("Done", d.done_todos || 0, done) +
      details("Records", d.record_count || 0, records) + details("Notes", (d.notes || []).length, notes) +
      details("Journal", (d.journals || []).length, journals) + '</div>' +
      '<footer>' + links.join("") + '</footer></article>';
  }
  var lines = [
    '<span>drift: <b style="color:' + hc + ';">' + esc(d.drift || "ok") + '</b></span>',
    '<span>stale <b>' + esc(d.stale_days || 0) + '</b>d</span>',
    '<span>' + _fmt(d.open_todos || 0) + ' open · ' + _fmt(d.overdue_todos || 0) + ' overdue todos</span>',
    '<span>' + _fmt(d.record_count || 0) + ' records</span>',
  ];
  if (d.has_board && d.board_stalls) {
    lines.push('<span>' + _fmt(d.board_stalls) + ' stalled</span>');
  }
  var label = d.label || d.name || "";
  return '<div class="card">' +
    '<div class="card-title">Project · ' + esc(label) + '</div>' +
    '<div class="emb-stat">' + lines.join("") + '</div>' +
  '</div>';
}

// ── Todo widget ──────────────────────────────────────────────────────────────
// Shared by the /todo page's widget views, note embeds and the home page:
// pure string builder over the svc.query_todos payload (groups of
// {key,label,color,todos:[_todo_json]}), reusing the shared .todo-row CSS
// from components.css. Interactive behavior (complete/undo/add) is wired by
// widget_host.js's mount; static callers render the same markup untouched.

function _todoDueBadge(t) {
  if (!t.due) return "";
  var iso = String(t.due).slice(0, 10);
  var now = new Date();
  var today = now.getFullYear() + "-" + _pad2(now.getMonth() + 1) + "-" + _pad2(now.getDate());
  var cls = iso < today ? "overdue" : (iso === today ? "today" : "future");
  var m = parseInt(iso.slice(5, 7), 10);
  var dd = parseInt(iso.slice(8, 10), 10);
  var time = t.due_time ? " " + t.due_time : "";
  return '<span class="todo-due-badge ' + cls + '">' + dd + " " + _monthName(m) + time + '</span>';
}

function renderTodoRow(t) {
  var pri = t.priority
    ? '<div class="todo-pri ' + esc(t.priority) + '" title="Priority ' + esc(t.priority) + '">' + esc(t.priority) + '</div>'
    : '<div class="todo-pri none" title="No priority">—</div>';
  var dueBadge = _todoDueBadge(t);
  var projs = (t.projects || []).map(function (p) {
    return '<a class="todo-project" href="/todo?project=' + encodeURIComponent(p) + '">' + esc(p) + '</a>';
  }).join("");
  var ctxs = (t.contexts || []).map(function (c) {
    return '<a class="todo-context" href="/todo?context=' + encodeURIComponent(c) + '">' + esc(c) + '</a>';
  }).join("");
  var links = (t.links || []).map(function (lk) {
    return '<a class="todo-link-badge" href="/todo?linked_to=' + encodeURIComponent(lk) + '" title="Todos linked to ' + esc(lk) + '">' + esc(lk) + '</a>';
  }).join("");
  var idBadge = t.id
    ? '<span class="todo-link-badge" title="id:' + esc(t.id) + '">id:' + esc(t.id) + '</span>'
    : "";
  return '<div class="todo-row' + (t.done ? " completed" : "") + '"' +
    ' data-line="' + (t.line_no == null ? "" : t.line_no) + '"' +
    ' data-raw="' + esc(t.raw_line || "") + '">' +
    '<div class="todo-check' + (t.done ? " checked" : "") + '"' +
      ' data-todo-act="' + (t.done ? "undo" : "complete") + '"' +
      ' role="button" tabindex="0"' +
      ' title="' + (t.done ? "Undo" : "Complete") + '"></div>' +
    pri +
    '<div class="todo-body">' +
      '<div class="todo-desc">' + esc(t.description) + '</div>' +
      '<div class="todo-meta">' + idBadge + links + dueBadge + projs + ctxs + '</div>' +
    '</div>' +
  '</div>';
}

function renderTodoGroup(g) {
  var rows = (g.todos || []).map(renderTodoRow).join("");
  return '<div class="todo-group" data-group="' + esc(g.key || "") + '">' +
    '<div class="todo-group-head" style="color:' + esc(g.color || "var(--sub)") + '">' +
      '<span>' + esc(g.label || "") + '</span>' +
      '<span class="todo-group-count">' + (g.todos || []).length + '</span>' +
    '</div>' + rows + '</div>';
}

function renderTodo(d) {
  d = d || {};
  var parts = [];
  if (d.add) {
    var f = d.filters || {};
    var pre = [];
    if (f.project && String(f.project).charAt(0) !== "-") {
      var p = String(f.project);
      pre.push(p.charAt(0) === "+" ? p : "+" + p);
    }
    if (f.context) {
      var c = String(f.context);
      pre.push(c.charAt(0) === "@" ? c : "@" + c);
    }
    if (f.priority) pre.push("(" + f.priority + ")");
    parts.push(
      '<div class="todo-add-bar">' +
        '<input type="text" class="todo-add-input" placeholder="Add a task…"' +
        ' value="' + esc(pre.join(" ")) + '">' +
        '<button type="button" class="btn btn-ghost btn-sm todo-add-btn">Add</button>' +
      '</div>');
  }
  var groups = d.groups || [];
  if (groups.length) {
    parts.push(groups.map(renderTodoGroup).join(""));
    if (d.total_open) {
      parts.push('<div class="emb-stat" style="padding:6px 12px 10px;">' +
        '<span><b>' + _fmt(d.total_open) + '</b> open</span></div>');
    }
  } else {
    parts.push('<div class="msg" style="color:var(--sub);margin:10px 12px;">No todos.</div>');
  }
  return '<div class="card">' + parts.join("") + '</div>';
}
