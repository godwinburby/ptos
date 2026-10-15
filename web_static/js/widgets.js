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
    case "dashboard": return renderDashboard(d);
    case "metric":    return renderMetric(d);
    case "group":     return renderGroup(d);
    case "pivot":     return renderPivot(d);
    case "trend":     return renderTrend(d);
    case "threshold": return renderThresholdResult(d.thresholds || []);
    case "records":   return renderRecordsStatic(d);
    case "board":     return renderBoard(d);
    case "habit":     return renderHabit(d);
    case "calendar":  return renderCalendar(d);
    case "due":       return renderDue(d);
    case "project":   return renderProject(d);
    default:          return errorCard("Unknown result type");
  }
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

function renderDashboard(d) {
  const items = (d.items || []).map(i =>
    '<div class="stat-card">' +
      '<div class="stat-label">' + esc(i.name.replace(/_/g, " ")) + '</div>' +
      '<div class="stat-value" style="font-size:20px;">' + esc(i.value) + '</div>' +
      '<div class="stat-sub">' + esc(d.time_label || "") + '</div>' +
    '</div>').join("");
  return '<div class="card"><div class="card-title">Dashboard · ' + esc(d.name) + '</div>' +
    exprBadge(d) +
    '<div class="stat-grid">' + items + '</div></div>';
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

function renderThresholdResult(thresholds) {
  if (!thresholds || !thresholds.length) return '<div class="card" style="color:var(--sub);">No thresholds configured.</div>';
  var statusLabel = function(t) {
    if (t.direction === "max") {
      return t.status === "over" ? "OVER" : t.status === "warning" ? "WARN" : "OK";
    } else {
      return t.status === "met" ? "MET" : t.status === "warning" ? "WARN" : "OK";
    }
  };
  var bars = thresholds.map(function(t) {
    var pct = Math.min(t.pct || 0, 100);
    return '<div class="thr-card" style="margin-bottom:8px;">' +
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
  }).join("");
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
  var monthHtml = "";
  if (blk) {
    var cells = (blk.days || []).map(function (day) {
      if (!day || !day.date) return '<td class="emb-cal-cell"></td>';
      var dnum = parseInt(day.date.slice(8, 10), 10);
      var on = day.present ? " cnt" : "";
      var out = day.is_today ? " today" : "";
      return '<td class="emb-cal-cell' + on + out + '">' + dnum + '</td>';
    });
    var rows = [];
    for (var i = 0; i < cells.length; i += 7) rows.push("<tr>" + cells.slice(i, i + 7).join("") + "</tr>");
    monthHtml = '<div style="margin-top:8px;">' +
      '<div class="emb-kicker">' + esc(blk.name) + '</div>' +
      '<table class="emb-cal"><thead><tr>' + wd.map(function (w) { return '<th class="emb-cal-wd">' + w + '</th>'; }).join("") +
      '</tr></thead><tbody>' + rows.join("") + '</tbody></table></div>';
  }
  return '<div class="card">' +
    '<div class="card-title">Habit · ' + esc(String(d.habit_name || "").replace(/_/g, " ")) + '</div>' +
    '<div class="emb-stat">' +
      '<span><b>' + _fmt(d.streak || 0) + '</b>-day streak</span>' +
      '<span>' + esc((d.days_done || 0) + " of " + (d.total_days || 0) + " days") + '</span>' +
      (d.range_label ? '<span>' + esc(d.range_label) + '</span>' : '') +
    '</div>' + monthHtml +
  '</div>';
}

function renderCalendar(d) {
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
      return '<td class="' + cls + '">' + inner + '</td>';
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
    return '<div class="emb-cal-day">' +
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

function renderDue(d) {
  var rows = d.rows || [];
  if (!rows.length) {
    return '<div class="card"><div class="card-title">Due</div>' +
      '<div class="msg" style="color:var(--sub);">Nothing outstanding.</div></div>';
  }
  var heatColor = { hot: "var(--error)", warm: "var(--warn)", cool: "var(--accent)" };
  var list = rows.map(function (r) {
    var hc = heatColor[r.heat] || "var(--sub)";
    var note = r.note ? '<span style="color:var(--sub);">— ' + esc(r.note) + '</span>' : "";
    return '<div class="emb-due-row">' +
      '<span class="emb-heat" style="background:' + hc + ';"></span>' +
      '<span class="emb-name">' + esc(r.name) + '</span>' +
      '<span class="emb-due-gap">' + _fmt(r.days) + 'd</span>' + note +
    '</div>';
  }).join("");
  var count = d.count == null ? rows.length : d.count;
  return '<div class="card"><div class="card-title">Due</div>' + list +
    '<div class="emb-stat" style="margin-top:8px;"><span><b>' + _fmt(count) + '</b> overdue</span></div>' +
  '</div>';
}

function renderProject(d) {
  var heatColor = { hot: "var(--error)", warm: "var(--warn)", cool: "var(--accent)" };
  var hc = heatColor[d.heat] || "var(--sub)";
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
