(function () {
  "use strict";

  var _fpLineNo = null, _fpField = "", _fpExpect = "";
  var _refreshFn = null;

  function positionPopup(popup, el) {
    popup.classList.remove("open");
    var rect = el.getBoundingClientRect();
    popup.style.top = (rect.bottom + 4) + "px";
    popup.style.left = Math.min(rect.left, window.innerWidth - 220) + "px";
    popup.classList.add("open");
  }

  function popupEditPriority(lineNo, currentPri, el, refreshFn) {
    _fpLineNo = lineNo;
    _fpField = "priority";
    _fpExpect = el.getAttribute ? (el.getAttribute("data-raw") || "") : "";
    _refreshFn = refreshFn || null;
    var popup = document.getElementById("field-popup");
    if (!popup) return;
    var opts = ["A", "B", "C", "D", ""];
    var defaultLabels = { A: "Critical", B: "Important", C: "Moderate", D: "Low" };
    var labels = [];
    for (var i = 0; i < opts.length; i++) {
      if (opts[i] === "") { labels.push("None"); continue; }
      var lbl = (window.PTOS && window.PTOS.priorityLabels && window.PTOS.priorityLabels[opts[i]]) ||
                defaultLabels[opts[i]] || opts[i];
      labels.push(opts[i] + " \u2014 " + lbl);
    }
    var html = '<div class="fp-label">Priority</div><div class="fp-row">';
    for (var i = 0; i < opts.length; i++) {
      var cls = "fp-chip";
      if (opts[i] === currentPri) cls += " active";
      html += '<div class="' + cls + '" onclick="PtosTodoPopups.pickFieldPriority(\'' + opts[i] + '\')">' + labels[i] + '</div>';
    }
    html += "</div>";
    popup.innerHTML = html;
    positionPopup(popup, el);
  }

  function pickFieldPriority(value) {
    _doEdit({ priority: value });
  }

  function popupEditRec(lineNo, currentRec, el, refreshFn) {
    _fpLineNo = lineNo;
    _fpField = "rec";
    _fpExpect = el.getAttribute ? (el.getAttribute("data-raw") || "") : "";
    _refreshFn = refreshFn || null;
    var popup = document.getElementById("field-popup");
    if (!popup) return;
    var opts = ["1d", "1w", "2w", "1m", "2m", "3m", "1y", "+1m", "+1w", "+1y"];
    var labels = ["Daily", "Weekly", "Biweekly", "Monthly", "Bimonthly", "Quarterly", "Yearly", "Strict Monthly", "Strict Weekly", "Strict Yearly"];
    var html = '<div class="fp-label">Recurrence</div><div class="fp-row">';
    for (var i = 0; i < opts.length; i++) {
      var cls = "fp-chip";
      if (opts[i] === currentRec) cls += " active";
      html += '<div class="' + cls + '" onclick="PtosTodoPopups.pickFieldRec(\'' + opts[i] + '\')">' + labels[i] + '</div>';
    }
    html += '<div class="fp-chip clear" onclick="PtosTodoPopups.pickFieldRec(\'\')">Clear</div>';
    html += "</div>";
    popup.innerHTML = html;
    positionPopup(popup, el);
  }

  function pickFieldRec(value) {
    _doEdit({ rec: value });
  }

  function closeFieldPopup() {
    var popup = document.getElementById("field-popup");
    if (popup) popup.classList.remove("open");
  }

  function _doEdit(updates) {
    closeFieldPopup();
    fetch("/todo/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ line_no: _fpLineNo, updates: updates, expect: _fpExpect })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (d && d.ok) {
        if (typeof _refreshFn === "function") _refreshFn();
        else window.location.reload();
      } else {
        alert((d && d.error) || "Failed");
      }
    }).catch(function () { window.location.reload(); });
  }

  function popupEditDate(lineNo, field, currentValue, el, refreshFn) {
    _fpLineNo = lineNo;
    _fpField = field;
    _fpExpect = el.getAttribute ? (el.getAttribute("data-raw") || "") : "";
    _refreshFn = refreshFn || null;
    var popup = document.getElementById("field-popup");
    if (!popup) return;
    var opts = ["today", "tomorrow", "this_week", "next_week", "this_month", "next_month"];
    var labels = ["Today", "Tomorrow", "This week", "Next week", "This month", "Next month"];
    var html = '<div class="fp-label">' + (field === "due" ? "Due date" : "Threshold date") + '</div><div class="fp-row">';
    for (var i = 0; i < opts.length; i++) {
      html += '<div class="fp-chip" onclick="PtosTodoPopups.pickFieldDate(\'' + opts[i] + '\')">' + labels[i] + '</div>';
    }
    if (field === "threshold") {
      html += '<div class="fp-chip" onclick="PtosTodoPopups.pickFieldThresholdNow()">Now</div>';
    }
    html += '<div class="fp-chip pick-date" onclick="PtosTodoPopups.pickFieldCustomDateTime()">Pick date...</div>';
    html += '<div class="fp-chip clear" onclick="PtosTodoPopups.pickFieldDate(\'\')">Clear</div>';
    html += "</div>";
    popup.innerHTML = html;
    positionPopup(popup, el);
  }

  function pickFieldDate(value) {
    var updates = {};
    updates[_fpField] = value;
    _doEdit(updates);
  }

  function pickFieldThresholdNow() {
    var now = new Date();
    var val = now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0") + "-" +
      String(now.getDate()).padStart(2, "0") + "T" + String(now.getHours()).padStart(2, "0") + ":" +
      String(now.getMinutes()).padStart(2, "0");
    _doEdit({ threshold: val });
  }

  function pickFieldCustomDateTime() {
    closeFieldPopup();
    if (typeof openDTPicker === "function") {
      openDTPicker({ callback: function (iso) { pickFieldDate(iso); } });
    }
  }

  function toggleChipSection(id, bar) {
    var el = document.getElementById(id);
    if (!el) return;
    var arrow = bar ? bar.querySelector(".chip-toggle-arrow") : null;
    var isOpen = el.classList.toggle("open");
    if (bar) bar.classList.toggle("open", isOpen);
    el.style.display = isOpen ? "grid" : "none";
    if (arrow) arrow.style.transform = isOpen ? "rotate(90deg)" : "";
  }

  function _addInput() {
    return document.getElementById("todo-shell-add-input") ||
           document.querySelector("[data-todo-add-input]");
  }

  function toggleAddChip(chip, group) {
    var input = _addInput();
    if (!input) return;
    var text = input.value;
    var token = (chip.getAttribute("data-token") || "").trim() + " ";
    var bare = token.trim();

    if (group === "pri") {
      document.querySelectorAll("#add-chips .pri-chip").forEach(function (c) {
        var t = (c.getAttribute("data-token") || "").trim();
        text = text.replace(new RegExp("\\(" + t + "\\)" + "\\s*"), "");
      });
      if (text.indexOf(bare) === -1) text = token + text;
    } else if (group === "due" || group === "threshold") {
      var prefix = group === "threshold" ? "t:" : "due:";
      text = text.replace(new RegExp(prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\S*\\s*", "gi"), "");
      text = text.trimEnd() + " " + token;
    } else if (group === "rec") {
      text = text.replace(/rec:\\S+\\s*/gi, "");
      text = text.trimEnd() + " " + token;
    } else if (text.indexOf(bare) !== -1) {
      text = text.replace(new RegExp(bare.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*"), "");
    } else {
      text = text.trimEnd() + " " + token;
    }

    input.value = text.replace(/^\s+/, "");
    chip.classList.toggle("selected");
    input.focus();
  }

  var _pickerPrefix = "";
  function pickAddDate(prefix) {
    _pickerPrefix = prefix + ":";
    var input = _addInput();
    if (!input) return;
    closeFieldPopup();
    if (typeof openDTPicker === "function") {
      openDTPicker({ callback: function (iso) {
        if (!_pickerPrefix) return;
        var text = input.value;
        text = text.replace(new RegExp(_pickerPrefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\S*\\s*"), "");
        text = text.trimEnd() + " " + _pickerPrefix + iso + " ";
        input.value = text.replace(/^\s+/, "");
        input.focus();
        _pickerPrefix = "";
      }});
    }
  }

  function expandChipGroup(btn) {
    var row = btn ? btn.closest(".chip-row") : null;
    if (row) row.querySelectorAll(".ac-extra").forEach(function (c) { c.style.display = "inline-flex"; });
    if (btn) btn.classList.add("expanded");
  }
  function _wireQuickPick() {
    var input = _addInput();
    var chips = document.getElementById("add-chips");
    if (!input || !chips) return;
    var timer = null;
    input.addEventListener("focus", function () {
      if (timer) { clearTimeout(timer); timer = null; }
      chips.style.display = "grid";
    });
    input.addEventListener("blur", function () {
      timer = setTimeout(function () {
        if (document.activeElement && chips.contains(document.activeElement)) return;
        chips.style.display = "none";
      }, 200);
    });
    chips.addEventListener("mousedown", function (e) {
      // Prevent blur from firing when clicking chips
      e.preventDefault();
    });
  }

  // Wire up after toolbar renders (poll for the input element)
  var _qpAttempts = 0;
  function _tryWire() {
    var input = _addInput();
    var chips = document.getElementById("add-chips");
    if (input && chips) {
      _wireQuickPick();
    } else if (_qpAttempts < 50) {
      _qpAttempts++;
      setTimeout(_tryWire, 100);
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { setTimeout(_tryWire, 200); });
  } else {
    setTimeout(_tryWire, 200);
  }

  window.PtosTodoPopups = {
    popupEditDate: popupEditDate,
    toggleChipSection: toggleChipSection,
    toggleAddChip: toggleAddChip,
    pickAddDate: pickAddDate,
    expandChipGroup: expandChipGroup,
    popupEditRec: popupEditRec,
    pickFieldRec: pickFieldRec,
    popupEditPriority: popupEditPriority,
    pickFieldPriority: pickFieldPriority,
    pickFieldDate: pickFieldDate,
    pickFieldThresholdNow: pickFieldThresholdNow,
    pickFieldCustomDateTime: pickFieldCustomDateTime,
    closeFieldPopup: closeFieldPopup,
    setRefresh: function (fn) { _refreshFn = fn; }
  };
  // Close popup when clicking outside
  document.addEventListener("click", function (e) {
    var popup = document.getElementById("field-popup");
    if (!popup || !popup.classList.contains("open")) return;
    if (popup.contains(e.target)) return;
    if (e.target && e.target.closest && e.target.closest(".todo-due-badge, .todo-pri, .todo-rec-badge, .todo-thr-badge")) return;
    closeFieldPopup();
  });

  // Global aliases for inline onclick handlers
  window.toggleChipSection = function(id, bar) {
    if (window.PtosTodoPopups && window.PtosTodoPopups.toggleChipSection) {
      window.PtosTodoPopups.toggleChipSection(id, bar);
    }
  };
  window.toggleAddChip = function(chip, group) {
    if (window.PtosTodoPopups && window.PtosTodoPopups.toggleAddChip) {
      window.PtosTodoPopups.toggleAddChip(chip, group);
    }
  };
  window.pickAddDate = function(prefix) {
    if (window.PtosTodoPopups && window.PtosTodoPopups.pickAddDate) {
      window.PtosTodoPopups.pickAddDate(prefix);
    }
  };
  window.expandChipGroup = function(btn) {
    if (window.PtosTodoPopups && window.PtosTodoPopups.expandChipGroup) {
      window.PtosTodoPopups.expandChipGroup(btn);
    }
  };
})();

