"""Phase 0 A3 — vendored markdown + sanitizer wiring.

marked 9.1.6 and DOMPurify 3.4.17 ship in ``web_static/vendor/`` (no CDN:
PTOS must render offline from a LAN/Tailscale phone server);
``web_static/js/md_render.js`` is the single renderer
(``window.renderMarkdown`` = marked → DOMPurify.sanitize, fail-closed to
escaped text when either library is missing); templates load both through
``av()`` and never call ``marked.parse``/``marked.setOptions`` directly.

Static pins run everywhere. ``tests/js/md_render.test.js`` runs under
``node --test`` when Node is available: marked-parse and fail-closed cases
headless, sanitizer cases only where jsdom is present (jsdom is never
shipped — a temp-only verification install).
"""

import glob
import os
import re
import shutil
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
        return f.read()


def _templates():
    return sorted(glob.glob(os.path.join(REPO, "web_templates", "*.html")))


class TestNoExternalLoads:
    @pytest.mark.parametrize("path", _templates(), ids=os.path.basename)
    def test_template_has_no_cdn_script_or_stylesheet(self, path):
        with open(path, encoding="utf-8") as f:
            src = f.read()
        assert not re.search(r"<script\b[^>]*\bsrc\s*=\s*[\"']https?://", src)
        assert not re.search(r"<link\b[^>]*\bhref\s*=\s*[\"']https?://", src)

    def test_web_static_code_loads_no_cdn(self):
        domains = ("cdnjs.cloudflare.com", "ajax.cloudflare.com",
                   "cdn.jsdelivr.net", "unpkg.com")
        for path in glob.glob(os.path.join(REPO, "web_static", "**", "*"),
                              recursive=True):
            if not path.endswith((".js", ".css")):
                continue
            with open(path, encoding="utf-8") as f:
                src = f.read()
            for dom in domains:
                assert dom not in src, path

    def test_render_markdown_defined_only_by_md_render(self):
        for path in glob.glob(os.path.join(REPO, "web_static", "js",
                                           "*.js")):
            with open(path, encoding="utf-8") as f:
                src = f.read()
            if os.path.basename(path) == "md_render.js":
                assert "window.renderMarkdown = render" in src
            else:
                assert not re.search(r"renderMarkdown\s*=(?!=)", src), path


class TestVendorPins:
    def test_marked_version_banner(self):
        assert "9.1.6" in _read("web_static", "vendor", "marked.min.js")

    def test_dom_purify_version_banner(self):
        assert "3.4.17" in _read("web_static", "vendor", "purify.min.js")

    def test_license_files_ship(self):
        assert "Permission is hereby granted" in _read(
            "web_static", "vendor", "marked-LICENSE")
        assert "Apache License" in _read(
            "web_static", "vendor", "purify-LICENSE")

    def test_versions_manifest_pins_both(self):
        src = _read("web_static", "vendor", "VERSIONS.md")
        assert "9.1.6" in src
        assert "3.4.17" in src
        assert "md_render.js" in src


class TestMdRenderWiring:
    def test_helper_sanitizes_and_fails_closed(self):
        src = _read("web_static", "js", "md_render.js")
        assert "DOMPurify.sanitize(html" in src
        assert "{ ALLOWED_TAGS: ALLOWED_TAGS }" in src
        assert 'typeof DOMPurify === "undefined"' in src
        assert "escapeText(src)" in src
        assert "window.renderMarkdown = render" in src
        assert "window.PtosMarkdown" in src

    def test_allowed_tags_cover_markdown_output(self):
        src = _read("web_static", "js", "md_render.js")
        for tag in ('"details"', '"summary"', '"br"', '"table"',
                    '"input"', '"pre"'):
            assert tag in src
        for tag in ('"script"', '"style"', '"iframe"', '"object"',
                    '"embed"'):
            assert tag not in src

    def test_template_loads_vendored_libraries_via_av(self):
        src = _read("web_templates", "_markdown_editor.html")
        i_marked = src.index("av('/static/vendor/marked.min.js')")
        i_purify = src.index("av('/static/vendor/purify.min.js')")
        i_helper = src.index("av('/static/js/md_render.js')")
        assert i_marked < i_purify < i_helper

    def test_template_never_calls_marked_directly(self):
        for path in _templates():
            with open(path, encoding="utf-8") as f:
                src = f.read()
            assert "marked.parse" not in src, path
            assert "marked.setOptions" not in src, path
            assert "cdnjs" not in src, path

    def test_template_routes_preview_through_helper(self):
        src = _read("web_templates", "_markdown_editor.html")
        assert "? renderMarkdown(text)" in src
        assert "mountEmbeds(pane)" in src


class TestNodeBehaviorSuite:
    @pytest.mark.skipif(shutil.which("node") is None,
                        reason="node not installed")
    def test_md_render_node_suite(self):
        path = os.path.join(REPO, "tests", "js", "md_render.test.js")
        if not os.path.isfile(path):
            pytest.skip("js suite missing")
        proc = subprocess.run(
            [shutil.which("node"), "--test", path],
            cwd=REPO, capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
