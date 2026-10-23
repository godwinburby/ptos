"""C5/C6 shared text blocks and markdown toolbar regression checks."""

import os
import shutil
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT_BLOCKS = "web_static/js/text_blocks.js"
SLASH = "web_static/js/slash_embed.js"
PICKER = "web_static/js/widget_picker.js"
TOOLBAR = "web_static/js/md_toolbar.js"
BLOCKS = "web_static/js/md_blocks.js"
EDITOR = "web_templates/_markdown_editor.html"
CSS = "web_static/css/components.css"


def _read(path):
    with open(os.path.join(REPO, path), encoding="utf-8") as stream:
        return stream.read()


def test_shared_text_block_script_loads_before_both_consumers():
    html = _read(EDITOR)
    catalog = html.index("av('/static/js/text_blocks.js')")
    picker = html.index("av('/static/js/widget_picker.js')")
    slash = html.index("av('/static/js/slash_embed.js')")
    assert catalog < picker < slash
    assert "window.PtosTextBlocks" in _read(SLASH)
    assert "window.PtosTextBlocks" in _read(PICKER)
    assert "var items = window.PtosTextBlocks" in _read(PICKER)
    assert "var _FORMAT_GROUP" not in _read(SLASH)


def test_shared_text_block_catalog_has_required_entries_and_metadata():
    source = _read(TEXT_BLOCKS)
    for entry in (
        'id: "heading-1"', 'id: "heading-2"', 'id: "heading-3"',
        'id: "paragraph"', 'id: "bulleted-list"', 'id: "numbered-list"',
        'id: "checklist"', 'id: "quote"', 'id: "callout"',
        'id: "divider"', 'id: "table"', 'id: "code-block"',
        'id: "greeting-line"', 'id: "today-date"', 'id: "your-name"',
        'id: "period-token"', 'id: "long-date"', 'id: "iso-date"',
    ):
        assert entry in source
    assert "description:" in source
    assert "aliases:" in source
    assert "caret:" in source
    assert "gallery: true" in source


def test_token_entries_cover_every_spec_token_and_feed_the_toolbar_menu():
    """The {} / "Token" menu offers all eight Part F tokens, driven from
    the single text_blocks.js catalog (no second token list anywhere)."""
    source = _read(TEXT_BLOCKS)
    spec_tokens = ("{{greeting}}", "{{period}}", "{{name}}", "{{date}}",
                   "{{date:long}}", "{{date:iso}}", "{{weekday}}",
                   "{{time}}")
    for token in spec_tokens:
        assert 'token: "%s"' % token in source, token
    # The three menu-only variants stay out of the gallery Text category
    # (spec C5) but remain in the slash Format group and the {} menu.
    for entry in ('id: "period-token"', 'id: "long-date"', 'id: "iso-date"'):
        line = next(l for l in source.splitlines() if entry in l)
        assert "gallery: false" in line, entry
    toolbar = _read(TOOLBAR)
    assert 'action("Token","Insert token"' in toolbar
    assert "window.PtosTextBlocks || []" in toolbar
    assert ".filter(function(item){return item.token;})" in toolbar


def test_full_editor_disables_the_under_textarea_preview_blocks_keeps_it():
    html = _read(EDITOR)
    assert "attach(_mainTextarea, { preview: false })" in html
    blocks = _read(BLOCKS)
    assert "window.PtosToolbar.attach(box)" in blocks  # default: preview on
    assert "attach(box, {" not in blocks


def test_blocks_editor_uses_catalog_caret_and_shared_safe_renderer():
    source = _read(BLOCKS)
    assert "picked.caret" in source
    assert "window.renderMarkdown(body)" in source
    assert "marked.parse(body)" not in source


def test_toolbar_is_loaded_and_covers_keyboard_and_accessibility_contract():
    html = _read(EDITOR)
    assert "av('/static/js/md_toolbar.js')" in html
    source = _read(TOOLBAR)
    for label in ("Bold", "Italic", "Insert link", "Heading level",
                  "Bulleted list", "Numbered list", "Checklist", "Quote",
                  "Code", "Insert token", "Markdown help"):
        assert label in source
    assert 'setAttribute("aria-label"' in source
    assert "visualViewport" in source
    assert "continueList" in source
    assert "indentLines" in source
    assert "window.renderMarkdown(ta.value)" in source


def test_toolbar_targets_and_mobile_preview_styles_exist():
    css = _read(CSS)
    assert ".md-tool-btn" in css and "min-width:44px" in css
    assert ".md-tool-pinned" in css
    assert ".md-tool-preview" in css


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_toolbar_node_suite():
    path = os.path.join(REPO, "tests", "js", "md_toolbar.test.js")
    proc = subprocess.run(
        [shutil.which("node"), path], cwd=REPO,
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
