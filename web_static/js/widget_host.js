// widget_host.js — interactive widget layer (spec §3.3).
//
// PtosWidgets.register(kind, {render(el, data, ctx), mount(el, data, ctx)})
//   render — static markup (the path note previews already use)
//   mount  — static markup plus event wiring; returns {destroy()}
// PtosWidgets.mount(el, body, {host, interactive, notifyChange, time})
//   body is the ```ptos TOML string (falls back to el.dataset.body);
//   returns {refresh(), destroy(), el, ctx}.
// PtosWidgets.mountAll(root, opts) — mounts every [data-ptos-widget].
//
// Chrome per widget: title + "Open →" link + refresh control, with loading
// and error states. Fetches go through POST /api/widgets/resolve (one item)
// so widgets get widget-layer semantics (row caps, threshold query_url);
// note previews keep embeds.js's /api/embed/resolve path.
//
// Instance-scoped DOM only: no global ids, everything queried from the host
// element. The single <style> block is stamped data-ph-style and injected
// once. ctx = {host, interactive, time, refresh(), notifyChange(), toast()}.
(function () {
  "use strict";

  var REG = {};
  var _cache = {};

  function register(kind, impl) {
    REG[kind] = impl || {};
  }

  function implFor(kind) {
    return (kind && REG[kind]) || null;
  }

  var TIME_AWARE = {
    query: 1, metric: 1, dashboard: 1, threshold: 1, board: 1,
    habit: 1, calendar: 1, records: 1
  };

  function timeWindowLabel(context) {
    context = context || {};
    var from = context.from_date || "";
    var to = context.to_date || "";
    if (context.time === "range" || from) {
      return (from || "Start") + " to " + (to || "Today");
    }
    var time = String(context.time || "");
    if (/^\d{4}$/.test(time)) return "Year " + time;
    if (/^\d{4}-\d{2}$/.test(time)) {
      var monthDate = new Date(time + "-01T00:00:00");
      return isNaN(monthDate.getTime()) ? time :
        monthDate.toLocaleString(undefined, { month: "long", year: "numeric" });
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(time)) return time;
    var labels = {
      td: "Today", yd: "Yesterday", tw: "This week", lw: "Last week",
      tm: "This month", lm: "Last month", tq: "This quarter",
      lq: "Last quarter", ty: "This year", ly: "Last year", all: "All time"
    };
    if (labels[time]) return labels[time];
    return time.replace(/-1$/, " · previous").replace(/[-_]/g, " ")
      .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  window.PtosWidgetTimeLabel = timeWindowLabel;

  function _esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function _post(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {})
    }).then(function (r) { return r.json(); });
  }

  function _cacheKey(body, context) {
    return String(body) + "\u0000" + JSON.stringify(context || {});
  }

  function _fetch(body, force, context) {
    var key = _cacheKey(body, context);
    if (!force && _cache.hasOwnProperty(key)) {
      return Promise.resolve({ ok: true, data: _cache[key] });
    }
    var payload = { items: [{ id: 1, body: body }] };
    if (context) payload.context = context;
    return _post("/api/widgets/resolve", payload)
      .then(function (d) {
        if (!d || !d.ok || !d.results || !d.results[0]) {
          return { ok: false, error: (d && d.error) || "Failed to load widget" };
        }
        var first = d.results[0];
        if (!first.ok) {
          return { ok: false, error: first.error || "Failed to load widget" };
        }
        _cache[key] = first.data;
        return { ok: true, data: first.data };
      })
      .catch(function (e) {
        return { ok: false, error: String(e) };
      });
  }

  function _nameOf(body) {
    var m = /name\s*=\s*"([^"]*)"/.exec(body || "");
    return m ? m[1] : "";
  }

  // ── scoped live refresh (spec 3.4) ─────────────────────────────────────────
  // sse.js relays the server's data-changed event as "ptos:data-changed".
  // Mounted widgets subscribe by scope: todo widgets only re-fetch on "todo",
  // every other kind reads records; "config" (settings/schema/queries) and a
  // scope-less payload refresh everything. Debounced 500 ms so one write that
  // fans out to several emits still triggers a single pass, and refreshed on
  // tab-visible / back-forward-cache restore. No polling.
  var _REFRESH_DEBOUNCE_MS = 500;
  var _live = [];
  var _pendingScopes = null;
  var _pendingAll = false;
  var _debounceTimer = null;

  function _scopesForKind(kind) {
    if (kind === "todo" || kind === "todo_summary") return ["todo"];
    if (kind === "project") return ["records", "todo", "notes"];
    if (kind === "quick_add" || kind === "quick_add_multi") return ["config"];
    if (kind === "capture" || kind === "journal") return [];
    return ["records"];
  }

  function _clearCache() {
    for (var k in _cache) {
      if (Object.prototype.hasOwnProperty.call(_cache, k)) delete _cache[k];
    }
  }

  function _runPendingRefresh() {
    var scopes = _pendingScopes || [];
    var all = _pendingAll || scopes.indexOf("config") !== -1;
    _pendingScopes = null;
    _pendingAll = false;
    _live.slice().forEach(function (h) {
      if (destroyedSafe(h)) return;
      var mine = h._phScopes || [];
      if (all || mine.some(function (s) { return scopes.indexOf(s) !== -1; })) {
        h.refresh();
      }
    });
  }

  function destroyedSafe(h) {
    try { return !h || !h.el || !h.el._phWidget; } catch (e) { return true; }
  }

  function _scheduleRefresh(scope) {
    if (scope == null) {
      _pendingAll = true;
    } else {
      _pendingScopes = _pendingScopes || [];
      if (_pendingScopes.indexOf(scope) === -1) _pendingScopes.push(scope);
    }
    if (_debounceTimer) clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(function () {
      _debounceTimer = null;
      _runPendingRefresh();
    }, _REFRESH_DEBOUNCE_MS);
  }

  window.addEventListener("ptos:data-changed", function (e) {
    _clearCache();
    var scope = e && e.detail ? e.detail.scope : null;
    _scheduleRefresh(scope || null);
  });
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      _clearCache();
      _scheduleRefresh(null);
    }
  });
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) {
      _clearCache();
      _scheduleRefresh(null);
    }
  });

  var _STYLE_CSS = [
    ".ph-widget{position:relative;}",
    ".ph-head{display:flex;align-items:center;gap:10px;padding:10px 14px 0;}",
    ".ph-title{font-size:14px;font-weight:700;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}",
    ".ph-link{font-size:12px;color:var(--accent);text-decoration:none;white-space:nowrap;}",
    ".ph-link:hover{text-decoration:underline;}",
    ".ph-refresh{border:1px solid var(--border);background:transparent;color:var(--sub);border-radius:6px;width:28px;height:24px;cursor:pointer;font-size:13px;line-height:1;}",
    ".ph-refresh:hover{color:var(--accent);border-color:var(--accent);}",
    ".ph-body{padding:8px 6px 6px;}",
    ".ph-state{color:var(--sub);font-size:13px;padding:8px 12px;}",
    ".ph-toast-slot{position:absolute;left:0;right:0;bottom:8px;display:flex;justify-content:center;pointer-events:none;z-index:20;}",
    ".ph-toast{pointer-events:auto;display:flex;gap:10px;align-items:center;background:var(--card);border:1px solid var(--border);border-radius:8px;box-shadow:0 6px 20px rgba(0,0,0,.18);padding:6px 12px;font-size:13px;}",
    ".ph-toast.error{border-color:var(--error);color:var(--error);}",
    ".ph-toast-btn{border:none;background:transparent;color:var(--accent);font-weight:700;cursor:pointer;font-size:13px;padding:0;}",
    ".ph-widget .todo-group-head{display:flex;justify-content:space-between;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;padding:8px 12px 2px;color:var(--sub);}",
    ".ph-widget .todo-group-count{color:var(--sub);font-weight:600;}",
    ".ph-widget .todo-add-bar{display:flex;gap:8px;padding:4px 12px 8px;}",
    ".ph-widget .todo-add-input{flex:1;min-width:0;border:1px solid var(--border);background:var(--bg);color:var(--text);border-radius:6px;padding:6px 8px;font-size:13px;}",
    ".ph-widget .todo-row{padding:5px 12px;}",
    ".ph-widget .todo-group + .todo-group{border-top:1px solid var(--border);}"
  ];

  function _ensureStyles() {
    if (document.querySelector("style[data-ph-style]")) return;
    var s = document.createElement("style");
    s.setAttribute("data-ph-style", "1");
    s.textContent = _STYLE_CSS.join("\n");
    document.head.appendChild(s);
  }

  function _toastIn(hostEl, msg, opts) {
    opts = opts || {};
    var slot = hostEl.querySelector(".ph-toast-slot");
    if (!slot) return;
    slot.innerHTML = "";
    var box = document.createElement("div");
    box.className = "ph-toast" + (opts.error ? " error" : "");
    var span = document.createElement("span");
    span.textContent = msg;
    box.appendChild(span);
    (opts.actions || []).forEach(function (a) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "ph-toast-btn";
      b.textContent = a.label;
      b.addEventListener("click", function () {
        slot.innerHTML = "";
        if (a.onClick) a.onClick();
      });
      box.appendChild(b);
    });
    slot.appendChild(box);
    var ttl = opts.timeout || ((opts.actions || []).length ? 8000 : 4000);
    setTimeout(function () {
      if (box.parentElement) box.parentElement.removeChild(box);
    }, ttl);
  }

  function _paintBody(el, data, ctx, interactive) {
    el.innerHTML = "";
    var impl = implFor(data && data.kind);
    if (impl && impl.render) {
      impl.render(el, data, ctx);
      return;
    }
    if (typeof window.embedRenderBody === "function") {
      window.embedRenderBody(el, data);
      return;
    }
    if (typeof renderResult === "function") {
      el.innerHTML = renderResult(data);
    } else {
      el.innerHTML = "";
    }
  }

  function mount(el, spec, opts) {
    if (!el) return null;
    opts = opts || {};
    _ensureStyles();
    var body = (typeof spec === "string" && spec) || el.getAttribute("data-body") || "";
    var interactive = !!(opts.interactive || el.getAttribute("data-interactive") === "1");
    if (interactive && window.PtosToml && typeof window.PtosToml.parse === "function") {
      try {
        if (window.PtosToml.parse(body).live === false) interactive = false;
      } catch (e) {}
    }
    var hostName = opts.host || el.getAttribute("data-widget-host") || "page";

    if (el._phWidget) el._phWidget.destroy();

    el.classList.add("ph-widget");
    var fullSize = opts.size === "full";
    if (fullSize) el.classList.add("ph-widget-full");
    el.innerHTML =
      '<div class="ph-head">' +
        '<span class="ph-title"></span>' +
        '<a class="ph-link" hidden>Open →</a>' +
        '<button type="button" class="ph-refresh" title="Refresh" aria-label="Refresh">⟳</button>' +
      '</div>' +
      '<div class="ph-body"><div class="ph-state">Loading widget…</div></div>' +
      '<div class="ph-toast-slot"></div>';

    var titleEl = el.querySelector(".ph-title");
    var linkEl = el.querySelector(".ph-link");
    var refreshBtn = el.querySelector(".ph-refresh");
    var bodyEl = el.querySelector(".ph-body");
    if (fullSize) {
      var chrome = el.querySelector(".ph-head");
      if (chrome) chrome.remove();
    }
    var destroyed = false;
    var sub = null;
    var current = null;
    var listeners = [];

    function on(node, type, fn) {
      node.addEventListener(type, fn);
      listeners.push([node, type, fn]);
    }

    var ctx = {
      host: hostName,
      size: fullSize ? "full" : "card",
      interactive: interactive,
      context: opts.context || null,
      time: opts.time != null ? opts.time : (el.getAttribute("data-time") || null),
      refresh: function () { return handle.refresh(); },
      notifyChange: opts.notifyChange || function () {},
      toast: function (msg, toastOpts) { _toastIn(el, msg, toastOpts); }
    };

    function paint(data) {
      current = data;
      handle._phScopes = _scopesForKind(data && data.kind);
      titleEl.textContent = data.title || data.name || _nameOf(body) || "Widget";
      if (ctx.context && ctx.context.apply_time && TIME_AWARE[data.kind]) {
        var badge = document.createElement("span");
        badge.className = "ph-time-badge";
        badge.title = "Inherited from this page's time window";
        badge.textContent = "Time: " + timeWindowLabel(ctx.context);
        badge.style.cssText = "display:inline-block;margin-left:8px;padding:2px 7px;border:1px solid var(--border);border-radius:999px;color:var(--sub);font-size:11px;font-weight:500;vertical-align:middle";
        titleEl.appendChild(badge);
      }
      if (data.link) {
        linkEl.setAttribute("href", data.link);
        linkEl.hidden = false;
      } else {
        linkEl.removeAttribute("href");
        linkEl.hidden = true;
      }
      if (sub && sub.destroy) { try { sub.destroy(); } catch (e) {} }
      sub = null;
      bodyEl.innerHTML = "";
      var impl = implFor(data && data.kind);
      if (interactive && impl && impl.mount) {
        try {
          sub = impl.mount(bodyEl, data, ctx) || null;
        } catch (e) {
          if (typeof errorCard === "function") bodyEl.innerHTML = errorCard(String(e));
          return;
        }
      } else {
        _paintBody(bodyEl, data, ctx, interactive);
      }
    }

    function load(force) {
      if (destroyed) return Promise.resolve();
      bodyEl.innerHTML = '<div class="ph-state">Loading widget…</div>';
      return _fetch(body, force, ctx.context).then(function (res) {
        if (destroyed) return;
        if (!res.ok) {
          bodyEl.innerHTML = typeof errorCard === "function"
            ? errorCard(res.error)
            : '<div class="msg msg-error">' + _esc(res.error) + "</div>";
          var nm = _nameOf(body);
          if (nm && !titleEl.textContent) titleEl.textContent = nm;
          return;
        }
        paint(res.data);
      });
    }

    var handle = {
      el: el,
      ctx: ctx,
      data: function () { return current; },
      refresh: function () { return load(true); },
      setSpec: function (nextBody, nextContext) {
        if (typeof nextBody === "string") body = nextBody;
        if (arguments.length > 1) {
          ctx.context = nextContext || null;
          ctx.time = nextContext && nextContext.time || null;
        }
        return load(true);
      },
      destroy: function () {
        destroyed = true;
        var i = _live.indexOf(handle);
        if (i !== -1) _live.splice(i, 1);
        if (sub && sub.destroy) { try { sub.destroy(); } catch (e) {} }
        sub = null;
        listeners.forEach(function (l) {
          try { l[0].removeEventListener(l[1], l[2]); } catch (e) {}
        });
        listeners = [];
        el.classList.remove("ph-widget");
        el.classList.remove("ph-widget-full");
        el.innerHTML = "";
        delete el._phWidget;
      }
    };

    on(refreshBtn, "click", function () { handle.refresh(); });

    el._phWidget = handle;
    _live.push(handle);
    if (opts.error) {
      bodyEl.innerHTML = typeof errorCard === "function"
        ? errorCard(opts.error)
        : '<div class="msg msg-error">' + _esc(opts.error) + "</div>";
      var enm = _nameOf(body);
      if (enm && !titleEl.textContent) titleEl.textContent = enm;
    } else if (opts.data) {
      paint(opts.data);
    } else {
      load(false);
    }
    return handle;
  }

  function mountBatch(items, opts) {
    opts = opts || {};
    if (!items || !items.length) return Promise.resolve([]);
    var bodies = items.map(function (it) { return it.body; });
    var seen = {};
    var unique = [];
    bodies.forEach(function (b) {
      if (!seen[b]) { seen[b] = true; unique.push(b); }
    });
    var payload = {
      items: unique.map(function (b, i) { return { id: i, body: b }; })
    };
    if (opts.context) payload.context = opts.context;
    return _post("/api/widgets/resolve", payload).then(function (d) {
      var byBody = {};
      if (d && d.ok && d.results) {
        unique.forEach(function (b, i) {
          var res = d.results[i];
          if (res && res.ok) {
            _cache[_cacheKey(b, opts.context)] = res.data;
            byBody[b] = { ok: true, data: res.data };
          } else {
            byBody[b] = { ok: false, error: (res && res.error) || "Failed to load widget" };
          }
        });
      } else {
        unique.forEach(function (b) {
          byBody[b] = { ok: false, error: (d && d.error) || "Failed to load widget" };
        });
      }
      // opts.lazy defers below-the-fold mounts on a long page (the home
      // note): only > 8 widgets AND a real IntersectionObserver; each
      // deferred item mounts the first time it approaches the viewport.
      var lazy = !!opts.lazy && items.length > 8 &&
        typeof IntersectionObserver === "function";
      var io = lazy ? new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (!en.isIntersecting) return;
          var t = en.target;
          io.unobserve(t);
          var rec = t && t._phPending;
          if (!rec) return;
          delete t._phPending;
          mount(t, rec.body, rec.mopts);
        });
      }, { rootMargin: "200px" }) : null;
      var out = [];
      items.forEach(function (it) {
        var r = byBody[it.body] || { ok: false, error: "Failed to load widget" };
        var mopts = {};
        for (var k in opts) {
          if (Object.prototype.hasOwnProperty.call(opts, k)) mopts[k] = opts[k];
        }
        delete mopts.lazy;
        for (var k2 in (it.opts || {})) {
          if (Object.prototype.hasOwnProperty.call(it.opts, k2)) mopts[k2] = it.opts[k2];
        }
        if (r.ok) mopts.data = r.data;
        else mopts.error = r.error;
        var below = io && it.el && it.el.getBoundingClientRect &&
          it.el.getBoundingClientRect().top >= (window.innerHeight || 0);
        if (below) {
          it.el._phPending = { body: it.body, mopts: mopts };
          io.observe(it.el);
          out.push(null);
          return;
        }
        out.push(mount(it.el, it.body, mopts));
      });
      return out;
    }).catch(function (e) {
      return items.map(function (it) {
        return mount(it.el, it.body, {
          host: opts.host, interactive: !!it.interactive, error: String(e)
        });
      });
    });
  }

  function mountAll(root, opts) {
    root = root || document;
    if (!root.querySelectorAll) return [];
    var out = [];
    var nodes = root.querySelectorAll("[data-ptos-widget]");
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i]._phWidget) continue;
      out.push(mount(nodes[i], null, opts));
    }
    return out;
  }

  // ── kind registrations (Phase 1 interactive kinds) ─────────────────────────
  // threshold and due need no mount: their interactivity is navigation, and
  // renderThresholdResult / renderDue build the links themselves.

  register("todo", {
    render: function (el, data) {
      el.innerHTML = renderTodo(data);
    },
    mount: function (el, data, ctx) {
      var evts = [];
      function on(node, type, fn) {
        node.addEventListener(type, fn);
        evts.push([node, type, fn]);
      }

      function undo(lineNo, raw) {
        _post("/todo/undo", { line_no: lineNo, expect: raw }).then(function (res) {
          if (!res || !res.ok) {
            ctx.toast((res && res.error) || "Could not undo", { error: true });
            return;
          }
          ctx.refresh();
        });
      }

      function complete(row) {
        var lineNo = parseInt(row.getAttribute("data-line"), 10);
        var raw = row.getAttribute("data-raw") || "";
        if (isNaN(lineNo)) return;
        _post("/todo/complete", { line_no: lineNo, expect: raw }).then(function (res) {
          if (!res || !res.ok) {
            ctx.toast((res && res.error) || "Could not complete", { error: true });
            return;
          }
          row.style.opacity = "0.45";
          if (res.done_line_no != null) {
            ctx.toast("Done", {
              actions: [{
                label: "Undo",
                onClick: function () { undo(res.done_line_no, res.done_raw || ""); }
              }]
            });
          } else {
            ctx.toast("Done");
          }
          ctx.refresh();
        });
      }

      function addTask() {
        var input = el.querySelector(".todo-add-input");
        if (!input) return;
        var text = (input.value || "").trim();
        if (!text) { input.focus(); return; }
        _post("/todo/add", { text: text }).then(function (res) {
          if (!res || !res.ok) {
            ctx.toast((res && res.error) || "Could not add", { error: true });
            return;
          }
          ctx.refresh();
        });
      }

      el.innerHTML = renderTodo(data);
      on(el, "click", function (e) {
        if (!e.target) return;
        var chk = e.target.closest && e.target.closest("[data-todo-act]");
        if (chk && el.contains(chk)) {
          var row = chk.closest(".todo-row");
          if (!row) return;
          if (chk.getAttribute("data-todo-act") === "undo") {
            var uln = parseInt(row.getAttribute("data-line"), 10);
            if (!isNaN(uln)) undo(uln, row.getAttribute("data-raw") || "");
            return;
          }
          complete(row);
          return;
        }
        if (e.target.classList && e.target.classList.contains("todo-add-btn")) {
          addTask();
        }
      });
      on(el, "keydown", function (e) {
        if (e.key !== "Enter") return;
        if (e.target && e.target.classList &&
            e.target.classList.contains("todo-add-input")) {
          e.preventDefault();
          addTask();
        }
      });

      return {
        destroy: function () {
          evts.forEach(function (x) {
            try { x[0].removeEventListener(x[1], x[2]); } catch (e) {}
          });
          evts = [];
        }
      };
    }
  });

  register("records", {
    render: function (el, data) {
      el.innerHTML = renderRecordsStatic(data);
    },
    mount: function (el, data, ctx) {
      el.innerHTML = "";
      var wrap = document.createElement("div");
      el.appendChild(wrap);
      var rt = new RecordTable({
        container: wrap,
        returnTo: data.link || undefined,
        enableBulk: true,
        fieldTypes: data.field_types || undefined,
        exportName: data.export_name || "widget_records",
        onRefresh: function () { ctx.refresh(); }
      });
      rt.render(data);
      return {
        destroy: function () {
          try { rt.destroy(); } catch (e) {}
          if (wrap.parentElement) wrap.parentElement.removeChild(wrap);
        }
      };
    }
  });

  register("habit", {
    render: function (el, data) {
      el.innerHTML = renderHabit(data);
    },
    mount: function (el, data, ctx) {
      var evts = [];
      function on(node, type, fn) {
        node.addEventListener(type, fn);
        evts.push([node, type, fn]);
      }
      el.innerHTML = renderHabit(data);
      var card = el.querySelector(".card");
      var toggleable = card && card.getAttribute("data-toggleable") === "1";
      if (toggleable) {
        on(el, "keydown", function (e) {
          var td = e.target && e.target.closest && e.target.closest("td[data-date]");
          if (td && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            td.click();
          }
        });
        on(el, "click", function (e) {
          var td = e.target && e.target.closest && e.target.closest("td[data-date]");
          if (!td || !el.contains(td)) return;
          var date = td.getAttribute("data-date");
          if (!date) return;
          _post("/api/habit/toggle", {
            habit_name: data.habit_name,
            date: date
          }).then(function (res) {
            if (!res || !res.ok) {
              ctx.toast((res && res.error) || "Could not toggle day", { error: true });
              return;
            }
            td.setAttribute("data-present", res.present ? "1" : "0");
            td.classList.toggle("cnt", !!res.present);
            var st = el.querySelector('[data-stat="streak"]');
            if (st && res.streak != null) st.textContent = String(res.streak);
            var dy = el.querySelector('[data-stat="days"]');
            if (dy && res.days_done != null) {
              dy.textContent = res.days_done + " of " +
                (data.total_days == null ? "" : data.total_days) + " days";
            }
          });
        });
      }
      return {
        destroy: function () {
          evts.forEach(function (x) {
            try { x[0].removeEventListener(x[1], x[2]); } catch (e) {}
          });
          evts = [];
        }
      };
    }
  });

  window.PtosWidgets = {
    register: register,
    mount: mount,
    mountAll: mountAll,
    mountBatch: mountBatch,
    kinds: function () { return Object.keys(REG); }
  };
})();
