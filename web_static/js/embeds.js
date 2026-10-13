// embeds.js — mounts live widgets inside the markdown preview.
//
// A fenced ```ptos TOML block in a note/journal becomes a live widget:
// the mounter replaces the <pre> with a card whose body is fetched from
// POST /api/embed/resolve. Widget bodies are rendered by the shared
// helpers in widgets.js (loaded before this file).
//
// When the source <textarea> is available (mountEmbeds(pane, src, srcEl)),
// cards can be reordered: drag card A onto card B to swap the two fenced
// regions in the source text, or use the ▲/▼ buttons (touch-friendly).
// The new text is written back into the textarea and an `input` event is
// dispatched, so the preview re-renders and the debounced autosave follow
// the same path as typing. Prose between the two fences stays put; only
// the two regions move.
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

  function swapRegions(text, a, b) {
    var nl = text.indexOf("\r\n") !== -1 ? "\r\n" : "\n";
    var lines = text.split(/\r\n|\n/);
    var aSlice = lines.slice(a.start, a.end + 1);
    var bSlice = lines.slice(b.start, b.end + 1);
    if (a.start < b.start) {
      return lines.slice(0, a.start).concat(
        bSlice,
        lines.slice(a.end + 1, b.start),
        aSlice,
        lines.slice(b.end + 1)
      ).join(nl);
    }
    return lines.slice(0, b.start).concat(
      aSlice,
      lines.slice(b.end + 1, a.start),
      bSlice,
      lines.slice(a.end + 1)
    ).join(nl);
  }
  window.swapEmbedRegions = swapRegions;
  window.embedRegions = embedRegions;

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
        '<span class="md-embed-actions">' +
          '<button type="button" class="md-embed-move md-embed-move-up" title="Move widget up">▲</button>' +
          '<button type="button" class="md-embed-move md-embed-move-down" title="Move widget down">▼</button>' +
          link +
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
    var up = container.querySelector(".md-embed-move-up");
    var down = container.querySelector(".md-embed-move-down");
    if (container._srcEl && container._pane) {
      if (up) up.addEventListener("click", function () { _moveBy(container, -1); });
      if (down) down.addEventListener("click", function () { _moveBy(container, 1); });
    } else if (up) {
      up.parentNode.removeChild(up);
      down.parentNode.removeChild(down);
    }
  }

  function _widgetsOf(pane) {
    return pane ? Array.prototype.slice.call(pane.querySelectorAll(".md-embed")) : [];
  }

  function _swapWith(a, b) {
    var srcEl = a._srcEl;
    var pane = a._pane;
    if (!srcEl || !pane || !b || !b._srcEl) return;
    var text = srcEl.value == null ? "" : srcEl.value;
    var regions = embedRegions(text);
    var aIdx = _widgetsOf(pane).indexOf(a);
    var bIdx = _widgetsOf(pane).indexOf(b);
    if (aIdx === -1 || bIdx === -1) return;
    var ra = regions[a._idx];
    var rb = regions[b._idx];
    if (!ra || !rb) return;
    var next = swapRegions(text, ra, rb);
    if (next === text) return;
    srcEl.value = next;
    srcEl.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function _moveBy(container, delta) {
    var peers = _widgetsOf(container._pane);
    var i = peers.indexOf(container);
    var other = peers[i + delta];
    if (!other) return;
    _swapWith(container, other);
  }

  function _wireReorder(container, idx, srcEl, pane) {
    container._idx = idx;
    container._srcEl = srcEl;
    container._pane = pane;
    container.draggable = true;
    container.addEventListener("dragstart", function (e) {
      if (e.target.closest && e.target.closest(".md-embed-link,.md-embed-refresh,.md-embed-move")) {
        e.preventDefault();
        return;
      }
      window._mdDragEl = container;
      container.classList.add("dragging");
      try { e.dataTransfer.effectAllowed = "move"; } catch (err) {}
    });
    container.addEventListener("dragend", function () {
      if (window._mdDragEl === container) window._mdDragEl = null;
      container.classList.remove("dragging");
    });
    container.addEventListener("dragenter", function () {
      var dragEl = window._mdDragEl;
      if (!dragEl || dragEl === container) return;
      container._ov = (container._ov || 0) + 1;
      container.classList.add("drag-over");
    });
    container.addEventListener("dragleave", function () {
      container._ov = Math.max(0, (container._ov || 1) - 1);
      if (container._ov === 0) container.classList.remove("drag-over");
    });
    container.addEventListener("dragover", function (e) {
      var dragEl = window._mdDragEl;
      if (dragEl && dragEl !== container) {
        e.preventDefault();
        try { e.dataTransfer.dropEffect = "move"; } catch (err) {}
      }
    });
    container.addEventListener("drop", function (e) {
      e.preventDefault();
      container._ov = 0;
      container.classList.remove("drag-over");
      var dragEl = window._mdDragEl;
      if (!dragEl || dragEl === container) return;
      window._mdDragEl = null;
      dragEl.classList.remove("dragging");
      _swapWith(dragEl, container);
    });
  }

  window.mountEmbeds = function (pane, src, srcEl) {
    if (!pane) return;
    var regions = embedRegions(src);
    var blocks = pane.querySelectorAll("pre > code.language-ptos");
    var wired = regions.length === blocks.length;
    Array.prototype.forEach.call(blocks, function (code, idx) {
      var pre = code.parentElement;
      if (!pre || pre.getAttribute("data-embed") === "1") return;
      var body = code.textContent || "";
      pre.setAttribute("data-embed", "1");
      var container = document.createElement("div");
      container.className = "md-embed";
      pre.parentNode.replaceChild(container, pre);
      if (wired && srcEl) _wireReorder(container, idx, srcEl, pane);
      _resolveEmbed(container, body, false);
    });
  };
})();