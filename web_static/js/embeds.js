// embeds.js — mounts live widgets inside the markdown preview.
//
// A fenced ```ptos TOML block in a note/journal becomes a live widget:
// the mounter replaces the <pre> with a card whose body is fetched from
// POST /api/embed/resolve. Widget bodies are rendered by the shared
// helpers in widgets.js (loaded before this file).
(function () {
  var _cache = {};

  function _resolveEmbed(container, body, force) {
    if (!force && _cache.hasOwnProperty(body)) {
      _paint(container, body, _cache[body]);
      return;
    }
    container.className = "md-embed";
    container.innerHTML = '<div class="md-embed-loading">Loading widget…</div>';
    fetch("/api/embed/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: body })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (!d || !d.ok) {
        container.className = "md-embed";
        container.innerHTML = '<div class="msg msg-error">' +
          esc((d && d.error) || "Failed to load widget") + '</div>';
        return;
      }
      _cache[body] = d.data;
      _paint(container, body, d.data);
    }).catch(function (e) {
      container.className = "md-embed";
      container.innerHTML = '<div class="msg msg-error">' + esc(String(e)) + '</div>';
    });
  }

  function _paint(container, body, data) {
    container.className = "md-embed";
    var title = data.title || data.name || "";
    var link = data.link
      ? '<a class="md-embed-link" href="' + esc(data.link) + '">Open →</a>'
      : "";
    container.innerHTML =
      '<div class="md-embed-head">' +
        '<span class="md-embed-title">' + esc(title) + '</span>' +
        '<span class="md-embed-actions">' + link +
          '<button type="button" class="md-embed-refresh" title="Refresh widget">⟳</button>' +
        '</span>' +
      '</div>' +
      '<div class="md-embed-body"></div>';
    var bodyEl = container.querySelector(".md-embed-body");
    if (data.kind === "threshold") {
      bodyEl.innerHTML = renderThresholdResult(data.thresholds || []);
    } else {
      bodyEl.innerHTML = renderResult(data);
    }
    var btn = container.querySelector(".md-embed-refresh");
    if (btn) btn.addEventListener("click", function () { _resolveEmbed(container, body, true); });
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
      _resolveEmbed(container, body, false);
    });
  };
})();
