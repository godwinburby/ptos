"""Phase 2 (home-note spec Part C) — widget gallery form + picker wiring.

Client files (all loaded through ``av()`` in ``_markdown_editor.html``:
widget_toml.js → widget_form.js → widget_picker.js, then slash_embed.js):

* ``widget_toml.js`` — the single client TOML parser/serializer
  (``window.PtosToml``); node-suite pinned in ``tests/js/widget_toml.test.js``.
* ``widget_form.js`` — metadata-driven form (``PtosWidgetForm.mount``),
  debounced validate + embedFetch preview, "Edit as text" toggle.
* ``widget_picker.js`` — gallery (``PtosWidgetPicker.open``, bottom sheet
  / popover, categories + starters + recent, change-mode ``merge``).

Server-side, this file also pins the Phase 2 ``schema.fields`` option
source (global field-name union for the ``where`` expression datalist).
"""

import os
import re
import shutil
import subprocess

import pytest

import ptos_service as svc

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
        return f.read()


TOML_JS = "web_static/js/widget_toml.js"
FORM_JS = "web_static/js/widget_form.js"
PICKER_JS = "web_static/js/widget_picker.js"
SLASH_JS = "web_static/js/slash_embed.js"
BLOCKS_JS = "web_static/js/md_blocks.js"
EDITOR_HTML = "web_templates/_markdown_editor.html"
COMPONENTS_CSS = "web_static/css/components.css"


class TestScriptOrder:
    def test_editor_loads_toml_form_picker_before_slash(self):
        html = _read(EDITOR_HTML)
        toml_at = html.index("av('/static/js/widget_toml.js')")
        form_at = html.index("av('/static/js/widget_form.js')")
        picker_at = html.index("av('/static/js/widget_picker.js')")
        slash_at = html.index("av('/static/js/slash_embed.js')")
        blocks_at = html.index("av('/static/js/md_blocks.js')")
        assert toml_at < form_at < picker_at < slash_at < blocks_at

    def test_all_three_load_via_av(self):
        html = _read(EDITOR_HTML)
        for name in ("widget_toml.js", "widget_form.js", "widget_picker.js"):
            assert f"av('/static/js/{name}')" in html

    def test_no_unversioned_static_refs_in_new_files(self):
        for path in (TOML_JS, FORM_JS, PICKER_JS):
            src = _read(path)
            assert "/static/" not in src


