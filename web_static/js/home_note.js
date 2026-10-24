// home_note.js — render the home page from the home note (Home.md).
//
// The note is split into text runs and ```ptos widget fences
// (window.embedRegions). Text runs render through the shared markdown
// pipeline (preprocessLinks + window.renderMarkdown — the same
// DOMPurify-sanitized path the notes preview uses); widgets resolve in
// ONE batch POST to /api/widgets/resolve with the page's time context,
// so `time = "@home"` in a fence follows the home time picker here and
// resolves "tm" everywhere else (the server does the substitution).
//
// The note is the SOURCE: this module never writes it back. Edit mode
// and save arrive with Phase 4 (D5). `span`/`hide_on` are layout keys —
// applied here as classes, ignored by the resolver.
//
// Pure helpers (no DOM) live on window.PtosHomeNote so the node test
// suite (tests/js/home_note.test.js) can exercise them directly.
(function () {
  "use strict";

  // ── pure helpers (node-testable) ─────────────────────────────────────

  function split(src) {
    var lines = String(src == null ? "" : src).split(/\r\n|\n/);
    var regions = (typeof window !== "undefined" && window.embedRegions)
      ? window.embedRegions(src) : [];
    var rmap = {};
    (regions || []).forEach(function (r) { rmap[r.start] = r; });
    var out = [];
    var textBuf = [];
    function flushText() {
      if (!textBuf.length) return;
      var t = textBuf.join("\n");
      if (/\S/.test(t)) out.push({ type: "text", text: t });
      textBuf = [];
    }
    for (var i = 0; i < lines.length; i++) {
      if (Object.prototype.hasOwnProperty.call(rmap, i)) {
        flushText();
        var r = rmap[i];
        out.push({
          type: "widget",
          body: lines.slice(r.start + 1, r.end).join("\n")
        });
        i = r.end;
      } else {
        textBuf.push(lines[i]);
      }
    }
    flushText();
    return out;
  }

  function homeContext(search) {
    var params = new URLSearchParams(String(search == null ? "" : search));
    var from = params.get("from_date") || null;
    var timeParam = params.get("time");
    var custom = params.get("custom_time") || "";
    if (from) {
      return { time: "range", from_date: from,
               to_date: params.get("to_date") || null };
    }
    if (timeParam === "custom" || timeParam === "year" ||
        timeParam === "month" || timeParam === "date") {
      if (custom && /^\d{4}(-\d{2}(-\d{2})?)?$/.test(custom)) {
        return { time: custom };
      }
      return { time: "tm" };
    }
    return { time: timeParam || "tm" };
  }

  function hasHomeTimeSelection(search) {
    var params = new URLSearchParams(String(search == null ? "" : search));
    return !!(params.get("from_date") || params.get("time"));
  }

  // Name-swap for ?dashboard=/?due=: only when the server validated the
  // value (it is in source.params) AND the widget still carries the
  // generated name (`from`). Returns the input object when nothing
  // changed, so the caller can keep the original body text byte-identical.
  function applyParamNames(spec, params) {
    if (!spec || typeof spec !== "object") return spec;
    if (!params || typeof params !== "object") return spec;
    var changed = false;
    var out = {};
    for (var k in spec) {
      if (Object.prototype.hasOwnProperty.call(spec, k)) out[k] = spec[k];
    }
    ["due", "dashboard"].forEach(function (kind) {
      var p = params[kind];
      if (!p || typeof p !== "object") return;
      if (out.view === kind && p.from && p.to != null &&
          out.name === p.from && String(p.to) !== String(p.from)) {
        out.name = p.to;
        changed = true;
      }
    });
    return changed ? out : spec;
  }

  function applyHomeTime(spec, context) {
    if (!spec || typeof spec !== "object" || !context ||
        !context.apply_time) return spec;
    var kind = String(spec.view || "").toLowerCase();
    var timeKinds = ["query", "group", "pivot", "trend", "metric",
                     "dashboard", "threshold", "board", "habit",
                     "calendar", "records"];
    if (timeKinds.indexOf(kind) === -1) return spec;
    var out = {};
    for (var k in spec) {
      if (Object.prototype.hasOwnProperty.call(spec, k)) out[k] = spec[k];
    }
    out.time = context.time || "tm";
    delete out.from_date;
    delete out.to_date;
    if (out.time === "range") {
      if (context.from_date) out.from_date = context.from_date;
      if (context.to_date) out.to_date = context.to_date;
    }
    return out;
  }

  // span / hide_on layout hints parsed from the fence body. Pure: no DOM
  // classes here — the boot code maps them onto the wrapper element.
  function widgetAttrs(bodyText) {
    var spec = null;
    if (typeof window !== "undefined" && window.PtosToml &&
        window.PtosToml.parse) {
      try { spec = window.PtosToml.parse(String(bodyText == null ? "" : bodyText)); }
      catch (e) { spec = null; }
    }
    var attrs = { span: 1, hideOn: [] };
    if (spec && typeof spec === "object") {
      if (spec.span === 2) attrs.span = 2;
      var hide = spec.hide_on;
      if (typeof hide === "string") hide = [hide];
      if (Object.prototype.toString.call(hide) === "[object Array]") {
        hide.forEach(function (h) {
          if (h === "phone" || h === "desktop") attrs.hideOn.push(h);
        });
      }
    }
    return attrs;
  }

  var helpers = { split: split, homeContext: homeContext,
                  applyParamNames: applyParamNames,
                  applyHomeTime: applyHomeTime, widgetAttrs: widgetAttrs };
  if (typeof window !== "undefined") window.PtosHomeNote = helpers;

  // ── DOM boot ─────────────────────────────────────────────────────────

  if (typeof document === "undefined") return;

  function parseSource() {
    var el = document.getElementById("home-note-source");
    if (!el) return null;
    try {
      var d = JSON.parse(el.textContent || "");
      return (d && typeof d === "object") ? d : null;
    } catch (e) { return null; }
  }

  function renderText(text) {
    var md = String(text == null ? "" : text);
    if (typeof window.preprocessLinks === "function") {
      md = window.preprocessLinks(md);
    }
    var html = "";
    if (typeof window.renderMarkdown === "function") {
      try { html = window.renderMarkdown(md); } catch (e) { html = ""; }
    }
    if (!html) {
      var esc = document.createElement("div");
      esc.textContent = md;
      html = "<pre>" + esc.innerHTML + "</pre>";
    }
    var wrap = document.createElement("div");
    wrap.className = "home-text";
    wrap.innerHTML = html;
    return wrap;
  }

  function boot() {
    var source = parseSource();
    var host = document.getElementById("home");
    if (!source || !host) return;
    if (typeof window.PtosWidgets === "undefined" ||
        !window.PtosWidgets.mountBatch) return;
    var ctx = homeContext(window.location.search || "");
    ctx.apply_time = hasHomeTimeSelection(window.location.search || "");
    var items = [];
    var timePickerSeen = false;
    var frag = document.createDocumentFragment();
    split(source.content || "").forEach(function (c) {
      if (c.type === "text") {
        frag.appendChild(renderText(c.text));
        return;
      }
      var body = c.body;
      var isTimePicker = false;
      if (window.PtosToml && window.PtosToml.parse &&
          window.PtosToml.serialize) {
        try {
          var spec = window.PtosToml.parse(body);
          isTimePicker = String(spec.view || "").toLowerCase() === "time_picker";
          var swapped = applyParamNames(spec, source.params);
          var timed = applyHomeTime(swapped, ctx);
          if (timed !== spec) body = window.PtosToml.serialize(timed);
        } catch (e) { /* unparsable fence — resolve reports it */ }
      }
      var attrs = widgetAttrs(c.body);
      var run = document.createElement("div");
      run.className = "home-widget-run";
      if (attrs.span === 2) run.classList.add("home-span-2");
      if (attrs.hideOn.indexOf("phone") !== -1) {
        run.classList.add("ph-hide-on-phone");
      }
      if (attrs.hideOn.indexOf("desktop") !== -1) {
        run.classList.add("ph-hide-on-desktop");
      }
      var el = document.createElement("div");
      el.className = "home-widget";
      run.appendChild(el);
      frag.appendChild(run);
      if (isTimePicker && timePickerSeen) {
        el.className = "card msg msg-error";
        el.textContent = "Only one time window picker is allowed on a Markdown page.";
        return;
      }
      if (isTimePicker) timePickerSeen = true;
      items.push({ body: body, el: el });
    });
    host.innerHTML = "";
    host.appendChild(frag);
    window.PtosWidgets.mountBatch(items, {
      host: "home", interactive: true, context: ctx, lazy: true
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
