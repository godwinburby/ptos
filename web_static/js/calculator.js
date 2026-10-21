(function () {
  "use strict";

  function evaluate(src) {
    var s = String(src == null ? "" : src).replace(/\s+/g, "");
    if (!s) return { ok: false };
    var i = 0;
    function parseExpr() {
      var v = parseTerm(null);
      while (i < s.length && (s[i] === "+" || s[i] === "-")) {
        var op = s[i++];
        var r = parseTerm(v);
        v = op === "+" ? v + r : v - r;
      }
      return v;
    }
    function parseTerm(base) {
      var v = parseFactor(base);
      while (i < s.length && (s[i] === "*" || s[i] === "/")) {
        var op = s[i++];
        var r = parseFactor(null);
        v = op === "*" ? v * r : v / r;
      }
      return v;
    }
    function parseFactor(base) {
      if (s[i] === "+") { i++; return parseFactor(base); }
      if (s[i] === "-") { i++; return -parseFactor(base); }
      if (s[i] === "(") {
        i++;
        var v = parseExpr();
        if (s[i] !== ")") throw new Error("expected )");
        i++;
        return v;
      }
      var start = i;
      while (i < s.length && /[0-9.]/.test(s[i])) i++;
      if (i === start) throw new Error("expected number");
      var n = parseFloat(s.slice(start, i));
      if (!isFinite(n)) throw new Error("bad number");
      if (s[i] === "%") {
        i++;
        return base != null ? (base * n) / 100 : n / 100;
      }
      return n;
    }
    var out;
    try {
      out = parseExpr();
      if (i < s.length) throw new Error("trailing input");
    } catch (err) {
      return { ok: false };
    }
    if (!isFinite(out)) return { ok: false };
    return { ok: true, value: out };
  }

  var _panel = null;
  var _expr = null;
  var _result = null;
  var _applyBtn = null;
  var _target = null;

  var _KEYS = [
    ["C", "util"], ["\u232B", "util"], ["(", "op"], [")", "op"],
    ["7", ""], ["8", ""], ["9", ""], ["/", "op"],
    ["4", ""], ["5", ""], ["6", ""], ["*", "op"],
    ["1", ""], ["2", ""], ["3", ""], ["-", "op"],
    ["0", ""], [".", ""], ["%", "op"], ["+", "op"]
  ];

  function _esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function _ensurePanel() {
    if (_panel) return _panel;
    _panel = document.createElement("div");
    _panel.className = "calc-panel";
    var html = '<input class="calc-expr" type="text" inputmode="decimal" autocomplete="off" spellcheck="false" placeholder="0">';
    html += '<div class="calc-result"></div>';
    html += '<div class="calc-keys">';
    for (var k = 0; k < _KEYS.length; k++) {
      html += '<button type="button" class="calc-key ' + _KEYS[k][1] + '" data-calc-key="' + _esc(_KEYS[k][0]) + '">' + _esc(_KEYS[k][0]) + "</button>";
    }
    html += '<button type="button" class="calc-apply" data-calc-apply>= Apply</button>';
    html += "</div>";
    _panel.innerHTML = html;
    document.body.appendChild(_panel);
    _expr = _panel.querySelector(".calc-expr");
    _result = _panel.querySelector(".calc-result");
    _applyBtn = _panel.querySelector(".calc-apply");
    _expr.addEventListener("input", _refresh);
    return _panel;
  }

  function _refresh() {
    var r = evaluate(_expr.value);
    if (r.ok) {
      _result.innerHTML = '= <span class="val">' + Math.round(r.value * 1000000) / 1000000 + "</span>";
      _applyBtn.disabled = false;
    } else {
      _result.textContent = _expr.value ? "= \u2014" : "";
      _applyBtn.disabled = true;
    }
  }

  function closeCalc() {
    if (_panel) _panel.classList.remove("open");
    _target = null;
  }

  function _insert(text) {
    _expr.value += text;
    _refresh();
    _expr.focus();
  }

  function _backspace() {
    _expr.value = _expr.value.slice(0, -1);
    _refresh();
    _expr.focus();
  }

  function applyCalc() {
    if (!_target) return;
    var r = evaluate(_expr.value);
    if (!r.ok) return;
    var v = String(Math.round(r.value));
    _target.value = v;
    _target.dispatchEvent(new Event("input", { bubbles: true }));
    _target.dispatchEvent(new Event("change", { bubbles: true }));
    closeCalc();
  }

  function openCalc(btn) {
    var forId = btn.getAttribute("data-for");
    var input = forId ? document.getElementById(forId) : null;
    if (!input) return;
    var panel = _ensurePanel();
    _target = input;
    _expr.value = input.value != null ? String(input.value) : "";
    _refresh();
    panel.classList.remove("open");
    var rect = btn.getBoundingClientRect();
    panel.style.top = (rect.bottom + 4) + "px";
    panel.style.left = Math.max(4, Math.min(rect.left, window.innerWidth - 244)) + "px";
    panel.classList.add("open");
    _expr.focus();
  }

  document.addEventListener("click", function (e) {
    if (!e.target || !e.target.closest) return;
    var btn = e.target.closest(".calc-btn");
    if (btn) {
      e.preventDefault();
      openCalc(btn);
      return;
    }
    var key = e.target.closest("[data-calc-key]");
    if (key && _panel && _panel.contains(key)) {
      var k = key.getAttribute("data-calc-key");
      if (k === "C") { _expr.value = ""; _refresh(); _expr.focus(); }
      else if (k === "\u232B") _backspace();
      else _insert(k);
      return;
    }
    if (e.target.closest("[data-calc-apply]") && _panel && _panel.contains(e.target)) {
      applyCalc();
      return;
    }
    if (_panel && _panel.classList.contains("open") && !e.target.closest(".calc-panel")) closeCalc();
  });

  document.addEventListener("keydown", function (e) {
    if (!_panel || !_panel.classList.contains("open")) return;
    if (e.key === "Escape") { closeCalc(); return; }
    if (e.key === "Enter" && _panel.contains(document.activeElement)) {
      e.preventDefault();
      applyCalc();
    }
  });

  window.PtosCalc = { open: openCalc, close: closeCalc, evaluate: evaluate, apply: applyCalc };
})();
