import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EDITOR = os.path.join(_REPO_ROOT, "web_templates", "_markdown_editor.html")
HIGHLIGHT = os.path.join(_REPO_ROOT, "web_static", "js", "md_highlight.js")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestMdHighlightTokenizers:
    def test_module_exports_pure_tokenizers_only(self):
        js = _read(HIGHLIGHT)
        assert "window.mdHighlight = { markdown: markdown, toml: toml }" in js
        assert "window.attachMdHighlight" not in js
        assert "attachMdHighlight" not in js

    def test_module_has_no_overlay_machinery(self):
        js = _read(HIGHLIGHT)
        assert "data-mdhl" not in js
        assert "mirror" not in js
        assert "ta.value" not in js
        assert "innerHTML" not in js
        assert "getComputedStyle" not in js

    def test_tokenizer_functions_present(self):
        js = _read(HIGHLIGHT)
        for fn in ("function markdown(src)", "function toml(src)",
                   "function tomlLine(line)", "function blockLine(line)",
                   "function inline(text)"):
            assert fn in js, fn
        assert "h[2].length" in js

    def test_tokenizer_emits_span_classes(self):
        js = _read(HIGHLIGHT)
        for cls in ('<span class="mh-b">', '<span class="mh-i">',
                    '<span class="mh-s">', '<span class="mh-c">',
                    '<span class="mh-br">', '<span class="mh-link">',
                    '<span class="mh-task">', '<span class="mh-op">',
                    '<span class="mh-q">', '<span class="mh-hr">',
                    '<span class="mh-fence">', '<span class="mh-tk-key">',
                    '<span class="mh-tk-str">', '<span class="mh-tk-num">'):
            assert cls in js, cls


class TestColourViewMarkup:
    def test_editor_loads_md_highlight_via_av(self):
        html = _read(EDITOR)
        assert "av('/static/js/md_highlight.js')" in html

    def test_editor_stays_a_plain_textarea(self):
        html = _read(EDITOR)
        assert "<textarea" in html
        assert "contenteditable" not in html

    def test_overlay_is_absent_from_editing_surface(self):
        html = _read(EDITOR)
        assert 'id="md-live-highlight"' not in html
        assert "md-live-input" not in html
        assert "caret-color:var(--text)" not in html

    def test_ships_static_colour_view(self):
        html = _read(EDITOR)
        assert '<pre id="md-syntax" class="md-syntax"' in html
        assert ".md-syntax {" in html
        assert "white-space:pre-wrap" in html
        assert "display:none" in html

    def test_colour_button_toggles_the_view(self):
        html = _read(EDITOR)
        assert 'id="btn-syntax"' in html
        assert "toggleSyntax()" in html
        assert "window.toggleSyntax = function()" in html
        assert '_mode === "syntax" ? "edit" : "syntax"' in html

    def test_setmode_renders_colour_from_tokenizer(self):
        html = _read(EDITOR)
        assert "mdHighlight.markdown(" in html
        assert 'syn.innerHTML' in html
        assert '"syntax"' in html

    def test_editor_ships_token_colors(self):
        html = _read(EDITOR)
        for cls in (".mh-h1", ".mh-hr", ".mh-op", ".mh-task", ".mh-b",
                    ".mh-i", ".mh-s", ".mh-c", ".mh-br", ".mh-link",
                    ".mh-fence", ".mh-fence-open", ".mh-q", ".mh-tk-key",
                    ".mh-tk-punct", ".mh-tk-str", ".mh-tk-num"):
            assert cls in html, cls
