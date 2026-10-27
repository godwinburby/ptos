(function () {
  "use strict";

  function parse(id) {
    var node = document.getElementById(id);
    if (!node) return null;
    try { return JSON.parse(node.textContent || "null"); } catch (e) { return null; }
  }

  function params() { return new URLSearchParams(window.location.search); }
  function syncUrl(p, path) {
    var q = p.toString();
    var url = (path || window.location.pathname) + (q ? "?" + q : "");
    window.history.replaceState({}, "", url);
  }

  function setValue(body, key, value) {
    var lines = String(body || "").split(/\r?\n/).filter(function (line) {
      return !new RegExp("^\\s*" + key + "\\s*=").test(line);
    });
    if (value !== null && value !== undefined && value !== "") {
      lines.push(key + " = " + JSON.stringify(String(value)));
    }
    return lines.filter(Boolean).join("\n");
  }

  function boot() {
    var spec = parse("page-spec");
    var data = parse("page-data");
    var state = window.PTOS_PAGE || {};
    var host = document.getElementById("page-widget");
    var items = spec && Array.isArray(spec.items) ? spec.items : (spec ? [spec] : []);
    var values = Array.isArray(data) ? data : (data ? [data] : []);
    var handles = [];

    if (host && window.PtosWidgets) {
      if (!items.length && state.empty) {
        var empty = document.createElement("div");
        empty.className = "msg";
        empty.style.color = "var(--sub)";
        empty.textContent = state.empty;
        host.appendChild(empty);
      }
      items.forEach(function (item, index) {
        var mountEl = document.createElement("div");
        mountEl.className = "page-widget-item";
        host.appendChild(mountEl);
        handles.push(PtosWidgets.mount(mountEl, item.body, {
          data: values[index] || {},
          host: "page",
          interactive: item.interactive !== false,
          size: "full",
          context: state.context || null,
          error: state.error || null
        }));
      });
    }

    function refreshBodies(update, p, path) {
      items.forEach(function (item, index) {
        item.body = update(item.body, index);
        if (handles[index] && handles[index].setSpec) handles[index].setSpec(item.body);
      });
      syncUrl(p, path);
    }

    var controls = document.querySelector("[data-page-controls]");
    if (!controls) return;
    var timeSelect = controls.querySelector("[data-page-time]");
    var custom = controls.querySelector("[data-page-custom-time]");
    var apply = controls.querySelector("[data-page-apply]");

    function setCustomMode() {
      if (custom && timeSelect) custom.dataset.mode = ["year", "month", "date", "range"].indexOf(timeSelect.value) >= 0 ? timeSelect.value : "";
    }

    function saveTime() {
      if (!timeSelect) return;
      var p = params();
      ["time", "custom_time", "from_date", "to_date"].forEach(function (key) { p.delete(key); });
      var value = timeSelect.value;
      var bodyTime = value;
      var from = "";
      var to = "";
      if (["year", "month", "date"].indexOf(value) >= 0) {
        var input = custom.querySelector(value === "year" ? "[data-page-year]" : value === "month" ? "[data-page-month-value]" : "[data-page-date]");
        if (!input || !input.value) { setCustomMode(); return; }
        bodyTime = input.value;
        p.set("time", value);
        p.set("custom_time", input.value);
      } else if (value === "range") {
        from = custom.querySelector("[data-page-from]").value;
        to = custom.querySelector("[data-page-to]").value;
        p.set("time", "range");
        if (from) p.set("from_date", from);
        if (to) p.set("to_date", to);
      } else if (value) {
        p.set("time", value);
      }
      refreshBodies(function (body) {
        body = setValue(body, "time", bodyTime);
        body = setValue(body, "from_date", from);
        return setValue(body, "to_date", to);
      }, p);
    }

    if (timeSelect) {
      setCustomMode();
      timeSelect.addEventListener("change", function () {
        setCustomMode();
        if (["year", "month", "date", "range"].indexOf(timeSelect.value) < 0) saveTime();
      });
    }
    if (apply) apply.addEventListener("click", saveTime);

    controls.querySelectorAll("[data-page-selector]").forEach(function (selector) {
      selector.addEventListener("change", function () {
        var p = params();
        var key = selector.getAttribute("data-page-selector") || "name";
        var pathPrefix = selector.getAttribute("data-page-path-prefix");
        if (pathPrefix) p.delete(key);
        else if (selector.value) p.set(key, selector.value); else p.delete(key);
        var value = selector.value === "__all__" ? "" : selector.value;
        var bodyKey = selector.getAttribute("data-page-body-key") || key;
        refreshBodies(function (body) { return setValue(body, bodyKey, value); }, p,
          pathPrefix ? pathPrefix + (value ? "/" + encodeURIComponent(value) : "") : null);
      });
    });

    controls.querySelectorAll("[data-page-month-shift]").forEach(function (button) {
      button.addEventListener("click", function () {
        var p = params();
        var ym = state.month || {};
        var date = new Date(Number(ym.year), Number(ym.month) - 1, 1);
        date.setMonth(date.getMonth() + Number(button.dataset.pageMonthShift));
        var month = String(date.getMonth() + 1).padStart(2, "0");
        var customMonth = date.getFullYear() + "-" + month;
        state.month = { year: date.getFullYear(), month: date.getMonth() + 1 };
        if (state.monthParam === "custom_time") {
          p.set("time", "month");
          p.set("custom_time", customMonth);
          p.delete("from_date");
          p.delete("to_date");
          refreshBodies(function (body) {
            body = setValue(body, "time", customMonth);
            body = setValue(body, "from_date", "");
            return setValue(body, "to_date", "");
          }, p);
        } else {
          p.set("year", String(date.getFullYear()));
          p.set("month", String(date.getMonth() + 1));
          refreshBodies(function (body) { return setValue(body, "time", customMonth); }, p);
        }
      });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
