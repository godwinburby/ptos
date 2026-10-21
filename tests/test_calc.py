"""Static-scan pins for the inline calculator (ƒx button on numeric fields).

There is no JS test runner, so these assert on the shipped file text the
same way tests/test_blocks.py and tests/test_embed.py do.
"""
import os
import re

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALC_JS = os.path.join(_REPO_ROOT, "web_static", "js", "calculator.js")
COMPONENTS_CSS = os.path.join(_REPO_ROOT, "web_static", "css", "components.css")
ADD_HTML = os.path.join(_REPO_ROOT, "web_templates", "add.html")
EDIT_HTML = os.path.join(_REPO_ROOT, "web_templates", "edit.html")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def calc_js():
    return _read(CALC_JS)


@pytest.fixture(scope="module")
def add_html():
    return _read(ADD_HTML)


@pytest.fixture(scope="module")
def edit_html():
    return _read(EDIT_HTML)


class TestCalculatorJs:
    def test_no_eval(self, calc_js):
        assert "eval(" not in calc_js
        assert "new Function" not in calc_js

    def test_exports_ptos_calc(self, calc_js):
        assert "window.PtosCalc" in calc_js
        for name in ("open", "close", "evaluate", "apply"):
            assert re.search(rf"\b{name}\s*:", calc_js), f"missing {name} export"

    def test_apply_rounds_and_dispatches_events(self, calc_js):
        assert "Math.round" in calc_js
        assert 'dispatchEvent(new Event("input"' in calc_js
        assert 'dispatchEvent(new Event("change"' in calc_js

    def test_apply_blocked_on_bad_expression(self, calc_js):
        assert re.search(r"if\s*\(\s*!r\.ok\s*\)\s*return", calc_js)

    def test_division_by_zero_rejected(self, calc_js):
        assert "isFinite" in calc_js

    def test_percent_key_on_keypad(self, calc_js):
        assert re.search(r'\["%",\s*"op"\]', calc_js)

    def test_percent_discount_semantics(self, calc_js):
        assert "parseTerm(v)" in calc_js
        assert re.search(r"base \* n\) / 100|base \* n / 100", calc_js)
        assert "n / 100" in calc_js

    def test_no_sign_toggle_key(self, calc_js):
        assert "_toggleSign" not in calc_js
        assert "\\u00B1" not in calc_js

    def test_delegated_button_handler(self, calc_js):
        assert 'closest(".calc-btn")' in calc_js
        assert "data-for" in calc_js

    def test_escape_and_outside_click_close(self, calc_js):
        assert 'e.key === "Escape"' in calc_js
        assert 'closest(".calc-panel")' in calc_js

    def test_expression_seeded_from_field_value(self, calc_js):
        assert "_expr.value = input.value" in calc_js


class TestCalculatorCss:
    def test_button_and_panel_styles(self):
        css = _read(COMPONENTS_CSS)
        assert ".calc-btn" in css
        assert ".calc-panel" in css
        assert ".calc-panel.open" in css
        assert ".calc-keys" in css
        assert ".calc-apply" in css


class TestFormTemplates:
    @pytest.mark.parametrize("name,html", [("add", ADD_HTML), ("edit", EDIT_HTML)])
    def test_loads_calculator_js_via_av(self, name, html):
        body = _read(html)
        assert re.search(
            r'<script src="\{\{\s*av\([\'"]/static/js/calculator\.js[\'"]\)\s*\}\}">',
            body), f"{name}.html must load calculator.js via av()"

    @pytest.mark.parametrize("name,html", [("add", ADD_HTML), ("edit", EDIT_HTML)])
    def test_is_int_branch_has_calc_button(self, name, html):
        body = _read(html)
        m = re.search(r"\{%\s*elif f\.is_int\s*%\}(.*?)\{%\s*elif", body, re.S)
        assert m, f"{name}.html missing is_int branch"
        branch = m.group(1)
        assert 'id="field-{{ f.name }}"' in branch
        assert 'class="calc-btn"' in branch
        assert 'data-for="field-{{ f.name }}"' in branch
        assert re.search(
            r'<input type="number" name="\{\{ f\.name \}\}"', branch)

    @pytest.mark.parametrize("name,html", [("add", ADD_HTML), ("edit", EDIT_HTML)])
    def test_calc_button_is_type_button(self, name, html):
        body = _read(html)
        m = re.search(r"\{%\s*elif f\.is_int\s*%\}(.*?)\{%\s*elif", body, re.S)
        assert m
        assert re.search(
            r'<button type="button" class="calc-btn"', m.group(1))
