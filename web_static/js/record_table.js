// ══════════════════════════════════════════════════════════════════════════════
// RecordTable  v2.0
// Drop-in modular records table.
//
// Usage:
//   var rt = new RecordTable({
//     containerId : "result-area",  // required
//     returnTo    : "/browse",      // optional, defaults to window.location.pathname
//     enableBulk  : true,           // optional, default true
//     onRefresh   : function() {}   // optional, called after delete / bulk ops
//   });
//   rt.render(data);   // data = { records:[], columns:[], count, total_fmt, avg_fmt, time_label }
//   rt.clear();
// ══════════════════════════════════════════════════════════════════════════════

function RecordTable(opts) {
  var self       = this;
  opts           = opts || {};
  var cid        = opts.containerId;
  var enableBulk = opts.enableBulk !== false;
  var onRefresh  = opts.onRefresh || function(){};

  // ── private state ──────────────────────────────────────────────────────────
  var _records  = [];
  var _cols     = [];
  var _selected = [];          // array of checked indices
  var _sortCol  = null;
  var _sortAsc  = true;
  var _delRec   = null;

  // ── tiny helpers ───────────────────────────────────────────────────────────
  function ge(id)  { return document.getElementById(id); }
  function esc(s)  {
    return String(s == null ? "" : s)
      .replace(/&/g,"&amp;").replace(/</g,"&lt;")
      .replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
  }

  // ── modal IDs (page-scoped, one set per page) ──────────────────────────────
  var M = {
    del:       "rt-del-dialog",
    delLine:   "rt-del-line",
    delMsg:    "rt-del-msg",
    bkBar:     "rt-bulk-bar",
    bkCount:   "rt-bulk-count",
    bkDel:     "rt-bulk-del-dialog",
    bkDelTop:  "rt-bulk-del-top",
    bkDelMsg:  "rt-bulk-del-msg",
    bkSet:     "rt-bulk-set-dialog",
    bkField:   "rt-bulk-set-field",
    bkValue:   "rt-bulk-set-value",
    bkPrev:    "rt-bulk-set-preview",
    bkSetMsg:  "rt-bulk-set-msg"
  };

  // ── inject modals once ─────────────────────────────────────────────────────
  function _injectModals() {
    if (ge(M.del)) return;

    var html =
      // single delete
      '<div id="'+M.del+'" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:800;align-items:center;justify-content:center;">' +
        '<div style="background:var(--card);border-radius:14px;padding:24px;width:340px;box-shadow:0 8px 32px rgba(0,0,0,.2);">' +
          '<div style="font-size:16px;font-weight:700;margin-bottom:12px;color:var(--error);">Delete Record</div>' +
          '<div style="font-size:13px;color:var(--sub);margin-bottom:8px;">This cannot be undone (backup is kept).</div>' +
          '<div id="'+M.delLine+'" style="font-family:monospace;font-size:12px;background:var(--bg);padding:8px;border-radius:6px;word-break:break-all;margin-bottom:14px;"></div>' +
          '<div id="'+M.delMsg+'" style="font-size:13px;color:var(--error);margin-bottom:10px;display:none;"></div>' +
          '<div style="display:flex;gap:10px;">' +
            '<button class="btn btn-primary" style="flex:1;background:var(--error);" onclick="RecordTable._del()">Delete</button>' +
            '<button class="btn btn-ghost" style="flex:1;" onclick="RecordTable._delClose()">Cancel</button>' +
          '</div>' +
        '</div>' +
      '</div>';

    if (enableBulk) {
      // bulk bar
      html +=
        '<div id="'+M.bkBar+'" style="display:none;position:fixed;bottom:70px;left:50%;transform:translateX(-50%);' +
        'background:var(--card);border:1.5px solid var(--accent);border-radius:12px;padding:10px 16px;' +
        'box-shadow:0 4px 24px rgba(0,0,0,.18);align-items:center;gap:10px;z-index:700;white-space:nowrap;">' +
          '<span id="'+M.bkCount+'" style="font-size:13px;font-weight:700;color:var(--accent);min-width:80px;"></span>' +
          '<button class="btn btn-ghost btn-sm" style="font-size:12px;" onclick="RecordTable._bkSetOpen()">✎ Set Field</button>' +
          '<button class="btn btn-ghost btn-sm" style="font-size:12px;color:var(--error);" onclick="RecordTable._bkDelOpen()">✕ Delete</button>' +
          '<button class="btn btn-ghost btn-sm" style="font-size:12px;" onclick="RecordTable._bkClear()">✕ Deselect</button>' +
        '</div>';
      // bulk delete confirm
      html +=
        '<div id="'+M.bkDel+'" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:810;align-items:center;justify-content:center;">' +
          '<div style="background:var(--card);border-radius:14px;padding:24px;width:340px;box-shadow:0 8px 32px rgba(0,0,0,.2);">' +
            '<div style="font-size:16px;font-weight:700;margin-bottom:8px;color:var(--error);">Bulk Delete</div>' +
            '<div id="'+M.bkDelTop+'" style="font-size:13px;color:var(--sub);margin-bottom:14px;"></div>' +
            '<div id="'+M.bkDelMsg+'" style="font-size:13px;color:var(--error);margin-bottom:10px;display:none;"></div>' +
            '<div style="display:flex;gap:10px;">' +
              '<button class="btn btn-primary" style="flex:1;background:var(--error);" onclick="RecordTable._bkDelConfirm()">Delete All</button>' +
              '<button class="btn btn-ghost" style="flex:1;" onclick="RecordTable._bkDelClose()">Cancel</button>' +
            '</div>' +
          '</div>' +
        '</div>';
      // bulk set
      html +=
        '<div id="'+M.bkSet+'" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:810;align-items:center;justify-content:center;">' +
          '<div style="background:var(--card);border-radius:14px;padding:24px;width:360px;box-shadow:0 8px 32px rgba(0,0,0,.2);">' +
            '<div style="font-size:16px;font-weight:700;margin-bottom:14px;">Set Field on Selected</div>' +
            '<div class="field-group" style="margin-bottom:10px;">' +
              '<label style="font-size:12px;">Field name</label>' +
              '<input type="text" id="'+M.bkField+'" placeholder="e.g. status, category" style="font-size:14px;" oninput="RecordTable._bkPrev()">' +
            '</div>' +
            '<div class="field-group" style="margin-bottom:10px;">' +
              '<label style="font-size:12px;">New value</label>' +
              '<input type="text" id="'+M.bkValue+'" placeholder="new value" style="font-size:14px;" oninput="RecordTable._bkPrev()">' +
            '</div>' +
            '<div id="'+M.bkPrev+'" style="font-size:12px;color:var(--sub);font-family:monospace;background:var(--bg);padding:8px;border-radius:6px;margin-bottom:12px;display:none;"></div>' +
            '<div id="'+M.bkSetMsg+'" style="font-size:13px;color:var(--error);margin-bottom:10px;display:none;"></div>' +
            '<div style="display:flex;gap:10px;">' +
              '<button class="btn btn-primary" style="flex:1;" onclick="RecordTable._bkSetConfirm()">Apply</button>' +
              '<button class="btn btn-ghost" style="flex:1;" onclick="RecordTable._bkSetClose()">Cancel</button>' +
            '</div>' +
          '</div>' +
        '</div>';
    }

    var wrap = document.createElement("div");
    wrap.innerHTML = html;
    document.body.appendChild(wrap);

    // backdrop dismiss
    ge(M.del).addEventListener("click", function(e){ if(e.target===this) RecordTable._delClose(); });
    if (enableBulk) {
      ge(M.bkDel).addEventListener("click", function(e){ if(e.target===this) RecordTable._bkDelClose(); });
      ge(M.bkSet).addEventListener("click", function(e){ if(e.target===this) RecordTable._bkSetClose(); });
    }
  }

  // ── summary bar ────────────────────────────────────────────────────────────
  function _summaryBar(d) {
    var p = [];
    if (d.count !== undefined) p.push("<span>"+esc(d.count)+" records</span>");
    if (d.total_fmt) p.push("<span>Total: <strong>"+esc(d.total_fmt)+"</strong></span>");
    if (d.avg_fmt)   p.push("<span>Avg: <strong>"+esc(d.avg_fmt)+"</strong></span>");
    if (d.time_label) p.push('<span style="color:var(--sub)">'+esc(d.time_label)+"</span>");
    return p.length
      ? '<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--sub);margin-bottom:10px;">'+p.join("")+"</div>"
      : "";
  }

  // ── row builder ────────────────────────────────────────────────────────────
  function _buildRows(recs, cols, returnTo) {
    return recs.map(function(r, idx) {
      var cells = cols.map(function(c) {
        var k = Object.keys(r).find(function(k){ return k.toLowerCase()===c.toLowerCase(); }) || c;
        return "<td>"+esc(r[k]||"")+"</td>";
      }).join("");

      var cb = "";
      if (enableBulk) {
        cb = r._line
          ? '<td style="text-align:center;width:32px;"><input type="checkbox" class="rt-row-cb" data-idx="'+idx+'" onchange="RecordTable._check(this)"></td>'
          : '<td style="width:32px;"></td>';
      }

      var acts = r._line
        ? '<td style="white-space:nowrap;">' +
          '<a class="btn btn-ghost btn-sm" style="padding:2px 8px;font-size:12px;" href="/edit?filepath='+encodeURIComponent(r._filepath)+'&lineno='+r._lineno+'&line='+encodeURIComponent(r._line)+'&return_to='+encodeURIComponent(returnTo)+'">✎</a> ' +
          '<button class="btn btn-ghost btn-sm" style="padding:2px 8px;font-size:12px;color:var(--error);" data-row=\''+JSON.stringify(r).replace(/'/g,"&#39;")+'\' onclick="RecordTable._openDel(JSON.parse(this.dataset.row))">✕</button>' +
          '</td>'
        : "<td></td>";

      return "<tr>"+cb+cells+acts+"</tr>";
    }).join("");
  }

  // ── sort value helper ──────────────────────────────────────────────────────
  function _cmp(a, b, asc) {
    if (a === b) return 0;
    if (a === null || a === undefined) return asc ? 1 : -1;
    if (b === null || b === undefined) return asc ? -1 : 1;
    var na = parseFloat(a), nb = parseFloat(b);
    if (!isNaN(na) && !isNaN(nb)) return asc ? na-nb : nb-na;
    var sa = String(a), sb = String(b);
    return asc ? sa.localeCompare(sb) : sb.localeCompare(sa);
  }

  // ── update bulk bar ────────────────────────────────────────────────────────
  function _updateBar() {
    if (!enableBulk) return;
    var bar = ge(M.bkBar);
    if (!bar) return;
    var n = _selected.length;
    if (n > 0) {
      ge(M.bkCount).textContent = n + " selected";
      bar.style.display = "flex";
    } else {
      bar.style.display = "none";
    }
  }

  // ══ PUBLIC ═════════════════════════════════════════════════════════════════

  self.render = function(d) {
    var container = ge(cid);
    if (!container) return;

    _injectModals();

    if (!d || !d.records || !d.records.length) {
      container.innerHTML = '<div class="card" style="color:var(--sub);text-align:center;padding:32px;">No records found.</div>';
      return;
    }

    _records  = d.records.slice();
    _cols     = (d.columns || []).filter(function(c){ return c.charAt(0) !== "_"; });
    _selected = [];
    _sortCol  = null;
    _sortAsc  = true;
    _updateBar();

    var returnTo = opts.returnTo || window.location.pathname;

    var cbHead = enableBulk
      ? '<th style="width:32px;text-align:center;"><input type="checkbox" id="rt-select-all" onchange="RecordTable._selAll(this)" title="Select all"></th>'
      : '';

    var heads = cbHead +
      _cols.map(function(c){
        return '<th class="sortable" onclick="RecordTable._sort(this,\''+c.replace(/'/g,"\\'")+'\')" style="cursor:pointer;">'+esc(c)+'</th>';
      }).join("") +
      '<th style="width:80px;"></th>';

    container.innerHTML =
      '<div class="card">' +
        _summaryBar(d) +
        '<div style="overflow-x:auto;">' +
          '<table class="data-table" id="rt-table">' +
            '<thead><tr>'+heads+'</tr></thead>' +
            '<tbody id="rt-tbody">'+_buildRows(_records, _cols, returnTo)+'</tbody>' +
          '</table>' +
        '</div>' +
      '</div>';
  };

  self.clear = function() {
    var container = ge(cid);
    if (container) container.innerHTML = "";
    _records = []; _cols = []; _selected = [];
    _updateBar();
  };

  // ── sorting ────────────────────────────────────────────────────────────────
  self._sort = function(th, col) {
    if (_sortCol === col) { _sortAsc = !_sortAsc; }
    else { _sortCol = col; _sortAsc = true; }

    document.querySelectorAll("#rt-table th.sortable").forEach(function(h){
      h.classList.remove("sort-asc","sort-desc");
    });
    th.classList.add(_sortAsc ? "sort-asc" : "sort-desc");

    var cl = col.toLowerCase(), asc = _sortAsc;
    _records.sort(function(a, b){
      var ak = Object.keys(a).find(function(k){ return k.toLowerCase()===cl; }) || col;
      var bk = Object.keys(b).find(function(k){ return k.toLowerCase()===cl; }) || col;
      return _cmp(a[ak], b[bk], asc);
    });

    _selected = [];
    var sa = ge("rt-select-all");
    if (sa) sa.checked = false;
    _updateBar();

    var tbody = ge("rt-tbody");
    if (tbody) tbody.innerHTML = _buildRows(_records, _cols, opts.returnTo || window.location.pathname);
  };

  // ── selection ──────────────────────────────────────────────────────────────
  self._check = function(cb) {
    var idx = parseInt(cb.dataset.idx);
    if (cb.checked) { if (_selected.indexOf(idx) < 0) _selected.push(idx); }
    else { _selected = _selected.filter(function(i){ return i !== idx; }); }
    _updateBar();
  };

  self._selAll = function(cb) {
    _selected = [];
    document.querySelectorAll(".rt-row-cb").forEach(function(box){
      box.checked = cb.checked;
      if (cb.checked) _selected.push(parseInt(box.dataset.idx));
    });
    _updateBar();
  };

  self._bkClear = function() {
    _selected = [];
    document.querySelectorAll(".rt-row-cb").forEach(function(b){ b.checked = false; });
    var sa = ge("rt-select-all");
    if (sa) sa.checked = false;
    _updateBar();
  };

  function _selRecs() {
    return _selected.map(function(i){ return _records[i]; }).filter(Boolean);
  }

  // ── single delete ──────────────────────────────────────────────────────────
  self._openDel = function(r) {
    if (!r || !r._line) return;
    _delRec = r;
    ge(M.delLine).textContent = r._line;
    ge(M.delMsg).style.display = "none";
    ge(M.del).style.display = "flex";
  };

  self._delClose = function() { ge(M.del).style.display = "none"; };

  self._del = function() {
    if (!_delRec) return;
    var msg = ge(M.delMsg);
    fetch("/api/records/delete", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({filepath:_delRec._filepath, old_line:_delRec._line, lineno:_delRec._lineno})
    }).then(function(r){ return r.json(); }).then(function(d){
      if (d.ok) { self._delClose(); onRefresh(); }
      else { msg.textContent = d.error || "Delete failed"; msg.style.display = "block"; }
    }).catch(function(e){ msg.textContent = String(e); msg.style.display = "block"; });
  };

  // ── bulk delete ────────────────────────────────────────────────────────────
  self._bkDelOpen = function() {
    var n = _selected.length;
    if (!n) return;
    ge(M.bkDelTop).textContent = "Delete "+n+" record"+(n>1?"s":"")+"? This cannot be undone (backup is kept).";
    ge(M.bkDelMsg).style.display = "none";
    ge(M.bkDel).style.display = "flex";
  };

  self._bkDelClose = function() { ge(M.bkDel).style.display = "none"; };

  self._bkDelConfirm = function() {
    var records = _selRecs().map(function(r){ return {filepath:r._filepath, line:r._line, lineno:r._lineno}; });
    var msg = ge(M.bkDelMsg);
    fetch("/api/records/bulk_delete", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({records:records})
    }).then(function(r){ return r.json(); }).then(function(d){
      if (d.ok) { self._bkDelClose(); self._bkClear(); onRefresh(); }
      else { msg.textContent = d.error || "Delete failed"; msg.style.display = "block"; }
    }).catch(function(e){ msg.textContent = String(e); msg.style.display = "block"; });
  };

  // ── bulk set ───────────────────────────────────────────────────────────────
  self._bkSetOpen = function() {
    if (!_selected.length) return;
    ge(M.bkField).value = "";
    ge(M.bkValue).value = "";
    ge(M.bkPrev).style.display = "none";
    ge(M.bkSetMsg).style.display = "none";
    ge(M.bkSet).style.display = "flex";
    setTimeout(function(){ ge(M.bkField).focus(); }, 50);
  };

  self._bkSetClose = function() { ge(M.bkSet).style.display = "none"; };

  self._bkPrev = function() {
    var f = ge(M.bkField).value.trim(), v = ge(M.bkValue).value.trim();
    var p = ge(M.bkPrev);
    if (f && v) {
      p.textContent = "Will apply: "+f+"="+v+" to "+_selected.length+" record"+(_selected.length>1?"s":"");
      p.style.display = "block";
    } else { p.style.display = "none"; }
  };

  self._bkSetConfirm = function() {
    var field = ge(M.bkField).value.trim(), value = ge(M.bkValue).value.trim();
    var msg = ge(M.bkSetMsg);
    if (!field || !value) { msg.textContent = "Field and value are required"; msg.style.display = "block"; return; }
    var records = _selRecs().map(function(r){ return {filepath:r._filepath, line:r._line, lineno:r._lineno}; });
    fetch("/api/records/bulk_set", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({records:records, set_args:[field+"="+value]})
    }).then(function(r){ return r.json(); }).then(function(d){
      if (d.ok) { self._bkSetClose(); self._bkClear(); onRefresh(); }
      else { msg.textContent = d.error || "Set failed"; msg.style.display = "block"; }
    }).catch(function(e){ msg.textContent = String(e); msg.style.display = "block"; });
  };

  // ── expose on global RecordTable for inline onclick handlers ───────────────
  // (set by the page after instantiation — see usage note below)
}
