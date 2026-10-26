// ══════════════════════════════════════════════════════════════════════════════
// RecordTable  v3.0
// Drop-in modular records table. Instance-scoped: several tables can live on
// one page (main results + widgets) without clobbering each other. Every
// generated id derives from a per-instance uid, modals are per-instance, and
// all interaction goes through delegated listeners on the instance's own
// container/modal wrap — no globals, no page-side handler wiring.
//
// Usage:
//   var rt = new RecordTable({
//     containerId : "result-area",  // id of the container element...
//     container   : el,             // ...or the element itself (widgets)
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
  var quickEdit = opts.quickEdit === true;
  var onRefresh  = opts.onRefresh || function(){};
  var _fieldTypes = opts.fieldTypes || {};
  var exportName = opts.exportName || "export";

  // ── private state ──────────────────────────────────────────────────────────
  var _records  = [];
  var _cols     = [];
  var _selected = [];          // array of checked indices
  var _sortCol  = null;
  var _sortAsc  = true;
  var _delRec   = null;
  var _page     = 1;
  var _pageSize = 100;
  var _wired    = false;

  // ── per-instance uid — every generated id derives from it ─────────────────
  RecordTable._seq = (RecordTable._seq || 0) + 1;
  var uid = "rt" + RecordTable._seq;

  // ── tiny helpers ───────────────────────────────────────────────────────────
  function ge(id)  { return document.getElementById(id); }
  function esc(s)  {
    return String(s == null ? "" : s)
      .replace(/&/g,"&amp;").replace(/</g,"&lt;")
      .replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
  }

  // ── modal ids (per-instance) ──────────────────────────────────────────────
  var M = {
    del:       uid + "-del-dialog",
    delLine:   uid + "-del-line",
    delMsg:    uid + "-del-msg",
    bkBar:     uid + "-bulk-bar",
    bkCount:   uid + "-bulk-count",
    bkDel:     uid + "-bulk-del-dialog",
    bkDelTop:  uid + "-bulk-del-top",
    bkDelMsg:  uid + "-bulk-del-msg",
    bkSet:     uid + "-bulk-set-dialog",
    bkField:   uid + "-bulk-set-field",
    bkValContainer: uid + "-bulk-set-val-ctnr",
    bkValInput: uid + "-bulk-set-val-input",
    bkPrev:    uid + "-bulk-set-preview",
    bkSetMsg:  uid + "-bulk-set-msg",
    wrap:      uid + "-modals",
    selectAll: uid + "-select-all",
    table:     uid + "-table",
    tbody:     uid + "-tbody",
    pagination: uid + "-pagination",
    quickEdit: uid + "-quick-edit",
    quickFrame: uid + "-quick-frame"
  };

  // ── delegated action wiring (once per instance) ───────────────────────────
  function _wire() {
    if (_wired) return;
    _wired = true;
    var container = _container();
    if (container) {
      container.addEventListener("click", function(e) {
        var t = e.target;
        if (!t.closest) return;
        var th = t.closest("th.sortable");
        if (th) { self._sort(th, th.dataset.col || ""); return; }
        var act = t.closest("[data-rt]");
        if (!act) return;
        var a = act.dataset.rt;
        if (a === "export") self._export();
        else if (a === "prev") self._prevPage();
        else if (a === "next") self._nextPage();
        else if (a === "quickedit") {
          try { _openQuickEdit(JSON.parse(decodeURIComponent(act.dataset.row))); } catch (err) {}
        }
        else if (a === "opendel") {
          try { self._openDel(JSON.parse(act.dataset.row)); } catch (err) {}
        }
      });
      container.addEventListener("change", function(e) {
        var t = e.target;
        if (t.classList && t.classList.contains("rt-row-cb")) self._check(t);
        else if (t.dataset && t.dataset.rt === "selall") self._selAll(t);
      });
    }
    var wrap = ge(M.wrap);
    if (!wrap) return;
    wrap.addEventListener("click", function(e) {
      if (e.target === ge(M.del)) { self._delClose(); return; }
      if (e.target === ge(M.bkDel)) { self._bkDelClose(); return; }
      if (e.target === ge(M.bkSet)) { self._bkSetClose(); return; }
      var act = e.target.closest && e.target.closest("[data-rt]");
      if (!act) return;
      if (act.dataset.rt === "quickclose") { _closeQuickEdit(); return; }
      switch (act.dataset.rt) {
        case "del": self._del(); break;
        case "delclose": self._delClose(); break;
        case "bksetopen": self._bkSetOpen(); break;
        case "bksetclose": self._bkSetClose(); break;
        case "bksetconfirm": self._bkSetConfirm(); break;
        case "bkdelopen": self._bkDelOpen(); break;
        case "bkdelclose": self._bkDelClose(); break;
        case "bkdelconfirm": self._bkDelConfirm(); break;
        case "bkclear": self._bkClear(); break;
      }
    });
    wrap.addEventListener("change", function(e) {
      if (e.target.id === M.bkField) { self._bkFieldChange(); self._bkPrev(); }
      else if (e.target.dataset && e.target.dataset.rt === "bkval") self._bkPrev();
    });
    wrap.addEventListener("input", function(e) {
      if (e.target.dataset && e.target.dataset.rt === "bkval") self._bkPrev();
    });
  }

  // ── inject modals once (per instance) ─────────────────────────────────────
  function _injectModals() {
    if (ge(M.wrap)) return;

    var html =
      // single delete
      '<div id="'+M.del+'" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:800;align-items:center;justify-content:center;">' +
        '<div style="background:var(--card);border-radius:14px;padding:24px;width:340px;box-shadow:0 8px 32px rgba(0,0,0,.2);">' +
          '<div style="font-size:16px;font-weight:700;margin-bottom:12px;color:var(--error);">Delete Record</div>' +
          '<div style="font-size:13px;color:var(--sub);margin-bottom:8px;">This cannot be undone (backup is kept).</div>' +
          '<div id="'+M.delLine+'" style="font-family:monospace;font-size:12px;background:var(--bg);padding:8px;border-radius:6px;word-break:break-all;margin-bottom:14px;"></div>' +
          '<div id="'+M.delMsg+'" style="font-size:13px;color:var(--error);margin-bottom:10px;display:none;"></div>' +
          '<div style="display:flex;gap:10px;">' +
            '<button class="btn btn-primary" style="flex:1;background:var(--error);" data-rt="del">Delete</button>' +
            '<button class="btn btn-ghost" style="flex:1;" data-rt="delclose">Cancel</button>' +
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
          '<button class="btn btn-ghost btn-sm" style="font-size:12px;" data-rt="bksetopen">✎ Set Field</button>' +
          '<button class="btn btn-ghost btn-sm" style="font-size:12px;color:var(--error);" data-rt="bkdelopen">✕ Delete</button>' +
          '<button class="btn btn-ghost btn-sm" style="font-size:12px;" data-rt="bkclear">✕ Deselect</button>' +
        '</div>';
      // bulk delete confirm
      html +=
        '<div id="'+M.bkDel+'" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:810;align-items:center;justify-content:center;">' +
          '<div style="background:var(--card);border-radius:14px;padding:24px;width:340px;box-shadow:0 8px 32px rgba(0,0,0,.2);">' +
            '<div style="font-size:16px;font-weight:700;margin-bottom:8px;color:var(--error);">Bulk Delete</div>' +
            '<div id="'+M.bkDelTop+'" style="font-size:13px;color:var(--sub);margin-bottom:14px;"></div>' +
            '<div id="'+M.bkDelMsg+'" style="font-size:13px;color:var(--error);margin-bottom:10px;display:none;"></div>' +
            '<div style="display:flex;gap:10px;">' +
              '<button class="btn btn-primary" style="flex:1;background:var(--error);" data-rt="bkdelconfirm">Delete All</button>' +
              '<button class="btn btn-ghost" style="flex:1;" data-rt="bkdelclose">Cancel</button>' +
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
              '<select id="'+M.bkField+'" style="font-size:14px;padding:6px 8px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);width:100%;">' +
                '<option value="">— select field —</option>' +
              '</select>' +
            '</div>' +
            '<div class="field-group" style="margin-bottom:10px;">' +
              '<label style="font-size:12px;">New value</label>' +
              '<div id="'+M.bkValContainer+'"></div>' +
            '</div>' +
            '<div id="'+M.bkPrev+'" style="font-size:12px;color:var(--sub);font-family:monospace;background:var(--bg);padding:8px;border-radius:6px;margin-bottom:12px;display:none;"></div>' +
            '<div id="'+M.bkSetMsg+'" style="font-size:13px;color:var(--error);margin-bottom:10px;display:none;"></div>' +
            '<div style="display:flex;gap:10px;">' +
              '<button class="btn btn-primary" style="flex:1;" data-rt="bksetconfirm">Apply</button>' +
              '<button class="btn btn-ghost" style="flex:1;" data-rt="bksetclose">Cancel</button>' +
            '</div>' +
          '</div>' +
        '</div>';
    }

    if (quickEdit) {
      html +=
        '<div id="'+M.quickEdit+'" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:950;align-items:center;justify-content:center;padding:12px;">' +
          '<div style="position:relative;width:min(980px,100%);height:min(92vh,900px);background:var(--card);border-radius:12px;overflow:hidden;box-shadow:0 8px 36px rgba(0,0,0,.3);">' +
            '<button type="button" class="btn btn-ghost btn-sm" data-rt="quickclose" style="position:absolute;right:8px;top:8px;z-index:2;">Close</button>' +
            '<iframe id="'+M.quickFrame+'" title="Edit record" style="width:100%;height:100%;border:0;background:var(--bg);"></iframe>' +
          '</div>' +
        '</div>';
    }

    var wrap = document.createElement("div");
    wrap.id = M.wrap;
    wrap.innerHTML = html;
    document.body.appendChild(wrap);

    if (quickEdit) {
      var quickModal = ge(M.quickEdit);
      var quickFrame = ge(M.quickFrame);
      quickFrame.addEventListener("load", function () {
        try {
          if (quickModal.style.display !== "flex") return;
          if (quickFrame.contentWindow.location.pathname !== "/edit") {
            quickModal.style.display = "none";
            quickFrame.src = "about:blank";
            onRefresh();
          }
        } catch (e) {}
      });
      quickModal.addEventListener("click", function (e) {
        if (e.target === quickModal) _closeQuickEdit();
      });
    }

    _wire();
  }

  function _openQuickEdit(row) {
    if (!quickEdit || !row || !row._filepath || !row._line) return;
    var modal = ge(M.quickEdit);
    var frame = ge(M.quickFrame);
    if (!modal || !frame) return;
    var qs = new URLSearchParams({
      filepath: row._filepath,
      lineno: row._lineno == null ? "" : String(row._lineno),
      line: row._line,
      return_to: opts.returnTo || window.location.pathname,
      quick_edit: "1"
    });
    modal.style.display = "flex";
    frame.src = "/edit?" + qs.toString();
  }

  function _closeQuickEdit() {
    var modal = ge(M.quickEdit);
    var frame = ge(M.quickFrame);
    if (modal) modal.style.display = "none";
    if (frame) frame.src = "about:blank";
  }

  // ── summary bar ────────────────────────────────────────────────────────────
  function _summaryBar(d) {
    var p = [];
    if (d.count !== undefined) p.push("<span>"+esc(d.count)+" records</span>");
    if (d.total_fmt) p.push("<span>Total: <strong>"+esc(d.total_fmt)+"</strong></span>");
    if (d.avg_fmt)   p.push("<span>Avg: <strong>"+esc(d.avg_fmt)+"</strong></span>");
    if (d.time_label) p.push('<span style="color:var(--sub)">'+esc(d.time_label)+"</span>");
    return p.length
      ? '<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--sub);">'+p.join("")+"</div>"
      : "";
  }

  // ── pagination helper ──────────────────────────────────────────────────────
  function _pageSlice(recs) {
    if (_records.length <= _pageSize) return recs;
    var start = (_page - 1) * _pageSize;
    return recs.slice(start, start + _pageSize);
  }

  function _totalPages() {
    return Math.ceil(_records.length / _pageSize);
  }

  function _updatePagination() {
    var pag = ge(M.pagination);
    if (!pag) return;
    var tp = _totalPages();
    if (tp <= 1) { pag.innerHTML = ""; return; }
    var start = (_page - 1) * _pageSize + 1;
    var end = Math.min(_page * _pageSize, _records.length);
    pag.innerHTML =
      '<div style="display:flex;align-items:center;gap:8px;font-size:13px;color:var(--sub);">' +
        '<button class="btn btn-ghost btn-sm" data-rt="prev" ' + (_page <= 1 ? 'disabled' : '') + '>← Prev</button>' +
        '<span>' + start + '–' + end + ' of ' + _records.length + '</span>' +
        '<button class="btn btn-ghost btn-sm" data-rt="next" ' + (_page >= tp ? 'disabled' : '') + '>Next →</button>' +
      '</div>';
  }

  // ── row builder ────────────────────────────────────────────────────────────
  function _buildRows(recs, cols, returnTo, globalOffset) {
    var offset = globalOffset || 0;
    return recs.map(function(r, idx) {
      var globalIdx = offset + idx;
      var cells = cols.map(function(c) {
        var k = Object.keys(r).find(function(k){ return k.toLowerCase()===c.toLowerCase(); }) || c;
        return "<td>"+esc(r[k]||"")+"</td>";
      }).join("");

      var cb = "";
      if (enableBulk) {
        cb = r._line
          ? '<td style="text-align:center;width:32px;"><input type="checkbox" class="rt-row-cb" data-idx="'+globalIdx+'"></td>'
          : '<td style="width:32px;"></td>';
      }

      var quickAction = quickEdit
        ? '<button type="button" class="btn btn-ghost btn-sm" style="padding:2px 8px;font-size:12px;" data-rt="quickedit" data-row="'+encodeURIComponent(JSON.stringify(r))+'" title="Quick edit">Edit in dialog</button> '
        : "";
      var acts = r._line
        ? '<td style="white-space:nowrap;">' +
          quickAction +
          '<a class="btn btn-ghost btn-sm" style="padding:2px 8px;font-size:12px;" href="/edit?filepath='+encodeURIComponent(r._filepath)+'&lineno='+r._lineno+'&line='+encodeURIComponent(r._line)+'&return_to='+encodeURIComponent(returnTo)+'" title="Edit">✎</a> ' +
          '<a class="btn btn-ghost btn-sm" style="padding:2px 8px;font-size:12px;color:var(--warn);" href="/edit?convert=1&filepath='+encodeURIComponent(r._filepath)+'&lineno='+r._lineno+'&line='+encodeURIComponent(r._line)+'&return_to='+encodeURIComponent(returnTo)+'" title="Convert to another type">⇄</a> ' +
          '<button class="btn btn-ghost btn-sm" style="padding:2px 8px;font-size:12px;color:var(--error);" data-rt="opendel" data-row=\''+JSON.stringify(r).replace(/'/g,"&#39;")+'\'>✕</button>' +
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

  function _container() { return opts.container || ge(cid); }

  // ══ PUBLIC ═════════════════════════════════════════════════════════════════

  self.render = function(d) {
    var container = _container();
    if (!container) return;

    _injectModals();
    _wire();

    if (!d || !d.records || !d.records.length) {
      container.innerHTML = '<div class="card" style="color:var(--sub);text-align:center;padding:32px;">No records found.</div>';
      return;
    }

    _records  = d.records.slice();
    _cols     = (d.columns || []).filter(function(c){ return c.charAt(0) !== "_"; });
    _selected = [];
    _sortCol  = null;
    _sortAsc  = true;
    _page     = 1;
    _updateBar();

    var returnTo = opts.returnTo || window.location.pathname;
    var pageRecs = _pageSlice(_records);

    var cbHead = enableBulk
      ? '<th style="width:32px;text-align:center;"><input type="checkbox" id="'+M.selectAll+'" data-rt="selall" title="Select all"></th>'
      : '';

    var heads = cbHead +
      _cols.map(function(c){
        return '<th class="sortable" data-col="'+esc(c)+'" style="cursor:pointer;">'+esc(c)+'</th>';
      }).join("") +
      '<th style="width:80px;"></th>';

    container.innerHTML =
      '<div class="card">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:10px;">' +
          _summaryBar(d) +
          '<button class="btn btn-ghost btn-sm" data-rt="export">↓ CSV</button>' +
        '</div>' +
        '<div id="'+M.pagination+'"></div>' +
        '<div style="overflow-x:auto;">' +
          '<table class="data-table" id="'+M.table+'">' +
            '<thead><tr>'+heads+'</tr></thead>' +
            '<tbody id="'+M.tbody+'">'+_buildRows(pageRecs, _cols, returnTo, (_page-1)*_pageSize)+'</tbody>' +
          '</table>' +
        '</div>' +
      '</div>';

    _updatePagination();
  };

  self.clear = function() {
    var container = _container();
    if (container) container.innerHTML = "";
    _records = []; _cols = []; _selected = [];
    _updateBar();
  };

  self.destroy = function() {
    self.clear();
    var wrap = ge(M.wrap);
    if (wrap && wrap.parentElement) wrap.parentElement.removeChild(wrap);
  };

  // ── sorting ────────────────────────────────────────────────────────────────
  self._sort = function(th, col) {
    if (_sortCol === col) { _sortAsc = !_sortAsc; }
    else { _sortCol = col; _sortAsc = true; }

    var container = _container();
    if (container) {
      container.querySelectorAll("th.sortable").forEach(function(h){
        h.classList.remove("sort-asc","sort-desc");
      });
    }
    if (th) th.classList.add(_sortAsc ? "sort-asc" : "sort-desc");

    var cl = col.toLowerCase(), asc = _sortAsc;
    _records.sort(function(a, b){
      var ak = Object.keys(a).find(function(k){ return k.toLowerCase()===cl; }) || col;
      var bk = Object.keys(b).find(function(k){ return k.toLowerCase()===cl; }) || col;
      return _cmp(a[ak], b[bk], asc);
    });

    _page = 1;
    _selected = [];
    var sa = ge(M.selectAll);
    if (sa) sa.checked = false;
    _updateBar();

    var tbody = ge(M.tbody);
    if (tbody) tbody.innerHTML = _buildRows(_pageSlice(_records), _cols, opts.returnTo || window.location.pathname, (_page-1)*_pageSize);
    _updatePagination();
  };

  // ── CSV export ─────────────────────────────────────────────────────────────
  self._export = function() {
    if (!_records.length) return;
    var q = function(v) {
      return '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"';
    };
    var lines = [_cols.map(q).join(",")];
    _records.forEach(function(r) {
      lines.push(_cols.map(function(c) {
        var k = Object.keys(r).find(function(k){ return k.toLowerCase()===c.toLowerCase(); }) || c;
        return q(r[k]);
      }).join(","));
    });
    var blob = new Blob([lines.join("\n")], { type: "text/csv" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = exportName + ".csv";
    a.click();
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
    var container = _container();
    if (container) {
      container.querySelectorAll(".rt-row-cb").forEach(function(box){
        box.checked = cb.checked;
        if (cb.checked) _selected.push(parseInt(box.dataset.idx));
      });
    }
    _updateBar();
  };

  self._bkClear = function() {
    _selected = [];
    var container = _container();
    if (container) {
      container.querySelectorAll(".rt-row-cb").forEach(function(b){ b.checked = false; });
    }
    var sa = ge(M.selectAll);
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
  function _getBkFieldType() {
    var f = ge(M.bkField).value.trim();
    if (!f || !_fieldTypes[f]) return "text";
    var ft = _fieldTypes[f];
    if (ft.is_date)     return "date";
    if (ft.is_month)    return "month";
    if (ft.is_datetime) return "datetime-local";
    if (ft.is_int)      return "number";
    return "text";
  }

  function _renderBkValueInput(val) {
    var t = _getBkFieldType();
    var id = M.bkValInput;
    var attrs = 'id="'+id+'" data-rt="bkval" style="font-size:14px;padding:6px 8px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);width:100%;box-sizing:border-box;"';
    if (t === "date" || t === "month" || t === "datetime-local") {
      return '<input type="'+t+'" '+attrs+' value="'+esc(val)+'">';
    }
    if (t === "number") {
      return '<input type="number" '+attrs+' value="'+esc(val)+'">';
    }
    return '<input type="text" '+attrs+' placeholder="new value" value="'+esc(val)+'">';
  }

  self._bkFieldChange = function() {
    ge(M.bkValContainer).innerHTML = _renderBkValueInput("");
    ge(M.bkPrev).style.display = "none";
  };

  self._bkSetOpen = function() {
    if (!_selected.length) return;
    var sel = ge(M.bkField);
    sel.innerHTML = '<option value="">— select field —</option>';
    _cols.forEach(function(c) {
      sel.innerHTML += '<option value="'+esc(c)+'">'+esc(c)+'</option>';
    });
    ge(M.bkValContainer).innerHTML = _renderBkValueInput("");
    ge(M.bkPrev).style.display = "none";
    ge(M.bkSetMsg).style.display = "none";
    ge(M.bkSet).style.display = "flex";
    setTimeout(function(){ ge(M.bkField).focus(); }, 50);
  };

  self._bkSetClose = function() { ge(M.bkSet).style.display = "none"; };

  self._bkPrev = function() {
    var f = ge(M.bkField).value.trim(), v = ge(M.bkValInput).value.trim();
    var p = ge(M.bkPrev);
    if (f && v) {
      p.textContent = "Will apply: "+f+"="+v+" to "+_selected.length+" record"+(_selected.length>1?"s":"");
      p.style.display = "block";
    } else { p.style.display = "none"; };
  };

  self._bkSetConfirm = function() {
    var field = ge(M.bkField).value.trim(), value = ge(M.bkValInput).value.trim();
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

  // ── pagination ─────────────────────────────────────────────────────────────
  self._prevPage = function() {
    if (_page <= 1) return;
    _page--;
    _refreshPage();
  };

  self._nextPage = function() {
    if (_page >= _totalPages()) return;
    _page++;
    _refreshPage();
  };

  function _refreshPage() {
    _selected = [];
    var sa = ge(M.selectAll);
    if (sa) sa.checked = false;
    _updateBar();
    var tbody = ge(M.tbody);
    if (tbody) tbody.innerHTML = _buildRows(_pageSlice(_records), _cols, opts.returnTo || window.location.pathname, (_page-1)*_pageSize);
    _updatePagination();
  }
}
