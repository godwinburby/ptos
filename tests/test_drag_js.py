import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAG_JS = os.path.join(_REPO_ROOT, "web_static", "js", "drag.js")
COMPONENTS_CSS = os.path.join(_REPO_ROOT, "web_static", "css", "components.css")
TYPES_HTML = os.path.join(_REPO_ROOT, "web_templates", "types.html")
SCHEMA_BUILDER_HTML = os.path.join(_REPO_ROOT, "web_templates", "schema_builder.html")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _drag_js():
    return _read(DRAG_JS)


def _components_css():
    return _read(COMPONENTS_CSS)


class TestTouchHitHelper:
    def test_helper_defined_and_used(self):
        src = _drag_js()
        assert "function _touchHit(" in src
        assert "_touchHit(t.clientX, t.clientY, chipSelector)" in src

    def test_walks_element_stack(self):
        src = _drag_js()
        assert "document.elementsFromPoint" in src
        assert ".closest(selector)" in src
        # the elementFromPoint single-shot fallback still exists
        assert "document.elementFromPoint(" in src

    def test_zoom_coordinate_candidates(self):
        src = _drag_js()
        assert "document.documentElement.style.zoom" in src
        assert "[x / z, y / z]" in src
        assert "[x * z, y * z]" in src

    def test_helper_is_a_global(self):
        # board.html relies on _touchHit coming from this file
        src = _drag_js()
        assert "function _touchHit(x, y, selector)" in src


class TestTouchDragGuards:
    def test_touchstart_ignores_interactive_children(self):
        src = _drag_js()
        assert 'e.target.closest("button, a, input, select, textarea")' in src
        ts = src.index('chip.addEventListener("touchstart"')
        guard = src.index('e.target.closest("button, a, input, select, textarea")')
        arm = src.index("_dragIdx = idx;", ts)
        assert ts < guard < arm

    def test_touchend_nan_index_guard(self):
        src = _drag_js()
        assert "!isNaN(targetIdx)" in src

    def test_touchmove_non_passive(self):
        src = _drag_js()
        assert 'chip.addEventListener("touchmove"' in src
        assert "{ passive: false }" in src

    def test_make_draggable_still_the_entry_point(self):
        src = _drag_js()
        assert "function _makeDraggable(chip, items, idx, rerender, chipSelector)" in src


class TestChipSelectionStyles:
    @staticmethod
    def _rule(css, name):
        start = css.index(name + " {")
        return css[start:css.index("}", start) + 1]

    def test_opt_chip_user_select_disabled(self):
        rule = self._rule(_components_css(), ".opt-chip")
        assert "-webkit-user-select:none" in rule
        assert "user-select:none" in rule

    def test_board_card_user_select_disabled(self):
        # long-press text selection must not fight the board's hold-to-grab
        rule = self._rule(_components_css(), ".board-card")
        assert "user-select:none" in rule
        assert "-webkit-touch-callout:none" in rule

    def test_board_card_dragging_visual(self):
        assert ".board-card.dragging" in _components_css()


class TestCrossArrayDropGuard:
    def test_drag_items_marker_on_every_chip(self):
        src = _drag_js()
        assert "chip._dragItems = items;" in src

    def test_mouse_drop_rejects_foreign_array(self):
        src = _drag_js()
        assert "_dragChip._dragItems !== this._dragItems" in src
        assert "_dragChip = null;" in src

    def test_touch_paths_reject_foreign_array(self):
        src = _drag_js()
        assert "chipEl._dragItems !== items" in src
        assert "chipEl._dragItems === items" in src


class TestTypesOptionChipDrag:
    def test_options_wired_with_per_field_selector(self):
        src = _read(TYPES_HTML)
        assert "optSel = '.opt-chip[data-fi=\"' + i + '\"]'" in src
        assert "parseInt(chip.dataset.oi, 10)" in src
        assert "renderFieldRows, optSel)" in src

    def test_chips_carry_field_and_option_ids(self):
        src = _read(TYPES_HTML)
        assert "data-fi=" in src
        assert "data-oi=" in src

    def test_drag_js_included(self):
        assert "/static/js/drag.js" in _read(TYPES_HTML)


class TestSchemaBuilderChipWiring:
    def test_five_option_chip_call_sites(self):
        src = _read(SCHEMA_BUILDER_HTML)
        assert src.count('".opt-chip"') == 5
