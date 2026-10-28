(function () {
  "use strict";

  var _acData = null;
  var _acIdx = -1;
  var _acItems = [];
  var _acInput = null;
  var _acDropdown = null;

  function _getInput() {
    return document.getElementById("todo-shell-add-input") ||
           document.querySelector("[data-todo-add-input]");
  }

  function _buildAcData(state) {
    var priLabels = (state && state.priority_labels) || {};
    var projects = (state && state.projects) || [];
    var contexts = (state && state.contexts) || [];
    var ac = {};
    ac["+"] = projects.map(function (p) { return { l: p, v: p + " " }; });
    ac["@"] = contexts.map(function (c) { return { l: c, v: c + " " }; });
    ac["due:"] = [
      { l: "today", v: "due:today " }, { l: "tomorrow", v: "due:tomorrow " },
      { l: "this week", v: "due:this_week " }, { l: "next week", v: "due:next_week " },
      { l: "this month", v: "due:this_month " }, { l: "next month", v: "due:next_month " }
    ];
    ac["t:"] = [
      { l: "today", v: "t:today " }, { l: "tomorrow", v: "t:tomorrow " },
      { l: "this week", v: "t:this_week " }, { l: "this month", v: "t:this_month " }
    ];
    ac["rec:"] = [
      { l: "daily", v: "rec:1d " }, { l: "weekly", v: "rec:1w " },
      { l: "biweekly", v: "rec:2w " }, { l: "monthly", v: "rec:1m " },
      { l: "quarterly", v: "rec:3m " }, { l: "yearly", v: "rec:1y " }
    ];
    var priOpts = ["A", "B", "C", "D"];
    var priDefs = { A: "Critical", B: "Important", C: "Moderate", D: "Low" };
    ac["pri:"] = priOpts.map(function (p) {
      return { l: p + " \u2014 " + (priLabels[p] || priDefs[p]), v: "(" + p + ") " };
    });
    ac["("] = priOpts.map(function (p) {
      return { l: "(" + p + ") " + (priLabels[p] || priDefs[p]), v: "(" + p + ") " };
    });
    return ac;
  }

  function _getCurrentToken(input) {
    var val = input.value;
    var pos = input.selectionStart || val.length;
    var before = val.substring(0, pos);
    var words = before.split(/\s+/);
    var token = words[words.length - 1] || "";
    if (!token) return null;
    var prefixes = Object.keys(_acData).sort(function (a, b) { return b.length - a.length; });
    for (var i = 0; i < prefixes.length; i++) {
      var p = prefixes[i];
      if (token.toLowerCase().startsWith(p.toLowerCase())) {
        return { prefix: p, query: token.substring(p.length), fullToken: token, start: pos - token.length };
      }
    }
    if (token.charAt(0) === "+" || token.charAt(0) === "@") {
      var singlePrefix = token.charAt(0);
      if (_acData[singlePrefix]) {
        return { prefix: singlePrefix, query: token.substring(1), fullToken: token, start: pos - token.length };
      }
    }
    return null;
  }

  function _showDropdown(input, items) {
    if (!_acDropdown) {
      _acDropdown = document.createElement("div");
      _acDropdown.className = "ac-dropdown";
      _acDropdown.style.cssText = "position:absolute;z-index:1000;background:var(--card);border:1px solid var(--border);border-radius:6px;max-height:200px;overflow-y:auto;box-shadow:0 4px 12px rgba(0,0,0,.15);";
      document.body.appendChild(_acDropdown);
    }
    if (!items || !items.length) {
      _acDropdown.style.display = "none";
      return;
    }
    _acItems = items;
    _acIdx = -1;
    var html = "";
    items.forEach(function (item, i) {
      html += '<div class="ac-item" data-idx="' + i + '" style="padding:6px 10px;cursor:pointer;font-size:13px;">' + (item.l || item.v) + '</div>';
    });
    _acDropdown.innerHTML = html;
    var rect = input.getBoundingClientRect();
    _acDropdown.style.top = (rect.bottom + window.scrollY + 2) + "px";
    _acDropdown.style.left = (rect.left + window.scrollX) + "px";
    _acDropdown.style.width = rect.width + "px";
    _acDropdown.style.display = "block";

    _acDropdown.querySelectorAll(".ac-item").forEach(function (el) {
      el.addEventListener("mousedown", function (e) {
        e.preventDefault();
        var idx = parseInt(el.getAttribute("data-idx"), 10);
        _selectItem(input, idx);
      });
    });
  }

  function _selectItem(input, idx) {
    if (idx < 0 || idx >= _acItems.length) return;
    var item = _acItems[idx];
    var val = input.value;
    var pos = input.selectionStart || val.length;
    var tok = _getCurrentToken(input);
    if (tok) {
      var v = item.v;
      if (v.indexOf("__PICKER__") === 0) {
        var pfx = v.replace("__PICKER__:", "").replace(":", "");
        if (window.PtosTodoPopups && window.PtosTodoPopups.pickAddDate) {
          window.PtosTodoPopups.pickAddDate(pfx);
        }
        _hideDropdown();
        return;
      }
      var newText = val.substring(0, tok.start) + v + val.substring(tok.start + tok.fullToken.length);
      input.value = newText;
      input.selectionStart = input.selectionEnd = tok.start + v.length;
    }
    _hideDropdown();
    input.focus();
  }

  function _hideDropdown() {
    if (_acDropdown) _acDropdown.style.display = "none";
    _acItems = [];
    _acIdx = -1;
  }

  function _filterItems(tok) {
    var items = _acData[tok.prefix] || [];
    if (!tok.query) return items;
    var q = tok.query.toLowerCase();
    return items.filter(function (item) {
      return (item.l || "").toLowerCase().indexOf(q) !== -1 ||
             (item.v || "").toLowerCase().indexOf(q) !== -1;
    });
  }

  function _onInput(e) {
    _acInput = (e && e.target) ? e.target : _acInput;
    if (!_acInput) return;
    var tok = _getCurrentToken(_acInput);
    if (!tok) { _hideDropdown(); return; }
    var items = _filterItems(tok);
    _showDropdown(_acInput, items);
  }

  function _onKeydown(e) {
    if (!_acDropdown || _acDropdown.style.display === "none") return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      _acIdx = Math.min(_acIdx + 1, _acItems.length - 1);
      _highlightIdx();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      _acIdx = Math.max(_acIdx - 1, 0);
      _highlightIdx();
    } else if (e.key === "Enter" && _acIdx >= 0) {
      e.preventDefault();
      _selectItem(_acInput, _acIdx);
    } else if (e.key === "Escape") {
      _hideDropdown();
    }
  }

  function _highlightIdx() {
    if (!_acDropdown) return;
    _acDropdown.querySelectorAll(".ac-item").forEach(function (el, i) {
      el.style.background = (i === _acIdx) ? "var(--accent-lt)" : "";
    });
  }

  var _wired = false;
  function _wire() {
    if (_wired) return true;
    var addInput = document.getElementById("todo-shell-add-input") ||
                   document.querySelector("[data-todo-add-input]");
    if (!addInput) return false;
    var state = (window.PTOS_PAGE && window.PTOS_PAGE.todo) || {};
    _acData = _buildAcData(state);

    var inputs = [addInput];
    var searchInput = document.getElementById("todo-shell-search-input");
    if (searchInput) inputs.push(searchInput);

    inputs.forEach(function (inp) {
      inp.addEventListener("input", _onInput);
      inp.addEventListener("keydown", _onKeydown);
      inp.addEventListener("blur", function () {
        setTimeout(_hideDropdown, 200);
      });
    });

    _acInput = addInput;

    fetch("/api/link-ids").then(function (r) { return r.json(); }).then(function (d) {
      if (!d || d.ok === false || !Array.isArray(d)) return;
      var items = d.map(function (it) {
        return { l: it.target, v: it.target + " " };
      });
      _acData["links:"] = items;
    }).catch(function () {});

    _wired = true;
    return true;
  }

  function _wireBracket() {
    if (typeof attachBracketAutocomplete !== "function") return;
    var addInput = document.getElementById("todo-shell-add-input");
    var searchInput = document.getElementById("todo-shell-search-input");
    if (addInput) attachBracketAutocomplete(addInput);
    if (searchInput) attachBracketAutocomplete(searchInput);
  }

  function _wireAll() {
    _wire();
    _wireBracket();
  }

  var _attempts = 0;
  function _tryWire() {
    _wireAll();
    if (_acInput) return;
    if (_attempts < 50) {
      _attempts++;
      setTimeout(_tryWire, 100);
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { setTimeout(_tryWire, 200); });
  } else {
    setTimeout(_tryWire, 200);
  }

  window.PtosTodoAutocomplete = {
    hide: _hideDropdown,
    rebuild: function (state) { _acData = _buildAcData(state); },
    wire: _wireAll
  };
})();