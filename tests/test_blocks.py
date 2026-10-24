"""Static-scan pins for Blocks mode (the block editor in the note/journal
markdown editor).

The suite stays free of a node dependency, so these assert on the shipped
file text (exports, mode wiring, control surface, shared-helper reuse) the
same way tests/test_embed.py does.
"""
import os

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDITOR = os.path.join(_REPO_ROOT, "web_templates", "_markdown_editor.html")
MD_BLOCKS = os.path.join(_REPO_ROOT, "web_static", "js", "md_blocks.js")
SLASH = os.path.join(_REPO_ROOT, "web_static", "js", "slash_embed.js")
TEXT_BLOCKS = os.path.join(_REPO_ROOT, "web_static", "js", "text_blocks.js")
EMBEDS = os.path.join(_REPO_ROOT, "web_static", "js", "embeds.js")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def html():
    return _read(EDITOR)


@pytest.fixture(scope="module")
def blocks_js():
    return _read(MD_BLOCKS)


@pytest.fixture(scope="module")
def slash_js():
    return _read(SLASH)


@pytest.fixture(scope="module")
def text_blocks_js():
    return _read(TEXT_BLOCKS)


@pytest.fixture(scope="module")
def embeds_js():
    return _read(EMBEDS)


class TestBlocksMarkup:
    def test_blocks_pane_and_button_exist(self, html):
        assert 'id="blocks-pane"' in html
        assert 'id="btn-blocks"' in html
        assert "setMode('blocks')" in html

    def test_blocks_script_loaded_via_av_after_slash_menu(self, html):
        assert "av('/static/js/md_blocks.js')" in html
        slash_at = html.index("av('/static/js/slash_embed.js')")
        blocks_at = html.index("av('/static/js/md_blocks.js')")
        assert slash_at < blocks_at, "md_blocks.js must load after slash_embed.js"

    def test_set_mode_highlights_and_enters_blocks(self, html):
        assert '"blocks"' in html
        assert "mdBlocks.enter()" in html
        assert "mdBlocks.exit()" in html

    def test_set_mode_hides_the_textarea_in_blocks_mode(self, html):
        assert 'ta.style.display = (isSyntax || m === "blocks") ? "none" : "block"' in html
        assert 'if (bp) bp.style.display = "none"' in html
        assert 'if (bp) bp.style.display="block"' in html

    def test_editor_init_wires_md_blocks(self, html):
        assert "mdBlocks.init(_eid)" in html

    def test_editor_skips_preview_render_in_blocks_mode(self, html):
        assert 'if (_mode !== "edit" && _mode !== "blocks") renderPreview();' in html

    def test_insert_view_button_still_present(self, html):
        assert 'id="btn-insert"' in html
        assert "openSlashMenu(document.getElementById('{{ _eid }}'))" in html

    def test_blocks_pane_is_hidden_by_default(self, html):
        start = html.index('id="blocks-pane"')
        end = html.index("</div>", start)
        assert 'display:none' in html[start:end]


class TestBlocksCss:
    def test_ships_block_card_and_controls_css(self, html):
        for cls in (".md-block {", ".md-block-head", ".md-block-actions",
                    ".md-block-btn", ".md-block-body", ".md-block-add-row",
                    ".md-block-edit-box", ".md-block-edit-actions",
                    ".md-block.dragging", ".md-block.drag-over"):
            assert cls in html, cls

    def test_block_body_rerenders_markdown_elements(self, html):
        for sel in (".md-block-body h1", ".md-block-body ul",
                    ".md-block-body blockquote", ".md-block-body table",
                    ".md-block-body pre", ".md-block-body li input[type=checkbox]"):
            assert sel in html, sel


class TestBlocksJs:
    def test_exports(self, blocks_js):
        assert "window.mdBlocks = {" in blocks_js
        for name in ("init:", "enter:", "exit:", "parse:", "serialize:", "render:"):
            assert name in blocks_js, name
        assert "window.blockParse = parse" in blocks_js
        assert "window.blockSerialize = serialize" in blocks_js

    def test_reuses_shared_helpers(self, blocks_js):
        for ref in ("embedRegions", "embedFetch", "embedRenderBody",
                    "openSlashPicker", "preprocessLinks", "window.renderMarkdown",
                    "marked.lexer"):
            assert ref in blocks_js, ref

    def test_live_widgets_mount_with_the_page_time_context(self, blocks_js):
        assert "window.PtosWidgets.mount(body, source" in blocks_js
        assert 'host: "note", interactive: true, data: data' in blocks_js
        assert "window.embedTimeContext()" in blocks_js
        assert '"ptos:time-window-change"' in blocks_js
        assert "_ptosWidgetHandle.destroy()" in blocks_js

    def test_control_surface(self, blocks_js):
        for cls in ('"md-block-actions"', '"md-block-add-row"',
                    '"md-block-edit-box"', '"md-block-add-row"',
                    'md-block-kind', 'md-block-body'):
            assert cls in blocks_js, cls
        for label in ("＋", "✎", "⇄", "▲", "▼", "✕"):
            assert label in blocks_js, label

    def test_actions_are_all_implemented(self, blocks_js):
        for fn in ("function _edit(", "function _move(", "function _remove(",
                   "function _pickerAt(", "function _insertBlock(",
                   "function _applyEdit(", "function _renderCard(",
                   "function _change(", "function _convert(",
                   "function _stripMdMarker(", "function _stripWrap(",
                   "function _sync(", "function render("):
            assert fn in blocks_js, fn

    def test_change_reuses_the_picker_and_resolves_by_identity(self, blocks_js):
        # ⇄ must reuse the shared menu core, and re-resolve its block by
        # object identity (not a captured index) so an async fetch cannot
        # restyle the wrong block after one moves.
        assert "openSlashPicker(anchor, function (picked)" in blocks_js
        assert "_blocks.indexOf(blk)" in blocks_js
        assert '"Change this block' in blocks_js

    def test_edit_box_saves_and_cancels(self, blocks_js):
        assert 'e.key === "Escape"' in blocks_js
        assert "(e.ctrlKey || e.metaKey)" in blocks_js
        assert '"md-embed-edit-save"' in blocks_js
        assert '"md-embed-edit-cancel"' in blocks_js
        assert "setSelectionRange" in blocks_js

    def test_serialize_joins_blocks_canonically(self, blocks_js):
        assert 'parts.join("\\n\\n")' in blocks_js
        assert '"```ptos\\n"' in blocks_js

    def test_serialization_writes_back_through_the_textarea(self, blocks_js):
        assert "_ta.value = serialize(_blocks)" in blocks_js
        assert 'new Event("input", { bubbles: true })' in blocks_js

    def test_sync_does_not_reparse_itself(self, blocks_js):
        assert "if (!_active || _syncing) return;" in blocks_js

    def test_partition_safety_net(self, blocks_js):
        assert "keep the whole" in blocks_js
        assert 'out.push({ kind: "md", source: norm });' in blocks_js

    def test_seed_starter_keeps_trailing_space(self, blocks_js):
        assert "function _normMd(" in blocks_js
        assert "/^(#{1,6}|>|1\\.|-)$/" in blocks_js

    def test_widget_errors_are_shown_not_swallowed(self, blocks_js):
        assert '"msg msg-error"' in blocks_js

    def test_drags_are_ordered_by_index(self, blocks_js):
        assert "dataset.idx" in blocks_js
        assert "_wireDrag" in blocks_js


