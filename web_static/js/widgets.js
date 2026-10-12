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
