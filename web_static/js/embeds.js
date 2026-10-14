// embeds.js — mounts live widgets inside the markdown preview.
//
// A fenced ```ptos TOML block in a note/journal becomes a live widget:
// the mounter replaces the <pre> with a card whose body is fetched from
// POST /api/embed/resolve. Widget bodies are rendered by the shared
// helpers in widgets.js (loaded before this file).
//
// The preview is a READ-ONLY render of the finished page. It shows the
// widget's title, its "Open →" link back to the owning page, and the
// rendered body — no move, no edit, no drag. Every edit / move / add
// control lives in Blocks mode (md_blocks.js), which owns the text source,
// so keeping a second copy of those buttons here only created two code
// paths for the same job. This is why mountEmbeds takes the pane alone:
// there is no source to write back to.
//
// Also exports three primitives reused by Blocks mode (md_blocks.js):
// window.embedRegions(src) → [{start,end}] line spans of each fence,
// window.embedFetch(body, force) → Promise<{ok, data|error}> (resolve +
// cache) and window.embedRenderBody(bodyEl, data) → paints the body with
// the shared widgets.js renderers.
(function () {
  var _cache = {};

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

  function embedFetch(body, force) {
    if (!force && _cache.hasOwnProperty(body)) {
      return Promise.resolve({ ok: true, data: _cache[body] });
    }
    return fetch("/api/embed/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: body })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (!d || !d.ok) {
        return { ok: false, error: (d && d.error) || "Failed to load widget" };
      }
      _cache[body] = d.data;
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
    if (_cache.hasOwnProperty(body)) {
      _paint(container, _cache[body]);
      return;
    }
    container.className = "md-embed";
    container.innerHTML = '<div class="md-embed-loading">Loading widget…</div>';
    embedFetch(body, false).then(function (res) {
      if (!res.ok) { _paintError(container, res.error); return; }
      _paint(container, res.data);
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

  function _paint(container, data) {
    container.className = "md-embed";
    var title = data.title || data.name || "";
    var link = data.link
      ? '<a class="md-embed-link" href="' + esc(data.link) + '">Open →</a>'
      : "";
    container.innerHTML =
      '<div class="md-embed-head">' +
        '<span class="md-embed-title">' + esc(title) + '</span>' + link +
      '</div>' +
      '<div class="md-embed-body"></div>';
    var bodyEl = container.querySelector(".md-embed-body");
    if (bodyEl) embedRenderBody(bodyEl, data);
  }

  window.mountEmbeds = function (pane) {
    if (!pane) return;
    var blocks = pane.querySelectorAll("pre > code.language-ptos");
    Array.prototype.forEach.call(blocks, function (code) {
      var pre = code.parentElement;
      if (!pre || pre.getAttribute("data-embed") === "1") return;
      var body = code.textContent || "";
      pre.setAttribute("data-embed", "1");
      var container = document.createElement("div");
      container.className = "md-embed";
      pre.parentNode.replaceChild(container, pre);
      _resolveEmbed(container, body);
    });
  };
})();
