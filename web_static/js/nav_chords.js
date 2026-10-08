
// ── Editable Options ────────────────────────────────────────────────────────────────
let pendingOption = null;

function getFieldInfo(fieldName) {
    const allFields = window.field_defs || [];
    return allFields.find(f => f.name === fieldName) || {};
}

// ── Generic Table Column Sort ─────────────────────────────────────────────────────
function initTableSort(tableId, colsKey, recordsKey) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const thead = table.querySelector("thead");
    if (!thead) return;
    const headers = thead.querySelectorAll("th");
    headers.forEach((th, idx) => {
        if (idx >= (colsKey ? window[colsKey]?.length || 0 : 0)) return;
        th.classList.add("sortable");
        th.addEventListener("click", () => {
            const col = colsKey ? window[colsKey][idx] : th.textContent.trim();
            genericSortTable(tableId, colsKey, recordsKey, th, col);
        });
    });
}

function genericSortTable(tableId, colsKey, recordsKey, th, col) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const tbody = table.querySelector("tbody");
    if (!tbody) return;
    
    // toggle direction if same column, otherwise reset to asc
    const stored = window._sortState = window._sortState || {};
    if (stored.col === col) {
        stored.asc = !stored.asc;
    } else {
        stored.col = col;
        stored.asc = true;
    }
    
    // update header styles
    table.querySelectorAll("th.sortable").forEach(h => h.classList.remove("sort-asc","sort-desc"));
    th.classList.add(stored.asc ? "sort-asc" : "sort-desc");
    
    // get records
    const records = recordsKey ? window[recordsKey] : null;
    if (!records) return;
    
    // sort
    const colLower = col.toLowerCase();
    const sorted = [...records].sort((a, b) => {
        const ak = Object.keys(a).find(k => k.toLowerCase() === colLower) || col;
        const bk = Object.keys(b).find(k => k.toLowerCase() === colLower) || col;
        let va = a[ak] || "", vb = b[bk] || "";
        const na = parseFloat(va), nb = parseFloat(vb);
        if (!isNaN(na) && !isNaN(nb)) return stored.asc ? na - nb : nb - na;
        if (/^\d{4}-\d{2}-\d{2}/.test(va) && /^\d{4}-\d{2}-\d{2}/.test(vb)) {
            return stored.asc ? va.localeCompare(vb) : vb.localeCompare(va);
        }
        return stored.asc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
    });
    
    // rebuild tbody
    const cols = colsKey ? window[colsKey] : Object.keys(records[0] || {});
    tbody.innerHTML = sorted.map(r => {
        const cells = cols.map(c => {
            const rk = Object.keys(r).find(k => k.toLowerCase() === c.toLowerCase()) || c;
            return `<td>${r[rk] || ""}</td>`;
        }).join("");
const acts = r._line ? `<td style="white-space:nowrap;">
            <a class="btn btn-ghost btn-sm" style="padding:2px 8px;font-size:12px;"
              href="/edit?filepath=${encodeURIComponent(r._filepath)}&lineno=${r._lineno}&line=${encodeURIComponent(r._line)}&return_to=${encodeURIComponent(window.location.pathname)}">✎</a>
            <button class="btn btn-ghost btn-sm" style="padding:2px 8px;font-size:12px;color:var(--error);"
              data-row='${JSON.stringify(r)}' onclick="openDeleteRecord(JSON.parse(this.dataset.row))">✕</button>
          </td>` : `<td></td>`;
        return `<tr>${cells}${acts}</tr>`;
    }).join("");
    
    // update records reference
    if (recordsKey) window[recordsKey] = sorted;
}


function getFieldInfo(fieldName) {
    const allFields = window.field_defs || [];
    return allFields.find(f => f.name === fieldName) || {};
}

function addGlobalFieldOption(fieldName, selectId) {
    const newVal = prompt('Enter new option for ' + fieldName + ':');
    if (!newVal || !newVal.trim()) return;
    
    const val = newVal.trim();
    const select = document.getElementById(selectId);
    
    // Check if option already exists
    const exists = Array.from(select.options).some(o => o.value === val);
    if (exists) {
        alert('Option already exists');
        return;
    }
    
    fetch('/add-global-field-option', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({field_name: fieldName, new_option: val})
    })
    .then(r => r.json())
    .then(result => {
        if (result.success) {
            const opt = document.createElement('option');
            opt.value = val;
            opt.textContent = val;
            opt.selected = true;
            select.appendChild(opt);
        } else {
            alert('Error: ' + (result.error || 'Failed to add option'));
        }
    })
    .catch(e => alert('Error: ' + e.message));
}

