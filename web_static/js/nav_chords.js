
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
  // Shortcut map is provided by the server via window.PTOS.keys
  // Falls back to empty object if not present
  var KEYS = (window.PTOS && window.PTOS.keys) || {};

  // Key state
  var _g = false, _gTimer = null;

  window.closeKbHelp = function() {
    var el = document.getElementById("kb-overlay");
    if (el) el.style.display = "none";
  };

  function openKbHelp() {
    var el = document.getElementById("kb-overlay");
    if (el) el.style.display = "flex";
  }

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
      var chord = "g" + key;
      if (KEYS[chord]) {
        e.preventDefault();
        var path = KEYS[chord];
        if (path !== "focus_search" && path !== "show_help" && path !== "close_overlay") {
          window.location = path;
        }
      }
      return;
    }

    // Single-key shortcuts
    if (KEYS[key]) {
      var path = KEYS[key];
      if (path !== "focus_search" && path !== "show_help" && path !== "close_overlay") {
        e.preventDefault();
        window.location = path;
        return;
      }
      // Special handlers for non-navigation keys
      if (path === "focus_search") {
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
      if (path === "show_help") {
        e.preventDefault();
        openKbHelp();
        return;
      }
      if (path === "close_overlay") {
        closeKbHelp();
        return;
      }
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
    document.body.innerHTML = "<div style='position:fixed;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column;background:#1a1a1a;color:#fff;font-family: var(--font-ui);'><h1 style='font-size:32px;margin-bottom:12px;'>Server stopped</h1><p style='font-size:18px;opacity:.7;'>You can close this tab.</p></div>";
    fetch("/shutdown").then(() => window.close());
  }
}
}
