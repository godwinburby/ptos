import datetime as dt
import os
import re

import pytest

import ptos
import ptos_service as svc

QUERIES = """
[all_expenses]
where = "type=expense"
time = "this-month"
sum = true

[metrics.food_spend]
sum = "all_expenses"
sum_field = "amount"

["threshold.food_budget"]
metric    = "food_spend"
agg       = "sum"
sum_field = "amount"
value     = 500
direction = "max"
time      = "this-month"

["board.pipeline"]
columns = ["jobsearch"]
time_window = "this-month"

["habit.meditation"]
filters = ["type=habit", "name=meditation"]
weeks = 12

["calendar.personal"]
filters = ["type=expense"]
time_window = "this-month"

["due.default"]
type = "expense"
key = "name"
days = 7
"""


def _write_queries(content):
    with open(ptos.QUERIES_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    ptos._invalidate_all()


def _write_records(lines):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    with open(os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log"),
              "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    ptos._CACHE.clear()
    if hasattr(svc, "_invalidate_history_cache"):
        svc._invalidate_history_cache()


def _client():
    from ptos_web import app
    return app.test_client()


def _configure_hrefs(html):
    """Hrefs of every "⚙ Configure" anchor on the page. Matched on the button
    text so the sidebar's global "Query Builder" nav link is not picked up."""
    return re.findall(r'href="([^"]*)"[^>]*>\s*(?:⚙\s*)?Configure', html)


class TestConfigureLinkTargets:
    """Every config-owning page's Configure button must point at its own
    Query Builder section, and preselect an item only when the page has one."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        _write_queries(QUERIES)

    def test_habits_links_to_habits_section(self):
        html = _client().get("/habits").data.decode()
        assert "/query-builder?section=habits" in html

    def test_thresholds_links_to_thresholds_section(self):
        html = _client().get("/thresholds").data.decode()
        assert "/query-builder?section=thresholds" in html

    def test_calendar_all_records_links_to_calendars_section(self):
        html = _client().get("/calendar").data.decode()
        assert "/query-builder?section=calendars" in html

    def test_calendar_named_view_preselects_that_calendar(self):
        html = _client().get("/calendar/personal").data.decode()
        assert "/query-builder?section=calendars&amp;edit=personal" in html

    def test_due_preselects_selected_due_config(self):
        html = _client().get("/due").data.decode()
        assert "/query-builder?section=due&amp;edit=default" in html

    def test_board_preselects_auto_selected_board(self):
        html = _client().get("/board").data.decode()
        assert "/query-builder?section=boards&amp;edit=pipeline" in html

    def test_config_name_is_url_encoded(self):
        _write_queries(QUERIES + '\n["board.a&b"]\ncolumns = ["expense"]\n')
        html = _client().get("/board?board=a%26b").data.decode()
        assert "edit=a%26b" in html

    def test_entity_configure_goes_to_types(self):
        html = _client().get("/entity").data.decode()
        assert _configure_hrefs(html) == ["/types"]

    def test_entity_results_configure_goes_to_types(self):
        today = dt.date.today()
        _write_records([f"{today} type=expense client_code=vka7 amount=100"])
        html = _client().get("/entity?field=client_code&value=vka7").data.decode()
        assert _configure_hrefs(html) == ["/types"]

    def test_projects_has_no_page_level_configure(self):
        """Projects have no Query Builder editor (they use /projects/<name>/edit),
        so the page must not offer a Configure button pointing at one."""
        html = _client().get("/projects").data.decode()
        assert _configure_hrefs(html) == []


class TestEmptyStateLinks:
    """The empty-state cards a fresh install shows must also carry the section,
    not dump the user on the Queries tab."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        _write_queries("")

    def test_habits_empty_state(self):
        html = _client().get("/habits").data.decode()
        assert "/query-builder?section=habits" in html

    def test_thresholds_empty_state(self):
        html = _client().get("/thresholds").data.decode()
        assert "/query-builder?section=thresholds" in html

    def test_calendar_empty_state(self):
        html = _client().get("/calendar").data.decode()
        assert "/query-builder?section=calendars" in html

    def test_board_empty_state(self):
        html = _client().get("/board").data.decode()
        assert "/query-builder?section=boards" in html

    def test_due_empty_state_has_no_bare_edit_param(self):
        html = _client().get("/due").data.decode()
        assert "/query-builder?section=due" in html


class TestQueryBuilderDeepLinkGate:
    """The boot gate is client-side JS with no JS test runner in the repo, so
    these pin the exact structure that makes ?section= work on its own and
    keeps a stale ?edit= from selecting a phantom item."""

    def _qb_js(self, query):
        html = _client().get(query).data.decode()
        return html

    def test_section_alone_is_honored(self):
        js = self._qb_js("/query-builder?section=habits")
        assert "if (editSection && _st[editSection])" in js
        assert "if (editName && editSection && _st[editSection])" not in js

    def test_edit_is_guarded_by_membership_check(self):
        js = self._qb_js("/query-builder?section=boards&edit=ghost")
        assert "if (editName && _st[editSection][editName]) select(editSection, editName);" in js

    def test_unknown_section_falls_back_to_queries(self):
        js = self._qb_js("/query-builder?section=bogus")
        assert 'switchSection("queries")' in js