function addNewOption(fieldName) {
    const newVal = prompt('Enter new option for ' + fieldName + ':');
    if (!newVal || !newVal.trim()) return;
    
    const val = newVal.trim();
    const fieldInfo = getFieldInfo(fieldName);
    const select = document.getElementById('field-' + fieldName);
    const currentOptions = fieldInfo.options || [];
    
    // Check if option already exists
    if (currentOptions.includes(val)) {
        alert('Option already exists');
        return;
    }
    
    // For parent-dependent, need parent value
    if (fieldInfo.option_source === 'parent_dependent') {
        const parentField = fieldInfo.parent;
        const parentSelect = document.querySelector(`[name="${parentField}"]`);
        const parentVal = parentSelect?.value;
        if (!parentVal) {
            alert('Please select ' + parentField + ' first');
            return;
        }
        pendingOption = {
            select: select,
            fieldInfo: fieldInfo,
            value: val,
            parentValue: parentVal
        };
        document.getElementById('add-option-value').textContent = val;
        document.getElementById('add-option-field').textContent = fieldName;
        document.getElementById('add-option-parent-msg').style.display = 'block';
        document.getElementById('add-option-parent-key').textContent = parentField + '=' + parentVal;
        document.getElementById('add-option-modal').style.display = 'flex';
        return;
    }
    
    pendingOption = {
        select: select,
        fieldInfo: fieldInfo,
        value: val,
        parentValue: null
    };
    document.getElementById('add-option-value').textContent = val;
    document.getElementById('add-option-field').textContent = fieldName;
    document.getElementById('add-option-parent-msg').style.display = 'none';
    document.getElementById('add-option-modal').style.display = 'flex';
}

function closeAddOptionModal() {
    document.getElementById('add-option-modal').style.display = 'none';
    pendingOption = null;
}