class TestBlockPicker:
    def test_open_slash_picker_exported(self, slash_js):
        assert "window.openSlashPicker = function (anchor, onPick)" in slash_js
        assert "function _closePicker(" in slash_js
        assert "function _commitPick(" in slash_js
        assert "function _renderPicker(" in slash_js

    def test_open_slash_menu_still_exported(self, slash_js):
        assert "window.openSlashMenu = function (el)" in slash_js
        assert "window.attachSlashEmbed = function (el)" in slash_js

    def test_picker_and_slash_menu_share_one_menu_core(self, slash_js):
        for shared in ("function _buildMenu(", "function _buildTimeStep(",
                       "function _embedSource(", "function _activateIn(",
                       "function _wireItems("):
            assert shared in slash_js, shared
        assert slash_js.count("function _buildMenu(") == 1
        assert slash_js.count("function _buildTimeStep(") == 1
        assert slash_js.count("function _embedSource(") == 1

    def test_picker_reports_md_seeds_and_widget_sources(self, slash_js):
        assert 'kind: "md",\n        seed: it.seed != null ? it.seed : "",\n        caret:' in slash_js
        assert 'onPick({ kind: "widget", source: _embedSource' in slash_js

    def test_picker_runs_the_time_step(self, slash_js):
        assert "function _openTimeStepPick(" in slash_js
        assert "_TIME_CAPABLE[it.view]" in slash_js

    def test_format_items_carry_a_seed(self, slash_js, text_blocks_js):
        assert "window.PtosTextBlocks" in slash_js
        assert text_blocks_js.count("seed:") >= 20
        for seed in ('seed: "# "', 'seed: "- "', 'seed: "- [ ] "',
                     'seed: "> "', 'seed: "---"', 'seed: "**bold text**"',
                     'seed: "*italic*"', 'seed: "~~strikethrough~~"',
                     'seed: "`code`"', 'seed: "[text](url)"',
                     'seed: "| Column | Column |'):
            assert seed in text_blocks_js, seed

    def test_format_items_keep_their_textarea_run(self, slash_js):
        assert "function _formatRun(item)" in slash_js
        for run in ('_prefix(item.prefix)', '_wrap(item.open, item.close)',
                    '_block(item.seed + "\\n",'):
            assert run in slash_js, run

    def test_format_items_declare_a_transform(self, text_blocks_js):
        # Each Format item says how to re-style a block that already has
        # text, so ⇄ keeps the paragraph instead of swapping in a skeleton.
        assert text_blocks_js.count("xform:") >= 15
        for shape in ('{ t: "prefix", pre: "# ", first: true }',
                      '{ t: "prefix", pre: "- ", all: true }',
                      '{ t: "prefix", pre: "1. ", all: true }',
                      '{ t: "prefix", pre: "> ", all: true }',
                      '{ t: "wrap", open: "**", close: "**" }',
                      '{ t: "wrap", open: "`", close: "`" }',
                      '{ t: "link" }', '{ t: "fence", lang: "text" }',
                      '{ t: "replace" }'):
            assert shape in text_blocks_js, shape

    def test_picker_passes_the_transform_through(self, slash_js):
        assert "xform: it.xform || null" in slash_js
        assert 'kind: "md",' in slash_js

    def test_convert_keeps_text_and_handles_widgets(self, blocks_js):
        # ⇄ on a widget replaces it; ⇄ on text re-styles in place; an empty
        # block falls back to the skeleton and opens the editor.
        assert "picked.kind === \"widget\"" in blocks_js
        assert "blk.kind === \"widget\" ? \"\" : blk.source" in blocks_js
        assert "conv.edit && _blocks[i].source" in blocks_js

    def test_embeds_exports_resolve_primitives(self, embeds_js):
        assert "function embedFetch(" in embeds_js
        assert "function embedRenderBody(" in embeds_js
        assert "window.embedFetch = embedFetch" in embeds_js
        assert "window.embedRenderBody = embedRenderBody" in embeds_js
