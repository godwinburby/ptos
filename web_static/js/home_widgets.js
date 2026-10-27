// home_widgets.js — home page widget boots + action-widget mounts.
//
// The home route serializes its widget specs into #home-widget-specs as
// [{section, kind, body}] (body is a ```ptos TOML string). This script
// creates a host element per spec inside the matching [data-home-section]
// container and resolves them in one batch POST, so every card paints
// from a single round trip. Section placement and titles are baked by
// the server; capture/quick_add/quick_add_multi are interactive mounts,
// dashboard/threshold/due paint through bare (chrome-less) renderers —
// the widget host supplies the title/Open/refresh chrome instead.
(function () {
  "use strict";

  var INTERACTIVE = { records: 1, capture: 1, quick_add: 1, quick_add_multi: 1 };

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function post(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {})
    }).then(function (r) { return r.json(); });
  }

  // ── bare renderers (widget chrome already carries the title) ───────────────
  if (window.PtosWidgets) {
    PtosWidgets.register("dashboard", {
      render: function (el, data) { el.innerHTML = renderDashboard(data, { bare: true }); }
    });
    PtosWidgets.register("threshold", {
      render: function (el, data) {
        el.innerHTML = renderThresholdResult(data.thresholds || [], { bare: true });
      }
    });
    PtosWidgets.register("due", {
      render: function (el, data) { el.innerHTML = renderDue(data, { bare: true }); }
    });
    PtosWidgets.register("calendar", {
      render: function (el, data, ctx) {
        el.innerHTML = renderCalendar(data, { interactive: ctx && ctx.size === "full" });
      },
      mount: function (el, data, ctx) {
        el.innerHTML = renderCalendar(data, { interactive: true });
        var onKey = function (e) {
          if ((e.key === "Enter" || e.key === " ") && e.target.matches("[data-calendar-day]")) {
            e.preventDefault();
            e.target.click();
          }
        };
        var onClick = function (e) {
          var cell = e.target.closest && e.target.closest("[data-calendar-day]");
          if (!cell || !el.contains(cell)) return;
          var day = cell.getAttribute("data-calendar-day");
          var active = cell.classList.contains("expanded");
          el.querySelectorAll("[data-calendar-day].expanded").forEach(function (node) {
            node.classList.remove("expanded");
          });
          el.querySelectorAll("[data-calendar-detail]").forEach(function (node) {
            node.style.display = "none";
          });
          if (!active) {
            cell.classList.add("expanded");
            var detail = el.querySelector('[data-calendar-detail="' + day + '"]');
            if (detail) detail.style.display = "block";
          }
        };
        el.addEventListener("click", onClick);
        el.addEventListener("keydown", onKey);
        return { destroy: function () {
          el.removeEventListener("click", onClick);
          el.removeEventListener("keydown", onKey);
        }};
      }
    });
    PtosWidgets.register("project", {
      render: function (el, data, ctx) {
        el.innerHTML = renderProject(data, { full: ctx && ctx.size === "full" });
      }
    });

    // ── capture ─────────────────────────────────────────────────────────────
    PtosWidgets.register("capture", {
      render: function (el) { el.innerHTML = _captureHtml(); },
      mount: function (el, data, ctx) {
        el.innerHTML = _captureHtml();
        var input = el.querySelector(".cap-input");
        var msg = el.querySelector(".cap-msg");
        function show(text, ok) {
          msg.textContent = text;
          msg.style.color = ok ? "var(--success)" : "var(--error)";
          msg.style.display = "block";
        }
        function capture(thenConvert) {
          var text = (input.value || "").trim();
          if (!text) return;
          post("/api/capture", { text: text }).then(function (d) {
            if (!d.ok) { show(d.error || "Capture failed", false); return; }
            if (thenConvert) {
              window.location.href = "/edit?convert=1&filepath=" +
                encodeURIComponent(d.filepath) + "&lineno=" + d.lineno +
                "&line=" + encodeURIComponent(d.line) +
                "&return_to=" + encodeURIComponent("/");
              return;
            }
            input.value = "";
            show("✔ Captured", true);
          }).catch(function (e) { show(String(e), false); });
        }
        el.addEventListener("click", function (e) {
          var t = e.target;
          if (!t) return;
          if (t.classList.contains("cap-btn")) capture(false);
          if (t.classList.contains("cap-convert-btn")) capture(true);
        });
        el.addEventListener("keydown", function (e) {
          if (e.key === "Enter" && e.target === input) capture(false);
        });
        return { destroy: function () {} };
      }
    });

    // ── quick add (single presets) ──────────────────────────────────────────
    PtosWidgets.register("quick_add", {
      render: function (el, data) { el.innerHTML = _quickAddHtml(data); },
      mount: function (el, data, ctx) {
        el.innerHTML = _quickAddHtml(data);
        var showAll = false;
        function repaint() { el.innerHTML = _quickAddHtml(data, showAll); }
        el.addEventListener("click", function (e) {
          var t = e.target;
          if (!t) return;
          var toggle = t.closest && t.closest(".qa-toggle-all");
          if (toggle) {
            showAll = !showAll;
            repaint();
            return;
          }
          var chip = t.closest && t.closest("[data-preset]");
          if (!chip) return;
          var name = chip.getAttribute("data-preset");
          if (chip.classList.contains("preset-del")) {
            if (!confirm("Delete preset '" + name + "'?\n\nThis cannot be undone.")) return;
            post("/api/preset_delete", { name: name }).then(function (d) {
              if (!d.ok) { ctx.toast(d.error || "Delete failed", { error: true }); return; }
              ctx.refresh();
            });
            return;
          }
          if (chip.classList.contains("preset-instant-toggle")) {
            var active = chip.getAttribute("data-active") === "1";
            post("/api/preset_instant", { name: name, instant: !active })
              .then(function (d) {
                if (!d.ok) { ctx.toast(d.error || "Toggle failed", { error: true }); return; }
                ctx.refresh();
              });
            return;
          }
          if (chip.classList.contains("preset-instant")) {
            post("/api/preset_use", { name: name }).catch(function () {});
            post("/api/preset_add", {
              name: name, date: new Date().toISOString().split("T")[0]
            }).then(function (d) {
              if (!d.ok) { ctx.toast(d.error || "Add failed", { error: true }); return; }
              ctx.toast("✔ " + (d.count || 1) + " added");
            });
            return;
          }
          if (chip.classList.contains("preset-chip")) {
            post("/api/preset_use", { name: name }).catch(function () {});
          }
        });
        return { destroy: function () {} };
      }
    });

    // ── quick add (multi presets) ───────────────────────────────────────────
    PtosWidgets.register("quick_add_multi", {
      render: function (el, data) { el.innerHTML = _quickAddMultiHtml(data); },
      mount: function (el, data, ctx) {
        el.innerHTML = _quickAddMultiHtml(data);
        el.addEventListener("click", function (e) {
          var t = e.target;
          if (!t) return;
          var del = t.closest && t.closest(".preset-del");
          if (del) {
            var dname = del.getAttribute("data-preset");
            if (!confirm("Delete preset '" + dname + "'?\n\nThis cannot be undone.")) return;
            post("/api/preset_delete", { name: dname }).then(function (d) {
              if (!d.ok) { ctx.toast(d.error || "Delete failed", { error: true }); return; }
              ctx.refresh();
            });
            return;
          }
          var chip = t.closest && t.closest(".preset-chip[data-preset]");
          if (!chip) return;
          var name = chip.getAttribute("data-preset");
          var orig = chip.innerHTML;
          chip.disabled = true;
          chip.textContent = "Adding…";
          post("/api/preset_add", {
            name: name, date: new Date().toISOString().split("T")[0]
          }).then(function (d) {
            if (!d.ok) {
              chip.innerHTML = orig;
              chip.disabled = false;
              ctx.toast(d.error || "Add failed", { error: true });
              return;
            }
            chip.textContent = "✔ " + (d.count || 1) + " added";
            chip.style.background = "var(--success)";
            setTimeout(function () { ctx.refresh(); }, 1200);
          }).catch(function () {
            chip.innerHTML = orig;
            chip.disabled = false;
          });
        });
        return { destroy: function () {} };
      }
    });

    PtosWidgets.register("time_picker", {
      render: function (el) {
        el.innerHTML = '<div style="color:var(--sub);font-size:13px;">' +
          'Time window controls are available on Home.</div>';
      },
      mount: function (el, data, ctx) {
        el.innerHTML = _timePickerHtml(data);
        var select = el.querySelector(".home-time-select");
        var custom = el.querySelector(".home-time-custom");
        var apply = el.querySelector(".home-time-apply");
        var listeners = [];
        function on(node, type, fn) {
          if (!node) return;
          node.addEventListener(type, fn);
          listeners.push([node, type, fn]);
        }
        function updateCustom() {
          var mode = select.value;
          var active = ["year", "month", "date", "range"].indexOf(mode) !== -1;
          if (custom) custom.style.display = active ? "flex" : "none";
          Array.prototype.forEach.call(
            el.querySelectorAll(".home-time-field"), function (field) {
              field.style.display = field.classList.contains(
                "home-time-" + mode + "-field") ? "block" : "none";
            });
        }
        function applySelection() {
          var mode = select.value;
          var url = new URL(window.location.href);
          ["time", "custom_time", "from_date", "to_date"].forEach(
            function (key) { url.searchParams.delete(key); });
          if (mode === "year" || mode === "month" || mode === "date") {
            var input = el.querySelector(".home-time-" + mode);
            if (!input || !input.value) return;
            url.searchParams.set("time", mode);
            url.searchParams.set("custom_time", input.value);
          } else if (mode === "range") {
            var from = el.querySelector(".home-time-from").value;
            var to = el.querySelector(".home-time-to").value;
            if (!from && !to) return;
            url.searchParams.set("time", "range");
            if (from) url.searchParams.set("from_date", from);
            if (to) url.searchParams.set("to_date", to);
          } else if (mode) {
            url.searchParams.set("time", mode);
          }
          var nextUrl = url.pathname + url.search + url.hash;
          if (ctx.host === "note") {
            window.history.pushState({}, "", nextUrl);
            window.dispatchEvent(new CustomEvent("ptos:time-window-change"));
          } else {
            window.location.href = nextUrl;
          }
        }
        on(select, "change", function () {
          updateCustom();
          if (["year", "month", "date", "range"].indexOf(select.value) === -1) {
            applySelection();
          }
        });
        on(apply, "click", applySelection);
        updateCustom();
        return { destroy: function () {
          listeners.forEach(function (entry) {
            entry[0].removeEventListener(entry[1], entry[2]);
          });
          listeners = [];
        }};
      }
    });
  }

  function _captureHtml() {
    return '<div style="display:flex;gap:8px;flex-wrap:wrap;">' +
      '<input type="text" class="cap-input" placeholder="Quick record… (Enter to capture)" ' +
      'style="flex:1;min-width:220px;padding:8px 12px;border-radius:8px;border:1.5px solid var(--border);background:var(--bg);color:var(--text);font-size:14px;">' +
      '<button type="button" class="btn btn-primary cap-btn">Capture</button>' +
      '<button type="button" class="btn btn-ghost cap-convert-btn" title="Capture and convert to another record type">Convert</button>' +
      '</div>' +
      '<div class="cap-msg" style="font-size:13px;margin-top:8px;display:none;"></div>';
  }

  function _presetChip(name, data, isRemaining) {
    var instant = (data.instant || []).indexOf(name) !== -1;
    var chip;
    if (instant) {
      chip = '<button type="button" class="preset-chip preset-instant" data-preset="' + esc(name) + '">' +
        '+ ' + esc(name) + ' <span style="opacity:.7;font-size:11px;">instant</span></button>' +
        '<a href="/add?preset=' + encodeURIComponent(name) + '" class="preset-edit" title="Edit preset">✎</a>';
    } else {
      chip = '<a href="/add?preset=' + encodeURIComponent(name) + '" class="preset-chip" data-preset="' +
        esc(name) + '">+ ' + esc(name) + '</a>';
    }
    return '<span class="preset-chip-wrap">' + chip +
      '<button type="button" class="preset-instant-toggle" data-preset="' + esc(name) + '"' +
      (instant ? ' data-active="1"' : '') +
      ' title="Toggle instant save">⚡</button>' +
      '<button type="button" class="preset-del" data-preset="' + esc(name) +
      '" title="Delete preset">×</button></span>';
  }

  function _quickAddHtml(data, showAll) {
    var frequent = data.frequent || [];
    var remaining = data.remaining || [];
    var html = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">' +
      '<div style="font-size:14px;font-weight:700;"></div>';
    if (remaining.length) {
      html += '<button type="button" class="qa-toggle-all" ' +
        'style="background:none;border:none;font-size:12px;color:var(--accent);cursor:pointer;font-weight:600;padding:0;">' +
        (showAll ? "Show less ▲" : "Show all ▾") + '</button>';
    }
    html += '</div><div class="chip-group">' +
      frequent.map(function (n) { return _presetChip(n, data, false); }).join("") +
      '</div>';
    if (remaining.length) {
      html += '<div class="chip-group" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border);' +
        (showAll ? "" : "display:none;") + '">' +
        remaining.map(function (n) { return _presetChip(n, data, true); }).join("") +
        '</div>';
    }
    return html;
  }

  function _quickAddMultiHtml(data) {
    var presets = data.presets || {};
    var names = Object.keys(presets);
    if (!names.length) return '<div style="color:var(--sub);font-size:13px;">No multi-record presets.</div>';
    return '<div class="chip-group">' + names.map(function (n) {
      return '<span class="preset-chip-wrap">' +
        '<button type="button" class="preset-chip" data-preset="' + esc(n) + '">+ ' + esc(n) +
        (presets[n] ? ' <span style="opacity:.6;font-size:11px;">(' + esc(presets[n]) + ')</span>' : '') +
        '</button>' +
        '<button type="button" class="preset-del" data-preset="' + esc(n) +
        '" title="Delete preset">×</button></span>';
    }).join("") + '</div>';
  }

  function _timePickerHtml(data) {
    var params = new URLSearchParams(window.location.search || "");
    var time = params.get("time") || "";
    var customTime = params.get("custom_time") || "";
    var fromDate = params.get("from_date") || "";
    var toDate = params.get("to_date") || "";
    var selected = time;
    if (fromDate || time === "range") selected = "range";
    else if (/^\d{4}$/.test(time)) { selected = "year"; customTime = time; }
    else if (/^\d{4}-\d{2}$/.test(time)) { selected = "month"; customTime = time; }
    else if (/^\d{4}-\d{2}-\d{2}$/.test(time)) { selected = "date"; customTime = time; }
    var options = data.time_options || [];
    var html = '<div class="home-time-picker">' +
      '<select class="home-time-select" style="padding:7px 10px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:13px;min-width:170px;">' +
      '<option value=""' + (selected ? "" : " selected") + '>Default</option>';
    options.forEach(function (item) {
      var value = String(item.value || "");
      html += '<option value="' + esc(value) + '"' +
        (value === selected ? " selected" : "") + '>' + esc(item.label || value) + '</option>';
    });
    html += '</select><div class="home-time-custom" style="display:none;gap:8px;align-items:end;flex-wrap:wrap;margin-top:8px;">' +
      '<label class="home-time-field home-time-year-field" style="display:none;">Year<input class="home-time-year" type="number" min="' + esc((data.year_range || [1900, 2100])[0]) + '" max="' + esc((data.year_range || [1900, 2100])[1]) + '" value="' + (selected === "year" ? esc(customTime) : "") + '"></label>' +
      '<label class="home-time-field home-time-month-field" style="display:none;">Month<input class="home-time-month" type="month" value="' + (selected === "month" ? esc(customTime.slice(0, 7)) : "") + '"></label>' +
      '<label class="home-time-field home-time-date-field" style="display:none;">Date<input class="home-time-date" type="date" value="' + (selected === "date" ? esc(customTime) : "") + '"></label>' +
      '<label class="home-time-field home-time-range-field" style="display:none;">From<input class="home-time-from" type="date" value="' + esc(fromDate) + '"></label>' +
      '<label class="home-time-field home-time-range-field" style="display:none;">To<input class="home-time-to" type="date" value="' + esc(toDate) + '"></label>' +
      '<button type="button" class="btn btn-primary btn-sm home-time-apply">Apply</button></div></div>';
    return html;
  }

  // ── boot ───────────────────────────────────────────────────────────────────
  function boot() {
    if (!window.PtosWidgets) return;
    var blob = document.getElementById("home-widget-specs");
    if (!blob) return;
    var specs;
    try {
      specs = JSON.parse(blob.textContent || "[]");
    } catch (e) {
      return;
    }
    if (!Array.isArray(specs) || !specs.length) return;
    var items = [];
    specs.forEach(function (s) {
      var section = document.querySelector(
        '[data-home-section="' + (s.section || "") + '"]');
      if (!section) return;
      var host = document.createElement("div");
      host.setAttribute("data-ptos-widget", "1");
      if (INTERACTIVE[s.kind]) host.setAttribute("data-interactive", "1");
      section.appendChild(host);
      items.push({ el: host, body: s.body });
    });
    if (items.length) {
      PtosWidgets.mountBatch(items, { host: "home" });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
