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
  return '<div class="card">' +
    '<div class="card-title">Grouped by ' + esc((d.fields || []).join(", ")) + ' · ' + esc(d.time_label) + '</div>' +
    exprBadge(d) +
    '<div style="overflow-x:auto;"><table class="data-table"><thead><tr>' + heads + '</tr></thead><tbody>' + rows + foot + '</tbody></table></div>' +
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
  return '<div class="card">' +
    '<div class="card-title">Pivot · ' + esc(d.row_field) + ' × ' + esc(d.col_field) + ' · ' + esc(d.time_label) + '</div>' +
    exprBadge(d) +
    '<div style="overflow-x:auto;"><table class="data-table"><thead><tr>' + heads + '</tr></thead><tbody>' + rows + foot + '</tbody></table></div>' +
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
  return '<div class="card">' +
    '<div class="card-title">Trend · ' + esc(d.filter_str) + '</div>' +
    exprBadge(d) +
    '<div style="overflow-x:auto;"><table class="data-table"><thead><tr>' + head + '</tr></thead><tbody>' + rows + '</tbody></table></div>' +
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
  var label = d.calendar_name === "__all__" ? "All records" : String(d.calendar_name || "");
  return '<div class="card">' +
    '<div class="card-title">Calendar · ' + esc(label) + '</div>' +
    '<div class="emb-kicker">' + esc(_monthName(d.month) + " " + d.year) + '</div>' +
    '<table class="emb-cal emb-cal-rec-grid"><thead><tr>' + wd.map(function (w) { return '<th class="emb-cal-wd">' + w + '</th>'; }).join("") +
    '</tr></thead><tbody>' + rows + '</tbody></table>' +
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
