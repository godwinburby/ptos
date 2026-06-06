(function(global) {
  "use strict";

  var MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
                "Jul","Aug","Sep","Oct","Nov","Dec"];

  function TimePicker(opts) {
    this.prefix = opts.prefix || "";
    this.yearMin = opts.yearMin;
    this.yearMax = opts.yearMax;
    this.onChange = opts.onChange || function(){};
    this.selYear = new Date().getFullYear();
    this.selMonth = null;
    this._el("month-picker-btn") && this._init();
  }

  TimePicker.prototype._id = function(n) { return this.prefix + n; };
  TimePicker.prototype._el = function(n) { return document.getElementById(this._id(n)); };

  // ── Public API ──

  TimePicker.prototype.getTime = function() {
    var sel = this._el("time-select");
    if (!sel) return null;
    var val = sel.value;
    if (val === "range") return "range";
    if (val !== "custom") return val || null;
    var dy = this._el("day-input");
    if (dy && dy.value) return dy.value;
    if (this.selMonth) return this.selYear + "-" + this.selMonth;
    var yr = this._el("year-input");
    if (yr && yr.value) return yr.value;
    return null;
  };

  TimePicker.prototype.getRange = function() {
    var fi = this._el("from-date");
    var ti = this._el("to-date");
    if (!fi || !ti) return null;
    var fromVal = fi.value || "";
    var toVal = ti.value || "";
    if (!fromVal && !toVal) return null;
    return {from: fromVal, to: toVal};
  };

  TimePicker.prototype.setRange = function(from, to) {
    var fi = this._el("from-date");
    var ti = this._el("to-date");
    if (fi && from) fi.value = from;
    if (ti && to) ti.value = to;
  };

  TimePicker.prototype.reset = function() {
    this.selYear = new Date().getFullYear();
    this.selMonth = null;
    var mt = this._el("month-text");
    if (mt) mt.textContent = "Pick a month";
    var yi = this._el("year-input");
    if (yi) yi.value = "";
    var di = this._el("day-input");
    if (di) di.value = "";
    var fi = this._el("from-date");
    if (fi) fi.value = "";
    var ti = this._el("to-date");
    if (ti) ti.value = "";
    this._showCustom(false);
    this._showRange(false);
    this.closePicker();
  };

  TimePicker.prototype.setTime = function(code, customTime, fromDate, toDate) {
    var sel = this._el("time-select");
    if (!sel) return;
    if (code && code !== "custom" && code !== "range") {
      for (var i = 0; i < sel.options.length; i++) {
        if (sel.options[i].value === code) {
          sel.value = code;
          this._showCustom(false);
          this._showRange(false);
          this.closePicker();
          return;
        }
      }
    }
    if (code === "range") {
      sel.value = "range";
      this._showCustom(false);
      this._showRange(true);
      if (fromDate) { var fi = this._el("from-date"); if (fi) fi.value = fromDate; }
      if (toDate)   { var ti = this._el("to-date");   if (ti) ti.value = toDate; }
      return;
    }
    sel.value = "custom";
    this._showCustom(true);
    this._showRange(false);
    if (customTime && customTime.length >= 7 && /^\d{4}-\d{2}/.test(customTime)) {
      this.selYear = parseInt(customTime.substring(0, 4));
      this.selMonth = customTime.substring(5, 7);
      var mt = this._el("month-text");
      if (mt) mt.textContent = customTime.substring(0, 7);
    }
    if (customTime && /^\d{4}$/.test(customTime)) {
      var yi = this._el("year-input");
      if (yi) yi.value = customTime;
    }
    if (customTime && /^\d{4}-\d{2}-\d{2}$/.test(customTime)) {
      var di = this._el("day-input");
      if (di) di.value = customTime;
    }
  };

  TimePicker.prototype.onSelectChange = function(val) {
    if (val === "custom") { this._showCustom(true); this._showRange(false); return; }
    if (val === "range")  { this._showCustom(false); this._showRange(true);  return; }
    this._showCustom(false);
    this._showRange(false);
    this.closePicker();
    this.onChange(val);
  };

  TimePicker.prototype._showRange = function(show) {
    var el = this._el("range-block");
    if (el) el.style.display = show ? "block" : "none";
  };

  TimePicker.prototype.shiftYear = function(d) {
    var n = this.selYear + d;
    if (n < this.yearMin || n > this.yearMax) return;
    this.selYear = n;
    this._renderGrid();
  };

  TimePicker.prototype.togglePicker = function(e) {
    var pop = this._el("month-picker-popup");
    if (!pop) return;
    if (e) e.stopPropagation();
    if (pop.style.display === "none") {
      this._renderGrid();
      var btn = this._el("month-picker-btn");
      if (btn) {
        var rect = btn.getBoundingClientRect();
        pop.style.top = (rect.bottom + window.scrollY + 6) + "px";
        pop.style.left = Math.max(4, Math.min(rect.left, window.innerWidth - 260)) + "px";
      }
      pop.style.display = "block";
    } else {
      this.closePicker();
    }
  };

  TimePicker.prototype.closePicker = function() {
    var pop = this._el("month-picker-popup");
    if (pop) pop.style.display = "none";
  };

  TimePicker.prototype._showCustom = function(show) {
    var el = this._el("custom-block");
    if (el) el.style.display = show ? "block" : "none";
  };

  TimePicker.prototype._renderGrid = function() {
    var py = this._el("picker-year");
    if (py) py.textContent = this.selYear;
    var grid = this._el("picker-grid");
    if (!grid) return;
    grid.innerHTML = "";
    var self = this;
    MONTHS.forEach(function(name, i) {
      var mm = String(i + 1).padStart(2, "0");
      var active = (self.selMonth === mm);
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = name;
      btn.style.cssText =
        "padding:9px 0;border-radius:8px;cursor:pointer;font-size:13px;" +
        "border:1px solid " + (active ? "var(--accent)" : "var(--border)") + ";" +
        "background:"       + (active ? "var(--accent)" : "var(--bg)")     + ";" +
        "color:"            + (active ? "#fff"           : "var(--text)")  + ";" +
        "font-weight:"      + (active ? "700"            : "400")          + ";";
      btn.addEventListener("click", function() {
        self.selMonth = mm;
        self.closePicker();
        var mt = self._el("month-text");
        if (mt) mt.textContent = self.selYear + "-" + mm;
        self.onChange(self.selYear + "-" + mm);
      });
      grid.appendChild(btn);
    });
  };

  // ── Internal ──

  TimePicker.prototype._init = function() {
    var self = this;
    var btn = this._el("month-picker-btn");
    if (btn) btn.addEventListener("click", function(e) { self.togglePicker(e); });

    document.addEventListener("click", function(e) {
      var pop = self._el("month-picker-popup");
      if (!pop || pop.style.display === "none") return;
      if (!pop.contains(e.target) && e.target !== self._el("month-picker-btn")) {
        self.closePicker();
      }
    });

    var pop = this._el("month-picker-popup");
    if (pop) {
      var prev = pop.querySelector("[data-tp-prev]");
      var next = pop.querySelector("[data-tp-next]");
      if (prev) prev.addEventListener("click", function() { self.shiftYear(-1); });
      if (next) next.addEventListener("click", function() { self.shiftYear(1); });
    }

    var yi = this._el("year-input");
    if (yi) yi.addEventListener("change", function() {
      if (yi.value && yi.value.length === 4) self.onChange(yi.value);
    });

    var di = this._el("day-input");
    if (di) di.addEventListener("change", function() {
      if (di.value) self.onChange(di.value);
    });

    var fi = this._el("from-date");
    var ti = this._el("to-date");
    if (fi) fi.addEventListener("change", function() {
      self.onChange("range");
    });
    if (ti) ti.addEventListener("change", function() {
      self.onChange("range");
    });
  };

  global.TimePicker = TimePicker;
})(window);
