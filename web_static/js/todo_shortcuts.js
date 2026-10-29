(function () {
  "use strict";

  function isTypingTarget(el) {
    if (!el) return false;
    var tag = (el.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return true;
    if (el.isContentEditable) return true;
    return false;
  }

  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    var active = document.activeElement;

    if (e.key === "Escape") {
      var openModal = document.querySelector(".modal-overlay.open, .thr-modal.open, .field-popup.open");
      if (openModal) { openModal.classList.remove("open"); e.preventDefault(); }
      if (active && isTypingTarget(active)) active.blur();
      return;
    }

    if (isTypingTarget(active)) return;

    if (e.key === "n" || e.key === "N") {
      var addInput = document.querySelector(".todo-add-input");
      if (addInput) { addInput.focus(); e.preventDefault(); }
    } else if (e.key === "/") {
      var search = document.getElementById("sidebar-search") || document.querySelector('input[name="q"]');
      if (search) { search.focus(); e.preventDefault(); }
    } else if (e.key === "?") {
      var help = document.getElementById("todo-help");
      if (help) { help.classList.toggle("open"); e.preventDefault(); }
    }
  });
})();