async function confirmAddOption() {
    if (!pendingOption) return;
    
    const { select, fieldInfo, value, parentValue } = pendingOption;
    const typeName = fieldInfo.type_name || new URLSearchParams(window.location.search).get('type');
    
    const payload = {
        type_name: typeName,
        field_name: fieldInfo.name,
        new_option: value,
        option_source: fieldInfo.option_source,
        parent_field: fieldInfo.parent,
        parent_value: parentValue,
        shared_key: fieldInfo.shared_key || ''
    };
    
    try {
        const resp = await fetch('/add-field-option', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const result = await resp.json();
        if (result.success) {
            const opt = document.createElement('option');
            opt.value = value;
            opt.textContent = value;
            opt.selected = true;
            select.appendChild(opt);
        } else {
            alert('Error: ' + (result.error || 'Failed to add option'));
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
    
    closeAddOptionModal();
}

function toggleMoreMenu(e) {
  if (e) e.preventDefault();
  var menu = document.getElementById("more-menu");
  menu.style.display = menu.style.display === "none" ? "flex" : "none";
}

// ── Keyboard Shortcuts ────────────────────────────────────────────────────────
(function() {
  // Navigation shortcuts
  var NAV = {
    "g h": "/",
    "g a": "/add",
    "g b": "/browse",
    "g q": "/queries",
    "g j": "/journal",
    "g n": "/notes",
    "g d": "/due",
    "g t": "/todo",
    "g e": "/editor",
    "g l": "/lint",
    "g s": "/settings",
    "g k": "/backup",
    "g c": "/schema-builder",
    "g u": "/query-builder",
    "g o": "/board",
    "g m": "/habits",
    "g y": "/calendar",
    "g r": "/thresholds",
    "g v": "/entity",
  };

  // Help overlay HTML
  var HELP_HTML = `
  <div id="kb-overlay"
       onclick="if(event.target===this)closeKbHelp()"
       style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);
              z-index:9999;align-items:center;justify-content:center;">
    <div style="background:var(--card);border-radius:14px;padding:24px 28px;
              max-width:520px;width:92%;max-height:85vh;overflow-y:auto;
              border:1px solid var(--border);">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;">
        <div style="font-size:17px;font-weight:800;color:var(--text);">Keyboard Shortcuts</div>
        <button onclick="closeKbHelp()"
                style="background:none;border:none;font-size:20px;color:var(--sub);cursor:pointer;padding:0 4px;">✕</button>
      </div>

      <div style="font-size:12px;font-weight:700;color:var(--sub);
                  text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px;">Quick Navigation</div>
      <table class="data-table" style="margin-bottom:12px;width:100%;">
        <thead><tr><th style="width:140px;">Key</th><th>Page</th></tr></thead>
        <tbody>
          <tr><td><kbd>H</kbd></td><td>Home</td></tr>
          <tr><td><kbd>A</kbd></td><td>Add Record</td></tr>
          <tr><td><kbd>T</kbd></td><td>Todo</td></tr>
          <tr><td><kbd>J</kbd></td><td>Journal</td></tr>
          <tr><td><kbd>N</kbd></td><td>Notes</td></tr>
          <tr><td><kbd>F</kbd></td><td>Search</td></tr>
          <tr><td><kbd>R</kbd></td><td>Routines</td></tr>
          <tr><td><kbd>Y</kbd></td><td>Record Types</td></tr>
          <tr><td><kbd>B</kbd></td><td>Browse</td></tr>
          <tr><td><kbd>Q</kbd></td><td>Queries</td></tr>
          <tr><td><kbd>S</kbd></td><td>Settings</td></tr>
          <tr><td><kbd>E</kbd></td><td>Add expense</td></tr>
          <tr><td><kbd>I</kbd></td><td>Add income</td></tr>
          <tr><td><kbd>/</kbd></td><td>Focus search</td></tr>
          <tr><td><kbd>?</kbd></td><td>Show this help</td></tr>
          <tr><td><kbd>Esc</kbd></td><td>Close overlay / cancel</td></tr>
        </tbody>
      </table>

      <div style="font-size:12px;font-weight:700;color:var(--sub);
                  text-transform:uppercase;letter-spacing:.6px;margin:16px 0 10px;">Extended Navigation</div>
      <table class="data-table" style="width:100%;">
        <thead><tr><th style="width:140px;"><kbd>G</kbd> then…</th><th>Page</th></tr></thead>
        <tbody>
          <tr><td><kbd>D</kbd></td><td>Due List</td></tr>
          <tr><td><kbd>O</kbd></td><td>Board</td></tr>
          <tr><td><kbd>M</kbd></td><td>Habits</td></tr>
          <tr><td><kbd>Y</kbd></td><td>Calendar</td></tr>
          <tr><td><kbd>R</kbd></td><td>Thresholds</td></tr>
          <tr><td><kbd>V</kbd></td><td>Entity</td></tr>
          <tr><td><kbd>U</kbd></td><td>Query Builder</td></tr>
          <tr><td><kbd>C</kbd></td><td>Schema Builder</td></tr>
          <tr><td><kbd>E</kbd></td><td>Log Editor</td></tr>
          <tr><td><kbd>L</kbd></td><td>Lint</td></tr>
          <tr><td><kbd>K</kbd></td><td>Backup</td></tr>
        </tbody>
      </table>
    </div>
  </div>
  <style>
  #kb-overlay kbd {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 26px;
    padding: 3px 7px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 5px;
    font-size: 12px;
    font-family: monospace;
    font-weight: 700;
    color: var(--text);
    line-height: 1.4;
    box-shadow: 0 1px 0 var(--border);
    margin-right: 2px;
  }
  #kb-overlay td:first-child {
    white-space: nowrap;
  }
  </style>
  `;

  // Inject overlay once
  document.addEventListener("DOMContentLoaded", function() {
    var div = document.createElement("div");
    div.innerHTML = HELP_HTML;
    document.body.appendChild(div.firstElementChild);
    // Ensure overlay is hidden on load
    var el = document.getElementById("kb-overlay");
    if (el) el.style.display = "none";
  });

  window.closeKbHelp = function() {
    var el = document.getElementById("kb-overlay");
    if (el) el.style.display = "none";
  };

  function openKbHelp() {
    var el = document.getElementById("kb-overlay");
    if (el) el.style.display = "flex";
  }

  // Key state
  var _g = false, _gTimer = null;

  document.addEventListener("keydown", function(e) {
    // Ignore when typing in inputs, textareas, selects
    var tag = document.activeElement && document.activeElement.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    // Ignore modifier combos (except our own)
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    var key = e.key.toLowerCase();

    // Escape — close overlay
    if (key === "escape") {
      closeKbHelp();
      _g = false;
      clearTimeout(_gTimer);
      return;
    }

    // ? — show help
    if (key === "?" || (e.shiftKey && e.key === "?")) {
      e.preventDefault();
      openKbHelp();
      return;
    }

    // H — go to Home
    if (key === "h" && !_g) {
      e.preventDefault();
      window.location = "/";
      return;
    }

    // A — go to Add Record
    if (key === "a" && !_g) {
      e.preventDefault();
      window.location = "/add";
      return;
    }

    // B — go to Browse
    if (key === "b" && !_g) {
      e.preventDefault();
      window.location = "/browse";
      return;
    }

    // Q — go to Queries
    if (key === "q" && !_g) {
      e.preventDefault();
      window.location = "/queries";
      return;
    }

    // J — go to Journal
    if (key === "j" && !_g) {
      e.preventDefault();
      window.location = "/journal";
      return;
    }

    // N — go to Notes
    if (key === "n" && !_g) {
      e.preventDefault();
      window.location = "/notes";
      return;
    }

    // S — go to Settings
    if (key === "s" && !_g) {
      e.preventDefault();
      window.location = "/settings";
      return;
    }

    // E — go to add expense
    if (key === "e" && !_g) {
      e.preventDefault();
      window.location = "/add?type=expense";
      return;
    }

    // I — go to add income
    if (key === "i" && !_g) {
      e.preventDefault();
      window.location = "/add?type=income";
      return;
    }

    // T — go to Todo page
    if (key === "t" && !_g) {
      e.preventDefault();
      window.location = "/todo";
      return;
    }

    // F — go to Search page
    if (key === "f" && !_g) {
      e.preventDefault();
      window.location = "/search";
      return;
    }

    // R — go to Routines page
    if (key === "r" && !_g) {
      e.preventDefault();
      window.location = "/routines";
      return;
    }

    // Y — go to Record Types page
    if (key === "y" && !_g) {
      e.preventDefault();
      window.location = "/types";
      return;
    }

    // / — focus visible search input
    if (key === "/") {
      e.preventDefault();
      var candidates = document.querySelectorAll(
        "#sidebar-search, input[name='q'], input[placeholder*='search' i], input[placeholder*='filter' i], #browse-search, #q, #b-search"
      );
      for (var i = 0; i < candidates.length; i++) {
        if (candidates[i].offsetParent !== null) {
          candidates[i].focus();
          candidates[i].select();
          break;
        }
      }
      return;
    }

    // G prefix — start two-key nav chord
    if (key === "g" && !_g) {
      _g = true;
      clearTimeout(_gTimer);
      _gTimer = setTimeout(function() { _g = false; }, 1500);
      return;
    }

    // Second key after G
    if (_g) {
      _g = false;
      clearTimeout(_gTimer);
      var chord = "g " + key;
      if (NAV[chord]) {
        e.preventDefault();
        window.location = NAV[chord];
      }
      return;
    }
  });
})();
// ── End Keyboard Shortcuts ────────────────────────────────────────────────────
if (!window.PTOS.frozen || window.PTOS.desktop) {
window.stopServer = function() {
  if (!confirm("Stop PTOS server?")) return;
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.close_app();
  } else {
    document.body.style.cssText = "display:block;margin:0;padding:0;";
    document.body.innerHTML = "<div style='position:fixed;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column;background:#1a1a1a;color:#fff;font-family:system-ui,sans-serif;'><h1 style='font-size:32px;margin-bottom:12px;'>Server stopped</h1><p style='font-size:18px;opacity:.7;'>You can close this tab.</p></div>";
    fetch("/shutdown").then(() => window.close());
  }
}
}
