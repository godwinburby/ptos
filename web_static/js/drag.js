// Shared drag-and-drop reorder helper
// Usage: _makeDraggable(chipElement, itemsArray, index, rerenderFn, cssSelector)
var _dragIdx = null;
var _dragChip = null;
var _touchOverEl = null;

// Coordinate-aware hit test for touch gestures. Walks the whole element stack
// at the point (the top element is often a child or an overlay) and, when the
// page carries a CSS zoom (the per-device Display size setting), retries the
// point divided and multiplied by the zoom factor — Android's coordinate APIs
// have been inconsistent about which space clientX/clientY live in under zoom.
// Returns the first element matching selector, or null.
function _touchHit(x, y, selector) {
  var pts = [[x, y]];
  var z = 1;
  try { z = parseFloat(document.documentElement.style.zoom) || 1; } catch (e) {}
  if (z !== 1) { pts.push([x / z, y / z]); pts.push([x * z, y * z]); }
  for (var p = 0; p < pts.length; p++) {
    var stack = null;
    if (document.elementsFromPoint) {
      stack = document.elementsFromPoint(pts[p][0], pts[p][1]);
    } else {
      var one = document.elementFromPoint(pts[p][0], pts[p][1]);
      stack = one ? [one] : [];
    }
    for (var i = 0; i < stack.length; i++) {
      var el = stack[i].closest ? stack[i].closest(selector) : null;
      if (el) return el;
    }
  }
  return null;
}

function _makeDraggable(chip, items, idx, rerender, chipSelector) {
  chip.draggable = true;
  chip.dataset.index = idx;
  // Marks which items array this chip reorders — a drop onto a chip of a
  // different array (options of another field) must never splice our list.
  chip._dragItems = items;

  function clearDrag() {
    _dragIdx = null;
    _dragChip = null;
    _touchOverEl = null;
    document.querySelectorAll(chipSelector).forEach(function(c) {
      c.classList.remove("dragging", "drag-over");
    });
  }

  // Mouse drag-and-drop
  chip.addEventListener("dragstart", function() {
    _dragIdx = idx;
    _dragChip = chip;
    this.classList.add("dragging");
  });
  chip.addEventListener("dragover", function(e) {
    e.preventDefault();
    if (_dragChip && _dragChip._dragItems !== this._dragItems) return;
    this.classList.add("drag-over");
  });
  chip.addEventListener("dragleave", function() {
    this.classList.remove("drag-over");
  });
  chip.addEventListener("drop", function(e) {
    e.preventDefault();
    if (_dragIdx === null || _dragIdx === idx) return;
    if (_dragChip && _dragChip._dragItems !== this._dragItems) return;
    var item = items.splice(_dragIdx, 1)[0];
    items.splice(idx, 0, item);
    rerender();
  });
  chip.addEventListener("dragend", clearDrag);

  // Touch drag-and-drop (mobile). A touch that starts on an interactive
  // child (the chip's delete button, a link, an input) is left alone so
  // taps keep working — only the chip body arms a drag.
  chip.addEventListener("touchstart", function(e) {
    if (e.target.closest &&
        e.target.closest("button, a, input, select, textarea")) return;
    _dragIdx = idx;
    _dragChip = chip;
    this.classList.add("dragging");
  }, { passive: true });
  chip.addEventListener("touchmove", function(e) {
    e.preventDefault();
    var t = e.touches[0];
    var chipEl = t ? _touchHit(t.clientX, t.clientY, chipSelector) : null;
    if (!chipEl || chipEl._dragItems !== items) {
      if (_touchOverEl) { _touchOverEl.classList.remove("drag-over"); _touchOverEl = null; }
      return;
    }
    var targetIdx = parseInt(chipEl.dataset.index);
    if (isNaN(targetIdx) || targetIdx === _dragIdx) {
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
    var t = e.changedTouches[0];
    var chipEl = t ? _touchHit(t.clientX, t.clientY, chipSelector) : null;
    if (chipEl && chipEl._dragItems === items && chipEl.dataset.index !== undefined) {
      var targetIdx = parseInt(chipEl.dataset.index);
      if (!isNaN(targetIdx) && targetIdx !== _dragIdx) {
        var item = items.splice(_dragIdx, 1)[0];
        items.splice(targetIdx, 0, item);
        rerender();
      }
    }
    clearDrag();
  }, { passive: true });
  chip.addEventListener("touchcancel", clearDrag, { passive: true });
}