class TestWidgetToml:
    def test_exposes_single_parser(self):
        src = _read(TOML_JS)
        assert "root.PtosToml = { parse: parse, serialize: serialize }" in src
        assert src.count("function parse(") == 1
        assert src.count("function serialize(") == 1

    def test_no_second_parser_in_form_or_picker(self):
        for path in (FORM_JS, PICKER_JS):
            src = _read(path)
            assert "PtosToml.parse" in src
            assert "function parseToml" not in src
            assert "function serializeToml" not in src

    @pytest.mark.skipif(shutil.which("node") is None,
                        reason="node not installed")
    def test_widget_toml_node_suite(self):
        path = os.path.join(REPO, "tests", "js", "widget_toml.test.js")
        assert os.path.isfile(path)
        proc = subprocess.run(
            [shutil.which("node"), "--test", path],
            cwd=REPO, capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr


class TestWidgetFormWiring:
    def test_form_uses_validate_and_embed_fetch(self):
        src = _read(FORM_JS)
        assert "/api/widgets/validate" in src
        assert "embedFetch(" in src
        assert "embedRenderBody(" in src
        assert "PtosWidgetForm = { mount: mount }" in src
        assert "Edit as text" in src
        assert "_DEBOUNCE = 400" in src

    def test_form_option_sources(self):
        src = _read(FORM_JS)
        assert '"schema.fields"' in src
        assert '"schema.types"' in src
        assert "/api/widgets/options?source=" in src

    def test_form_no_eval(self):
        src = _read(FORM_JS)
        assert "eval(" not in src

    def test_blocks_edit_opens_form_for_widgets(self):
        src = _read(BLOCKS_JS)
        assert "PtosWidgetForm.mount" in src
        assert 'blk.kind === "widget" && window.PtosWidgetForm' in src

    def test_blocks_change_opens_gallery_in_change_mode(self):
        src = _read(BLOCKS_JS)
        assert 'mode: "change"' in src
        assert "PtosWidgetPicker.open" in src
        assert "onFormat:" in src

    def test_blocks_drag_guard_covers_form(self):
        src = _read(BLOCKS_JS)
        assert ".wf-form" in src


class TestWidgetPickerWiring:
    def _require_node_jsdom(self):
        node = shutil.which("node")
        if node is None:
            message = "Node.js is required for JavaScript widget tests; run npm ci"
            if os.environ.get("CI"):
                pytest.fail(message)
            pytest.skip(message)
        proc = subprocess.run([node, "-e", "require.resolve('jsdom')"],
                              cwd=REPO, capture_output=True, text=True)
        if proc.returncode != 0:
            message = "jsdom is required for JavaScript widget tests; run npm ci"
            if os.environ.get("CI"):
                pytest.fail(message)
            pytest.skip(message)
        return node

    def test_picker_surface(self):
        src = _read(PICKER_JS)
        assert "/api/widgets/catalog" in src
        assert 'encodeURIComponent("saved." + kind)' in src
        assert "window.PtosWidgetPicker = {" in src
        assert "catalog: function (cb)" in src
        assert "_RECENT_KEY" in src
        assert "localStorage" in src

    def test_picker_recent_is_try_caught(self):
        src = _read(PICKER_JS)
        assert src.count("localStorage") >= 2
        assert "catch (e) { return []; }" in src

    def test_slash_menu_has_gallery_entry(self):
        src = _read(SLASH_JS)
        assert "_GALLERY_GROUP" in src
        assert "All widgets…" in src
        assert "it._gallery" in src

    def test_slash_empty_menu_uses_gallery_categories(self):
        src = _read(SLASH_JS)
        render = src[src.index("function _render(el, tok, list)"):src.index("function _escape")]
        assert "PtosWidgetPicker.catalog" in render
        assert "_navCategory" in render
        assert "if (tok.query)" in render
        assert "_buildMenu(tok.query)" not in render

    def test_slash_handles_gallery_in_both_paths(self):
        src = _read(SLASH_JS)
        assert "_openGallerySlash" in src
        assert src.count("it._gallery") >= 3  # filter hay, label, buildMenu, commits
        assert "mode: \"add\"" in src

    def test_blocks_plus_opens_gallery_directly(self):
        src = _read(BLOCKS_JS)
        picker = src[src.index("function _pickerAt"):src.index("function _change")]
        assert "PtosWidgetPicker.open" in picker
        assert "openSlashPicker" not in picker

    def test_picker_node_suite(self):
        node = self._require_node_jsdom()
        path = os.path.join(REPO, "tests", "js", "widget_picker.test.js")
        proc = subprocess.run([node, "--test", path],
                              cwd=REPO, capture_output=True, text=True,
                              timeout=180)
        assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr

    def test_slash_navigation_node_suite(self):
        node = self._require_node_jsdom()
        path = os.path.join(REPO, "tests", "js", "slash_nav.test.js")
        proc = subprocess.run([node, path], cwd=REPO,
                              capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr


class TestWidgetCss:
    def test_picker_and_form_classes_exist(self):
        css = _read(COMPONENTS_CSS)
        for cls in (".wp-overlay", ".wp-sheet", ".wp-card", ".wp-item",
                    ".wp-search", ".wf-form", ".wf-field", ".wf-chip",
                    ".wf-preview-frame", ".wf-actions", ".wf-save"):
            assert cls in css, cls

    def test_picker_has_44px_targets_and_phone_sheet(self):
        css = _read(COMPONENTS_CSS)
        assert "min-height:44px" in css
        assert "@media (min-width:768px)" in css
        assert "max-height:85vh" in css


class TestSchemaFieldsOptionSource:
    def test_union_across_types(self):
        vals = svc.get_widget_options("schema.fields")
        assert isinstance(vals, list)
        assert vals and all(isinstance(v, str) for v in vals)
        types = svc.get_widget_options("schema.types")
        assert types
        assert "name" in vals or "amount" in vals or "category" in vals
