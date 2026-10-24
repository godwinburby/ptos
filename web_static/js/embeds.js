// embeds.js — mounts live widgets inside the markdown preview.
//
// A fenced ```ptos TOML block in a note/journal becomes a live widget:
// the mounter replaces the <pre> with a card whose body is fetched from
// POST /api/embed/resolve. Widget bodies are rendered by the shared
// helpers in widgets.js (loaded before this file).
//
// Widgets mount interactively by default; `live = false` uses the static
// renderer. Neither path edits or autosaves the markdown source. Reordering
// and widget configuration stay in Blocks mode (md_blocks.js), which owns
// the source text; mountEmbeds therefore only needs the preview pane.
//
// Also exports three primitives reused by Blocks mode (md_blocks.js):
// window.embedRegions(src) → [{start,end}] line spans of each fence,
// window.embedFetch(body, force) → Promise<{ok, data|error}> (resolve +
// cache) and window.embedRenderBody(bodyEl, data) → paints the body with
// the shared widgets.js renderers.
(function () {
  var _cache = {};
  var _timePickerMounted = false;
  var TIME_AWARE = {
    query: 1, metric: 1, dashboard: 1, threshold: 1, board: 1,
    habit: 1, calendar: 1, records: 1
  };

  function embedRegions(src) {
    var lines = String(src || "").split(/\r\n|\n/);
    var out = [];
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].trim() !== "```ptos") continue;
      var start = i;
      var end = i;
      for (var j = i + 1; j < lines.length; j++) {
        if (lines[j].trim() === "```") { end = j; i = j; break; }
        end = j;
      }
      out.push({ start: start, end: end });
    }
    return out;
  }

  window.embedRegions = embedRegions;

  // ── Shared primitives ─────────────────────────────────────────────────
  // embedFetch / embedRenderBody are exported for views that build their own
  // card chrome (Blocks mode) but need the same resolve+cache and the same
  // body painter as the preview cards, so the two can never drift.

  function _timeContext() {
    var params = new URLSearchParams(window.location.search || "");
    var from = params.get("from_date") || "";
    var time = params.get("time") || "";
    var custom = params.get("custom_time") || "";
    if (from || time === "range") {
      return { time: "range", from_date: from || null,
               to_date: params.get("to_date") || null, apply_time: true };
    }
    if (time === "year" || time === "month" || time === "date") {
      if (/^\d{4}(-\d{2}(-\d{2})?)?$/.test(custom)) {
        return { time: custom, apply_time: true };
      }
      return { time: "tm", apply_time: true };
    }
    return { time: time || "tm", apply_time: !!time };
  }

  window.embedTimeContext = _timeContext;

  function _cacheKey(body, context) {
    return String(body) + "\u0000" + JSON.stringify(context || {});
  }

  function embedFetch(body, force, context) {
    context = context || _timeContext();
    var key = _cacheKey(body, context);
    if (!force && _cache.hasOwnProperty(key)) {
      return Promise.resolve({ ok: true, data: _cache[key] });
    }
    return fetch("/api/embed/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: body, context: context })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (!d || !d.ok) {
        return { ok: false, error: (d && d.error) || "Failed to load widget" };
      }
      _cache[key] = d.data;
      return { ok: true, data: d.data };
    }).catch(function (e) {
      return { ok: false, error: String(e) };
    });
  }

  function embedRenderBody(bodyEl, data) {
    if (data.kind === "threshold") {
      bodyEl.innerHTML = renderThresholdResult(data.thresholds || []);
    } else {
      bodyEl.innerHTML = renderResult(data);
    }
  }

  window.embedFetch = embedFetch;
  window.embedRenderBody = embedRenderBody;

  // ── Preview-only card painting ────────────────────────────────────────

  function _resolveEmbed(container, body) {
    container._body = body;
    var context = _timeContext();
    var key = _cacheKey(body, context);
    if (_cache.hasOwnProperty(key)) {
      _paint(container, _cache[key], body);
      return;
    }
    container.className = "md-embed";
    container.innerHTML = '<div class="md-embed-loading">Loading widget…</div>';
    embedFetch(body, false, context).then(function (res) {
      if (!container.isConnected) return;
      if (!res.ok) { _paintError(container, res.error); return; }
      _paint(container, res.data, body);
    });
  }

  // A broken embed still shows its name so you can tell which fence failed;
  // the fix happens in Blocks mode (✎ on that block).
  function _paintError(container, message) {
    container.className = "md-embed";
    var m = /name\s*=\s*"([^"]*)"/.exec(container._body || "");
    container.innerHTML =
      '<div class="md-embed-head">' +
        '<span class="md-embed-title">' + esc(m ? m[1] : "Widget") + '</span>' +
      '</div>' +
      '<div class="msg msg-error">' + esc(message) + '</div>';
  }

  function _isLive(body) {
    if (!window.PtosToml || typeof window.PtosToml.parse !== "function") return false;
    try { return window.PtosToml.parse(body).live !== false; }
    catch (e) { return false; }
  }

  function _paint(container, data, body) {
    if (_isLive(body) && window.PtosWidgets &&
        typeof window.PtosWidgets.mount === "function") {
      container.className = "md-embed md-embed-live";
      container.setAttribute("data-ptos-widget", "1");
      container.setAttribute("data-interactive", "1");
      container._ptosLiveHandle = window.PtosWidgets.mount(container, body, {
        host: "note", interactive: true, data: data,
        context: _timeContext()
      });
      var pane = container.closest && container.closest("#preview-pane");
      if (pane) {
        pane._ptosLiveHandles = pane._ptosLiveHandles || [];
        if (container._ptosLiveHandle) pane._ptosLiveHandles.push(container._ptosLiveHandle);
      }
      return;
    }
    container.className = "md-embed";
    var title = data.title || data.name || "";
    var context = _timeContext();
    var timeBadge = context.apply_time && TIME_AWARE[data.kind]
      ? '<span class="md-embed-time" title="Inherited from this page\'s time window">Time: ' +
        esc(window.PtosWidgetTimeLabel
          ? window.PtosWidgetTimeLabel(context) : context.time) + '</span>'
      : "";
    var link = data.link
      ? '<a class="md-embed-link" href="' + esc(data.link) + '">Open →</a>'
      : "";
    container.innerHTML =
      '<div class="md-embed-head">' +
        '<span class="md-embed-title">' + esc(title) + '</span>' + timeBadge + link +
      '</div>' +
      '<div class="md-embed-body"></div>';
    var bodyEl = container.querySelector(".md-embed-body");
    if (bodyEl) embedRenderBody(bodyEl, data);
  }

  window.unmountEmbeds = function (pane) {
    var handles = pane && pane._ptosLiveHandles;
    if (!handles) return;
    handles.forEach(function (handle) {
      if (handle && typeof handle.destroy === "function") handle.destroy();
    });
    pane._ptosLiveHandles = [];
  };

  window.mountEmbeds = function (pane) {
    if (!pane) return;
    _timePickerMounted = false;
    var blocks = pane.querySelectorAll("pre > code.language-ptos");
    Array.prototype.forEach.call(blocks, function (code) {
      var pre = code.parentElement;
      if (!pre || pre.getAttribute("data-embed") === "1") return;
      var body = code.textContent || "";
      pre.setAttribute("data-embed", "1");
      var container = document.createElement("div");
      container.className = "md-embed";
      pre.parentNode.replaceChild(container, pre);
      var isTimePicker = false;
      try {
        isTimePicker = !!(window.PtosToml &&
          String(window.PtosToml.parse(body).view || "").toLowerCase() === "time_picker");
      } catch (e) {}
      if (isTimePicker && _timePickerMounted) {
        container.className = "md-embed md-embed-error";
        container.innerHTML = '<div class="msg msg-error">Only one time window picker is allowed on a Markdown page.</div>';
        return;
      }
      if (isTimePicker) _timePickerMounted = true;
      _resolveEmbed(container, body);
    });
  };
})();
