"""Static-scan pins for RecordTable instance-scoping (Stage 1d of the
live-widgets spec).

record_table.js must stay multi-instance safe: several tables (main results
+ widgets) can live on one page. There is no JS test runner in the repo, so
these assert on the shipped file text the same way tests/test_embed.py and
tests/test_blocks.py do:

- every generated id derives from a per-instance uid (no fixed rt-* ids),
- all interaction is delegated (no inline onclick/onchange/oninput handlers
  referencing RecordTable statics),
- row/checkbox queries are container-scoped (never document-wide),
- the consumer templates no longer assign RecordTable._* statics (the old
  last-instance-wins wiring is dead code now).
"""
import os

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(_REPO_ROOT, "web_static", "js", "record_table.js")
TEMPLATES = [
    os.path.join(_REPO_ROOT, "web_templates", name)
    for name in ("browse.html", "home.html", "queries.html",
                 "query_builder.html", "entity.html")
]


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def js():
    return _read(JS)


class TestNoInlineStaticHandlers:
    """Generated HTML used to call RecordTable._sort(...) etc. via inline
    handlers; a second instance clobbered the statics and the first table
    broke. Delegation on the instance's own container/modal wrap replaced
    them — no inline handler may mention RecordTable."""

    @pytest.mark.parametrize("attr", ["onclick=", "onchange=", "oninput="])
    def test_no_inline_event_attributes(self, js, attr):
        assert attr not in js

    def test_no_static_reference_in_html_strings(self, js):
        for name in ("_sort", "_export", "_check", "_selAll", "_openDel",
                     "_del", "_delClose", "_bkDelOpen", "_bkDelClose",
                     "_bkDelConfirm", "_bkSetOpen", "_bkSetClose",
                     "_bkSetConfirm", "_bkPrev", "_bkClear",
                     "_bkFieldChange"):
            assert ("RecordTable." + name) not in js


class TestPerInstanceIds:
    """Every generated id derives from a per-instance uid counter, so two
    instances' modals/tables never collide in the document."""

    def test_uid_counter_exists(self, js):
        assert 'RecordTable._seq = (RecordTable._seq || 0) + 1;' in js
        assert 'var uid = "rt" + RecordTable._seq;' in js

    @pytest.mark.parametrize("suffix", [
        '-del-dialog', '-bulk-bar', '-bulk-del-dialog', '-bulk-set-dialog',
        '-select-all', '-table', '-tbody', '-pagination', '-modals',
    ])
    def test_modal_and_table_ids_derive_from_uid(self, js, suffix):
        assert ('uid + "' + suffix + '"') in js

    @pytest.mark.parametrize("fixed", [
        '"rt-del-dialog"', '"rt-bulk-bar"', '"rt-select-all"',
        '"rt-table"', '"rt-tbody"', '"rt-pagination"',
        '"rt-bulk-del-dialog"', '"rt-bulk-set-dialog"',
    ])
    def test_no_fixed_id_literals(self, js, fixed):
        assert fixed not in js

    def test_no_document_wide_fixed_id_lookup(self, js):
        assert 'getElementById("rt-' not in js


class TestDelegatedEvents:
    def test_wire_attaches_container_click_listener(self, js):
        assert 'function _wire()' in js
        assert 'container.addEventListener("click"' in js

    def test_wire_attaches_container_change_listener(self, js):
        assert 'container.addEventListener("change"' in js

    def test_row_actions_carry_data_rt_attributes(self, js):
        for action in ("export", "prev", "next", "opendel", "del",
                       "delclose", "bksetopen", "bksetclose", "bksetconfirm",
                       "bkdelopen", "bkdelclose", "bkdelconfirm", "bkclear"):
            assert ('data-rt="' + action + '"') in js or \
                   ("data-rt='" + action + "'") in js or \
                   ('case "' + action + '"') in js

    def test_sort_uses_data_col_on_th(self, js):
        assert 'data-col="' in js
        assert "th.dataset.col" in js


class TestContainerScopedQueries:
    """Row checkboxes must be queried within the instance container only —
    document-wide queries would hit the other table's rows."""

    def test_row_checkbox_queries_are_container_scoped(self, js):
        assert 'document.querySelectorAll(".rt-row' not in js
        assert 'container.querySelectorAll(".rt-row-cb")' in js

    def test_sortable_headers_queried_within_container(self, js):
        assert 'document.querySelectorAll("#rt-' not in js
        assert 'container.querySelectorAll("th.sortable")' in js

    def test_lookup_helpers_scope_to_instance_ids(self, js):
        assert "function ge(id)" in js
        assert "ge(M.tbody)" in js
        assert "ge(M.pagination)" in js


class TestTemplatesDroppedStaticWiring:
    """The four consumer pages used to assign all 16 RecordTable._* statics
    after instantiation (last-instance-wins). entity.html never assigned
    them, so its inline handlers were dead — delegation now serves every
    page uniformly."""

    @pytest.mark.parametrize("path", TEMPLATES)
    def test_template_has_no_static_assignments(self, path):
        assert "RecordTable._" not in _read(path)

    @pytest.mark.parametrize("path", TEMPLATES)
    def test_template_still_instantiates_via_new(self, path):
        assert "new RecordTable(" in _read(path)
