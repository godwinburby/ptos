// Keep the shell's "last change" label ticking without a page reload.
//
// The server renders the initial text (no-JS / first paint). Each .last-change
// element carries data-epoch (seconds) and data-prefix; recompute the relative
// label from that absolute value so elapsed time advances on its own. Once the
// change is over a day old, the server's absolute date is left alone.
(function () {
  function relLabel(epoch) {
    var secs = Date.now() / 1000 - epoch;
    if (secs < 0 || secs < 60) return "just now";
    if (secs < 3600) return Math.floor(secs / 60) + " min ago";
    if (secs < 86400) {
      var hrs = Math.floor(secs / 3600);
      var mins = Math.floor((secs % 3600) / 60);
      return mins ? hrs + " hr " + mins + " min ago" : hrs + " hr ago";
    }
    return null;
  }

  function refresh() {
    var els = document.querySelectorAll(".last-change[data-epoch]");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var epoch = parseFloat(el.getAttribute("data-epoch"));
      if (!isFinite(epoch)) continue;
      var label = relLabel(epoch);
      if (label !== null) {
        el.textContent = (el.getAttribute("data-prefix") || "") + label;
      }
    }
  }

  refresh();
  setInterval(refresh, 30000);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) refresh();
  });
  window.addEventListener("pageshow", refresh);
})();
