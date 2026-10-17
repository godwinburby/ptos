// Per-device display size: a CSS `zoom` multiplier on <html>, stored in
// localStorage (key ptos.uiScale) so the phone and desktop keep different
// values — config.toml is synced by Syncthing, so a shared value would be
// wrong. The tiny head script in base.html applies the stored value before
// first paint; this file owns the API the Settings row and the sidebar
// A-/A+ stepper call. Values are a fixed allowlist (1, 1.15, 1.3, 1.5) and
// the whole feature stands down on browsers without CSS zoom support: the
// stored value is ignored and every control hides itself.
(function () {
  var KEY = "ptos.uiScale";
  var SIZES = [1, 1.15, 1.3, 1.5];

  function supported() {
    try {
      return !!(window.CSS && CSS.supports && CSS.supports("zoom", "1.2"));
    } catch (e) { return false; }
  }

  function getUiScale() {
    if (!supported()) return 1;
    var v = 1;
    try {
      var raw = parseFloat(localStorage.getItem(KEY));
      if (SIZES.indexOf(raw) > -1) v = raw;
    } catch (e) {}
    return v;
  }

  function highlight(v) {
    var btns = document.querySelectorAll(".uiscale-btn[data-scale]");
    for (var i = 0; i < btns.length; i++) {
      var on = parseFloat(btns[i].getAttribute("data-scale")) === v;
      if (on) btns[i].classList.add("active");
      else btns[i].classList.remove("active");
    }
    var lbl = document.getElementById("uiscale-label");
    if (lbl) lbl.textContent = Math.round(v * 100) + "%";
  }

  function setUiScale(v) {
    if (SIZES.indexOf(v) === -1) v = 1;
    if (!supported()) return getUiScale();
    try { localStorage.setItem(KEY, String(v)); } catch (e) {}
    document.documentElement.style.zoom = v === 1 ? "" : String(v);
    highlight(v);
    try {
      document.dispatchEvent(new CustomEvent("ptos:uiscale",
        { detail: { scale: v } }));
    } catch (e) {}
    return v;
  }

  function stepUiScale(dir) {
    var i = SIZES.indexOf(getUiScale());
    if (i === -1) i = 0;
    i = Math.min(SIZES.length - 1, Math.max(0, i + dir));
    return setUiScale(SIZES[i]);
  }

  function wire() {
    if (!supported()) {
      var blocks = document.querySelectorAll("[data-uiscale]");
      for (var i = 0; i < blocks.length; i++) {
        blocks[i].style.display = "none";
      }
      return;
    }
    var btns = document.querySelectorAll(".uiscale-btn[data-scale]");
    for (var j = 0; j < btns.length; j++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          setUiScale(parseFloat(btn.getAttribute("data-scale")));
        });
      })(btns[j]);
    }
    highlight(getUiScale());
  }

  window.getUiScale = getUiScale;
  window.setUiScale = setUiScale;
  window.stepUiScale = stepUiScale;
  wire();
})();
