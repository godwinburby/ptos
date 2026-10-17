"""Per-device display size (uiScale): head script, settings control,
sidebar stepper, viewport-zoom freedom, and allowlist parity."""
import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(REPO, "web_templates")
STATIC_JS = os.path.join(REPO, "web_static", "js")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def _base():
    return _read(TEMPLATE_DIR, "base.html")


def _ui_scale_js():
    return _read(STATIC_JS, "ui_scale.js")


class TestHeadScript:
    def test_present_before_first_stylesheet(self):
        text = _base()
        i_script = text.index("ptos.uiScale")
        i_css = text.index("av('/static/css/")
        assert i_script < i_css, "scale script must run before stylesheets"
        assert i_script < text.index("</head>")

    def test_within_inline_script_cap(self):
        m = re.search(
            r"<script>\(function\(\)\{try\{var s=parseFloat\(localStorage"
            r"\.getItem\('ptos\.uiScale'\)\).*?</script>",
            _base(), re.S)
        assert m, "head scale script missing or altered"
        assert len(m.group(0)) < 1000

    def test_feature_detects_and_ignores_default(self):
        text = _base()
        assert "CSS.supports('zoom','1.2')" in text
        assert "user-scalable" not in text


class TestViewportNeverBlocksZoom:
    @pytest.mark.parametrize("name", sorted(
        f for f in os.listdir(TEMPLATE_DIR) if f.endswith(".html")))
    def test_template_viewport(self, name):
        text = _read(TEMPLATE_DIR, name)
        for m in re.finditer(r'<meta[^>]+name="viewport"[^>]*>', text):
            assert "user-scalable" not in m.group(0), name
            assert "maximum-scale" not in m.group(0), name


class TestAllowlistParity:
    def test_head_and_js_lists_match(self):
        head = _base()
        m = re.search(r"\[([\d.,\s]+)\]\.indexOf", head)
        assert m, "head allowlist missing"
        head_vals = sorted(float(x) for x in m.group(1).split(","))
        js = _ui_scale_js()
        m2 = re.search(r"var SIZES = \[([\d.,\s]+)\];", js)
        assert m2, "ui_scale.js SIZES missing"
        js_vals = sorted(float(x) for x in m2.group(1).split(","))
        assert head_vals == [v for v in js_vals if v != 1.0]

    def test_default_is_one(self):
        m = re.search(r"var SIZES = \[([\d.,\s]+)\];", _ui_scale_js())
        assert 1.0 in [float(x) for x in m.group(1).split(",")]


class TestUiScaleJs:
    def test_file_is_external_and_substantial(self):
        text = _ui_scale_js()
        assert len(text) > 100
        assert "{{" not in text and "{%" not in text

    def test_loaded_once_via_av(self):
        assert _base().count("av('/static/js/ui_scale.js')") == 1

    def test_exposes_api(self):
        text = _ui_scale_js()
        for name in ("window.getUiScale", "window.setUiScale",
                     "window.stepUiScale"):
            assert name in text, name

    def test_validates_before_applying(self):
        text = _ui_scale_js()
        assert "SIZES.indexOf(v) === -1" in text
        assert "localStorage.setItem" in text
        assert "ptos:uiscale" in text
        assert text.count("catch") >= 3

    def test_stands_down_without_zoom_support(self):
        text = _ui_scale_js()
        assert 'CSS.supports("zoom", "1.2")' in text
        assert "[data-uiscale]" in text
        assert 'style.display = "none"' in text


class TestSidebarStepper:
    def test_footer_has_step_buttons(self):
        text = _base()
        assert 'onclick="stepUiScale(-1)"' in text
        assert 'onclick="stepUiScale(1)"' in text
        assert 'id="uiscale-label"' in text
        i_row = text.index("data-uiscale")
        i_footer = text.index('class="sidebar-footer"')
        assert i_footer < i_row, "stepper must live in the sidebar footer"


class TestSettingsControl:
    @pytest.fixture()
    def client(self):
        import ptos_web
        ptos_web.app.config["TESTING"] = True
        return ptos_web.app.test_client()

    def test_settings_renders_display_size(self, client):
        html = client.get("/settings").get_data(as_text=True)
        assert "Display size" in html
        assert "data-uiscale" in html
        for scale in ("1", "1.15", "1.3", "1.5"):
            assert 'data-scale="%s"' % scale in html, scale
        assert "uiscale-sample" in html
        assert 'class="uiscale-btn"' in html

    def test_display_size_block_is_client_side_only(self):
        text = _read(TEMPLATE_DIR, "settings.html")
        assert "ptos.uiScale" not in text
        assert "ui_scale" not in text
        block = text.split('id="sec-display"')[1].split('id="sec-dashboard"')[0]
        assert "/settings/save" not in block
        assert "data-uiscale" in block

    def test_settings_reuses_view_toggle_style(self):
        text = _read(TEMPLATE_DIR, "settings.html")
        block = text.split('id="sec-display"')[1]
        assert 'class="view-toggle"' in block
