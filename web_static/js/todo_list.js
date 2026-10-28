(function () {
  "use strict";

  var STORAGE_KEY = "ptos.todo.sections";

  function readState() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); }
    catch (e) { return {}; }
  }

  function writeState(state) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }
    catch (e) {}
  }

  // Select mode state
  window._selMode = false;
  window._selLines = {};
  window._selLineExpects = function () {
    var expects = {};
    Object.keys(window._selLines).forEach(function (ln) {
      var row = document.querySelector('.todo-row[data-line="' + ln + '"]');
      if (row) expects[ln] = row.getAttribute("data-raw") || "";
    });
    return expects;
  };

  function toggleSelectMode() {
    window._selMode = !window._selMode;
    var btn = document.querySelector(".todo-sel-btn");
    var bar = document.getElementById("sel-bar");
    var rows = document.querySelectorAll(".todo-row");
    if (window._selMode) {
      if (btn) { btn.textContent = "☑ Selecting"; btn.classList.add("active"); }
      if (bar) { bar.classList.add("show"); bar.style.display = "flex"; }
      var list = document.querySelector(".todo-list");
      if (list) list.classList.add("sel-mode");
      rows.forEach(function (r) { r.classList.add("sel-mode"); });
    } else {
      if (btn) { btn.textContent = "☐ Select"; btn.classList.remove("active"); }
      if (bar) { bar.classList.remove("show"); bar.style.display = "none"; }
      var list2 = document.querySelector(".todo-list");
      if (list2) list2.classList.remove("sel-mode");
      rows.forEach(function (r) {
        r.classList.remove("sel-mode");
        r.classList.remove("selected");
      });
      window._selLines = {};
      var countEl = document.getElementById("sel-count");
      if (countEl) countEl.textContent = "0 selected";
    }
  }

  function toggleRowSel(el) {
    if (!window._selMode) return;
    el.classList.toggle("selected");
    var lineNo = parseInt(el.getAttribute("data-line"), 10);
    if (el.classList.contains("selected")) {
      window._selLines[lineNo] = el.getAttribute("data-raw") || "";
    } else {
      delete window._selLines[lineNo];
    }
    var count = Object.keys(window._selLines).length;
    var countEl = document.getElementById("sel-count");
    if (countEl) countEl.textContent = count + " selected";
  }

  function openBulkEdit() {
    if (Object.keys(window._selLines).length === 0) {
      window.alert("No tasks selected");
      return;
    }
    var modalTitle = document.getElementById("todo-modal-title");
    if (modalTitle) modalTitle.textContent = "Edit " + Object.keys(window._selLines).length + " Selected Tasks";
    var lineNoEl = document.getElementById("modal-line-no");
    if (lineNoEl) lineNoEl.value = "1";
    ["modal-desc","modal-pri","modal-due","modal-due-time","modal-threshold","modal-threshold-time","modal-rec"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.value = "";
    });
    document.querySelectorAll("#modal-project-chips .modal-chip.selected, #modal-context-chips .modal-chip.selected").forEach(function (c) { c.classList.remove("selected"); });
    var projOther = document.getElementById("modal-project-other");
    var ctxOther = document.getElementById("modal-context-other");
    if (projOther) { projOther.style.display = "none"; projOther.value = ""; }
    if (ctxOther) { ctxOther.style.display = "none"; ctxOther.value = ""; }
    document.querySelectorAll(".modal-field-bulk-hide").forEach(function (f) { f.style.display = "none"; });
    var modal = document.getElementById("todo-modal");
    if (modal) modal.classList.add("open");
  }

  function mount(root) {
    var savedState = readState();
    var _usp = new URLSearchParams(window.location.search);
    var isSearching = ["search","project","context","priority","due","linked_to"].some(function (k) {
      var v = _usp.get(k);
      return v !== null && String(v).trim() !== "";
    });
    var nodes = Array.prototype.slice.call(
      root.querySelectorAll("details[data-todo-section]")
    );
    var listeners = [];
    nodes.forEach(function (node) {
      var key = node.getAttribute("data-todo-section") || "";
      if (isSearching) {
        // When searching, respect the server-rendered open state (items present => open)
        // Don't override with saved collapsed state
      } else if (Object.prototype.hasOwnProperty.call(savedState, key)) {
        node.open = !!savedState[key];
      }
      var onToggle = function () {
        savedState[key] = node.open;
        writeState(savedState);
      };
      node.addEventListener("toggle", onToggle);
      listeners.push([node, onToggle]);
    });

    return { destroy: function () {
      listeners.forEach(function (entry) {
        entry[0].removeEventListener("toggle", entry[1]);
      });
    }};
  }

  window.toggleSelectMode = toggleSelectMode;
  window.toggleRowSel = toggleRowSel;
  window.openBulkEdit = openBulkEdit;

  window.PtosTodoList = { mount: mount, toggleSelectMode: toggleSelectMode, openBulkEdit: openBulkEdit };
})();
