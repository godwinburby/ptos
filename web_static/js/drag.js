// Shared drag-and-drop reorder helper
// Usage: _makeDraggable(chipElement, itemsArray, index, rerenderFn, cssSelector)
var _dragIdx = null;
var _touchOverEl = null;

function _makeDraggable(chip, items, idx, rerender, chipSelector) {
  chip.draggable = true;
  chip.dataset.index = idx;

  function clearDrag() {
    _dragIdx = null;
    _touchOverEl = null;
    document.querySelectorAll(chipSelector).forEach(function(c) {
      c.classList.remove("dragging", "drag-over");
    });
  }

  // Mouse drag-and-drop
  chip.addEventListener("dragstart", function() {
    _dragIdx = idx;
    this.classList.add("dragging");
  });
  chip.addEventListener("dragover", function(e) {
    e.preventDefault();
    this.classList.add("drag-over");
  });
  chip.addEventListener("dragleave", function() {
    this.classList.remove("drag-over");
  });
  chip.addEventListener("drop", function(e) {
    e.preventDefault();
    if (_dragIdx === null || _dragIdx === idx) return;
    var item = items.splice(_dragIdx, 1)[0];
    items.splice(idx, 0, item);
    rerender();
  });
  chip.addEventListener("dragend", clearDrag);

  // Touch drag-and-drop (mobile)
  chip.addEventListener("touchstart", function() {
    _dragIdx = idx;
    this.classList.add("dragging");
  }, { passive: true });
  chip.addEventListener("touchmove", function(e) {
    e.preventDefault();
    var el = document.elementFromPoint(e.touches[0].clientX, e.touches[0].clientY);
    if (!el) return;
    var chipEl = el.closest(chipSelector);
    if (!chipEl) return;
    var targetIdx = parseInt(chipEl.dataset.index);
    if (targetIdx === _dragIdx) {
      if (_touchOverEl) { _touchOverEl.classList.remove("drag-over"); _touchOverEl = null; }
      return;
    }
    if (chipEl !== _touchOverEl) {
      if (_touchOverEl) _touchOverEl.classList.remove("drag-over");
      _touchOverEl = chipEl;
      chipEl.classList.add("drag-over");
    }
  }, { passive: false });
  chip.addEventListener("touchend", function(e) {
    if (_dragIdx === null) return;
    var el = document.elementFromPoint(e.changedTouches[0].clientX, e.changedTouches[0].clientY);
    if (el) {
      var chipEl = el.closest(chipSelector);
      if (chipEl && chipEl.dataset.index !== undefined) {
        var targetIdx = parseInt(chipEl.dataset.index);
        if (targetIdx !== _dragIdx) {
          var item = items.splice(_dragIdx, 1)[0];
          items.splice(targetIdx, 0, item);
          rerender();
        }
      }
    }
    clearDrag();
  }, { passive: true });
  chip.addEventListener("touchcancel", clearDrag, { passive: true });
}
