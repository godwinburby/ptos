"""Phase 0 A3 — vendored markdown + sanitizer wiring, plus Part F tokens.

marked 9.1.6 and DOMPurify 3.4.17 ship in ``web_static/vendor/`` (no CDN:
PTOS must render offline from a LAN/Tailscale phone server);
``web_static/js/md_render.js`` is the single renderer
(``window.renderMarkdown`` = marked → DOMPurify.sanitize, fail-closed to
escaped text when either library is missing); templates load both through
``av()`` and never call ``marked.parse``/``setOptions`` directly.

Part F — inline ``{{tokens}}`` are substituted AFTER sanitizing by a
TreeWalker text-node pass inside ``render`` (the only caller); values are
inserted as text nodes inside ``<span class="md-token">`` so a hostile
name can never become markup, and ``window.PTOS.userName`` (JSON-escaped
in the base.html shim) is the name source. The pure ``tokenize``/
``nextBoundary`` helpers run under ``node --test`` (md_tokens.test.js).

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
        assert "ALLOWED_TAGS: ALLOWED_TAGS" in src
        assert 'FORBID_ATTR: ["style"]' in src
        assert 'typeof DOMPurify === "undefined"' in src
        assert "escapeText(src)" in src
        assert "window.renderMarkdown = render" in src
        assert "window.PtosMarkdown" in src

    def test_allowed_tags_cover_markdown_output(self):
        src = _read("web_static", "js", "md_render.js")
        for tag in ('"details"', '"summary"', '"br"', '"table"',
                    '"input"', '"pre"'):
            assert tag in src
        for tag in ('"script",', '"style",', '"iframe"', '"object"',
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


class TestTokens:
    """Part F — inline {{token}} substitution lives only in md_render."""

    def _src(self):
        return _read("web_static", "js", "md_render.js")

    def test_render_is_the_only_token_pass_caller(self):
        src = self._src()
        # The render pipeline calls it exactly once, after sanitize.
        assert "substituteTokens(container" in src
        i_sanitize = src.index("DOMPurify.sanitize(html")
        i_tokens = src.index("substituteTokens(container")
        assert i_sanitize < i_tokens
        # No other client module may run the pass itself.
        for path in glob.glob(os.path.join(REPO, "web_static", "js", "*.js")):
            if os.path.basename(path) == "md_render.js":
                continue
            with open(path, encoding="utf-8") as f:
                assert "substituteTokens" not in f.read(), path

    def test_span_built_with_dom_methods_never_string_html(self):
        src = self._src()
        assert 'span.className = "md-token"' in src
        assert "doc.createElement(\"span\")" in src
        assert "doc.createTextNode(v)" in src
        assert "<span" not in src  # no string-built markup anywhere

    def test_code_pre_and_passthrough_tags_are_skipped(self):
        src = self._src()
        assert '"code,pre,script,style"' in src
        assert "createTreeWalker" in src
        assert ".closest(SKIP_TOKEN_ANCESTORS)" in src

    def test_values_are_inserted_as_text_nodes_only(self):
        # refreshTokens repaints spans in place: textContent only, never a
        # re-render, so focus and open embeds survive a period change.
        src = self._src()
        start = src.index("function refreshTokens")
        body = src[start:src.index("function nextBoundary")]
        assert "innerHTML" not in body
        assert "render(" not in body
        assert "substituteTokens" not in body
        assert "createTextNode" in body

    def test_refresh_fires_on_boundary_and_visibilitychange(self):
        src = self._src()
        assert "visibilitychange" in src
        assert "nextBoundary(new Date())" in src

    def test_name_comes_from_json_escaped_shim_key(self):
        base = _read("web_templates", "base.html")
        m = re.search(r"window\.PTOS=\{(.*?)\};", base, re.S)
        assert m, "PTOS config shim missing"
        assert "userName:" in m.group(1)
        assert 'userName:{{ user_name|default("", true)|tojson }}' in m.group(1)

    def test_context_processor_supplies_user_name(self):
        src = _read("ptos_web.py")
        assert '"user_name"' in src
        i_proc = src.index("def _inject_globals")
        assert '"user_name"' in src[i_proc:i_proc + 4000]

    def test_pure_helpers_are_exported_for_node(self):
        src = self._src()
        for name in ("tokenize: tokenize", "tokenValue: tokenValue",
                     "nextBoundary: nextBoundary",
                     "substituteTokens: substituteTokens",
                     "refreshTokens: refreshTokens"):
            assert name in src, name

    def test_toolbar_preview_inherits_tokens_for_free(self):
        src = _read("web_static", "js", "md_toolbar.js")
        assert "window.renderMarkdown(ta.value)" in src


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

    @pytest.mark.skipif(shutil.which("node") is None,
                        reason="node not installed")
    def test_md_tokens_node_suite(self):
        path = os.path.join(REPO, "tests", "js", "md_tokens.test.js")
        proc = subprocess.run(
            [shutil.which("node"), "--test", path],
            cwd=REPO, capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
