import os
import re
import tomli_w
import pytest

import ptos
import ptos_service as svc
from ptos_service import PTOSError

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIDGETS_JS = os.path.join(_REPO_ROOT, "web_static", "js", "widgets.js")
BASE_CSS = os.path.join(_REPO_ROOT, "web_static", "css", "base.css")
COMPONENTS_CSS = os.path.join(_REPO_ROOT, "web_static", "css", "components.css")
QB_HTML = os.path.join(_REPO_ROOT, "web_templates", "query_builder.html")
STARTER_QUERIES = os.path.join(_REPO_ROOT, "starters", "starter_queries.toml")


def _write_records(lines):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    year = ptos.today().year
    with open(os.path.join(ptos.RECORDS_DIR, f"{year}.log"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _set_queries(d):
    with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
        tomli_w.dump(d, w.stream)
    ptos._invalidate_all()


def _clean():
    ptos._CACHE.clear()


def _seed_expenses():
    d = ptos.today().strftime("%Y-%m-%d")
    _write_records([
        f"{d} type=expense amount=100 category=food",
        f"{d} type=expense amount=250 category=transport",
    ])


def _read_queries():
    import tomllib
    with open(ptos.QUERIES_PATH, "rb") as f:
        return tomllib.load(f)


class TestChartValidation:
    def test_group_accepts_bar_and_hbar(self):
        _clean()
        svc.save_query_entry("g", {"where": "type=expense", "time": "tm",
                                   "group": "category", "chart": "bar"})
        assert _read_queries()["g"]["chart"] == "bar"
        svc.save_query_entry("g", {"where": "type=expense", "time": "tm",
                                   "group": "category", "chart": "hbar"})
        assert _read_queries()["g"]["chart"] == "hbar"

    def test_trend_accepts_line_with_y(self):
        _clean()
        svc.save_query_entry("t", {"where": "type=expense", "time": "tm",
                                   "trend": "6", "chart": "line", "y": "total"})
        q = _read_queries()["t"]
        assert q["chart"] == "line"
        assert q["y"] == "total"
        assert q["trend"] == 6

    def test_pivot_accepts_stacked(self):
        _clean()
        svc.save_query_entry("p", {"where": "type=expense", "time": "tm",
                                   "pivot": "category, source",
                                   "chart": "stacked"})
        q = _read_queries()["p"]
        assert q["pivot"] == ["category", "source"]
        assert q["chart"] == "stacked"

    def test_unknown_chart_value_rejected(self):
        _clean()
        with pytest.raises(PTOSError, match="Unknown chart"):
            svc.save_query_entry("g", {"where": "type=expense", "time": "tm",
                                       "group": "category", "chart": "pie"})

    def test_incompatible_combo_rejected(self):
        _clean()
        with pytest.raises(PTOSError, match="not valid for a group"):
            svc.save_query_entry("g", {"where": "type=expense", "time": "tm",
                                       "group": "category", "chart": "stacked"})
        with pytest.raises(PTOSError, match="not valid for a trend"):
            svc.save_query_entry("t", {"where": "type=expense", "time": "tm",
                                       "trend": "6", "chart": "hbar"})

    def test_chart_on_records_query_rejected(self):
        _clean()
        with pytest.raises(PTOSError, match="group, trend or pivot"):
            svc.save_query_entry("r", {"where": "type=expense", "time": "tm",
                                       "chart": "bar"})

    def test_y_only_on_trend(self):
        _clean()
        with pytest.raises(PTOSError, match="only applies to trend"):
            svc.save_query_entry("g", {"where": "type=expense", "time": "tm",
                                       "group": "category", "y": "total"})

    def test_invalid_trend_value_rejected(self):
        _clean()
        with pytest.raises(PTOSError, match="trend must be"):
            svc.save_query_entry("t", {"where": "type=expense", "time": "tm",
                                       "trend": "abc"})
        with pytest.raises(PTOSError, match="two fields"):
            svc.save_query_entry("p", {"where": "type=expense", "time": "tm",
                                       "pivot": "category"})


class TestChartKeyOwnership:
    def test_clearing_chart_removes_key(self):
        _clean()
        svc.save_query_entry("g", {"where": "type=expense", "time": "tm",
                                   "group": "category", "chart": "bar"})
        assert _read_queries()["g"]["chart"] == "bar"
        svc.save_query_entry("g", {"where": "type=expense", "time": "tm",
                                   "group": "category", "chart": ""})
        assert "chart" not in _read_queries()["g"]

    def test_clearing_trend_removes_key(self):
        _clean()
        svc.save_query_entry("t", {"where": "type=expense", "time": "tm",
                                   "trend": "6", "chart": "line"})
        assert "trend" in _read_queries()["t"]
        svc.save_query_entry("t", {"where": "type=expense", "time": "tm",
                                   "trend": "", "chart": ""})
        q = _read_queries()["t"]
        assert "trend" not in q
        assert "chart" not in q

    def test_cfg_without_chart_keys_preserves_them(self):
        _clean()
        svc.save_query_entry("g", {"where": "type=expense", "time": "tm",
                                   "group": "category", "chart": "bar"})
        svc.save_query_entry("g", {"where": "type=expense AND tag=x",
                                   "time": "tm", "group": "category"})
        q = _read_queries()["g"]
        assert q["chart"] == "bar"
        assert q["where"] == "type=expense AND tag=x"

    def test_full_save_owned_clear(self):
        _clean()
        svc.save_queries_full(
            {"t": {"where": "type=expense", "time": "tm", "trend": 6,
                   "chart": "line"}}, {}, {})
        assert "trend" in _read_queries()["t"]
        svc.save_queries_full(
            {"t": {"where": "type=expense", "time": "tm", "trend": "",
                   "pivot": "", "chart": "", "y": ""}}, {}, {})
        q = _read_queries()["t"]
        assert "trend" not in q
        assert "chart" not in q


class TestRunQueryChartPayload:
    def test_group_payload_carries_chart(self):
        _clean()
        _set_queries({"g": {"where": "type=expense", "time": "tm",
                            "group": "category", "chart": "hbar"}})
        _seed_expenses()
        r = svc.run_query("g")
        assert r["kind"] == "group"
        assert r["chart"] == "hbar"

    def test_trend_payload_carries_chart_and_y(self):
        _clean()
        _set_queries({"t": {"where": "type=expense", "time": "tm",
                            "trend": 3, "chart": "line", "y": "count"}})
        _seed_expenses()
        r = svc.run_query("t")
        assert r["kind"] == "trend"
        assert r["chart"] == "line"
        assert r["y"] == "count"

    def test_records_payload_has_no_chart(self):
        _clean()
        _set_queries({"r": {"where": "type=expense", "time": "tm"}})
        _seed_expenses()
        r = svc.run_query("r")
        assert r["kind"] == "records"
        assert "chart" not in r

    def test_hand_edited_invalid_chart_falls_back(self):
        _clean()
        _set_queries({"g": {"where": "type=expense", "time": "tm",
                            "group": "category", "chart": "stacked"}})
        _seed_expenses()
        r = svc.run_query("g")
        assert r["kind"] == "group"
        assert "chart" not in r

    def test_override_param_wins(self):
        _clean()
        _set_queries({"g": {"where": "type=expense", "time": "tm",
                            "group": "category", "chart": "bar"}})
        _seed_expenses()
        r = svc.run_query("g", chart="hbar")
        assert r["chart"] == "hbar"

    def test_invalid_override_raises(self):
        _clean()
        _set_queries({"g": {"where": "type=expense", "time": "tm",
                            "group": "category"}})
        _seed_expenses()
        with pytest.raises(PTOSError):
            svc.run_query("g", chart="stacked")


class TestEmbedChartOverride:
    def test_embed_chart_override(self):
        _clean()
        _set_queries({"g": {"where": "type=expense", "time": "tm",
                            "group": "category"}})
        _seed_expenses()
        r = svc.resolve_embed({"name": "g", "view": "group", "chart": "hbar"})
        assert r["kind"] == "group"
        assert r["chart"] == "hbar"

    def test_embed_saved_chart_flows_through(self):
        _clean()
        _set_queries({"g": {"where": "type=expense", "time": "tm",
                            "group": "category", "chart": "bar"}})
        _seed_expenses()
        r = svc.resolve_embed({"name": "g"})
        assert r["chart"] == "bar"

    def test_embed_unknown_chart_raises(self):
        _clean()
        _set_queries({"g": {"where": "type=expense", "time": "tm",
                            "group": "category"}})
        _seed_expenses()
        with pytest.raises(PTOSError, match="Unknown chart"):
            svc.resolve_embed({"name": "g", "chart": "pie"})

    def test_embed_chart_on_records_query_raises(self):
        _clean()
        _set_queries({"r": {"where": "type=expense", "time": "tm"}})
        _seed_expenses()
        with pytest.raises(PTOSError, match="group, trend or pivot"):
            svc.resolve_embed({"name": "r", "view": "records", "chart": "bar"})


class TestWebQueriesRun:
    def test_run_returns_chart_payload(self):
        _clean()
        _set_queries({"g": {"where": "type=expense", "time": "tm",
                            "group": "category", "chart": "hbar"}})
        _seed_expenses()
        from ptos_web import app
        resp = app.test_client().post(
            "/queries/run", json={"name": "g", "time": "tm"})
        payload = resp.get_json()
        assert payload["ok"] is True
        assert payload["data"]["kind"] == "group"
        assert payload["data"]["chart"] == "hbar"


class TestWidgetsJsStatic:
    def _read(self):
        with open(WIDGETS_JS, encoding="utf-8") as f:
            return f.read()

    def test_chart_functions_defined(self):
        src = self._read()
        for fn in ("function chartBar(", "function chartHBar(",
                   "function chartLine(", "function chartStacked(",
                   "function renderChart(", "function qtWrap("):
            assert fn in src, f"missing {fn}"

    def test_hbar_axis_is_left_to_right_and_precedence_safe(self):
        # chartHBar must use _chartX (value grows left→right, zero at ml).
        # The tick rounding must parenthesize (ml + offset) * 100 — the old
        # `ml + _chartY(...) * 100` bound *100 to the offset only, so ticks
        # rendered near the left margin while bars were drawn full-width
        # (a 404.8k bar "barely crossed" the misplaced 200k tick).
        src = self._read()
        assert "function _chartX(" in src
        hbar = src[src.index("function chartHBar("):src.index("function chartLine(")]
        assert "_chartX(dom, t, pw)" in hbar
        assert "_chartX(dom, 0, pw)" in hbar
        assert "ml + _chartY(dom, t, pw) * 100" not in hbar
        assert "Math.round((ml + _chartX(dom, t, pw)) * 100)" in hbar

    def test_renderers_call_toggle_when_chart_set(self):
        src = self._read()
        assert src.count("qtWrap(") >= 4  # def + 3 renderers
        assert "d.chart" in src

    def test_labels_escaped(self):
        src = self._read()
        chart_block = src.split("Charts (inline SVG")[1]
        assert "esc(" in chart_block

    def test_no_hardcoded_hex_in_chart_block(self):
        src = self._read()
        chart_block = src.split("Charts (inline SVG")[1]
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", chart_block), \
            "chart code must use CSS variables, not hex colors"

    def test_svg_accessibility(self):
        src = self._read()
        assert 'role="img"' in src
        assert "aria-label" in src
        assert "<title>" in src

    def test_palette_uses_css_variables(self):
        src = self._read()
        assert 'var(--chart-' in src
        assert "var(--chart-other)" in src


class TestCssPalette:
    def test_base_css_defines_chart_palette(self):
        with open(BASE_CSS, encoding="utf-8") as f:
            css = f.read()
        for i in range(1, 9):
            assert f"--chart-{i}:" in css, f"missing --chart-{i}"
        assert "--chart-other:" in css

    def test_components_css_toggle_styles(self):
        with open(COMPONENTS_CSS, encoding="utf-8") as f:
            css = f.read()
        assert ".qt-toggle" in css
        assert ".qt-legend" in css
        assert ".qt-swatch" in css


class TestQueryBuilderChartControls:
    def _read(self):
        with open(QB_HTML, encoding="utf-8") as f:
            return f.read()

    def test_chart_dropdown_present(self):
        src = self._read()
        assert 'id="qb-chart"' in src
        assert "_chartOptsHtml" in src
        assert "_refreshChartSelect" in src

    def test_chart_helpers_defined_before_boot(self):
        # The boot IIFE synchronously calls select() → _buildQueryEditor(),
        # which reads _CHART_OPTS. var assignments don't hoist their values,
        # so declaring the map below the boot throws on page load and kills
        # the rest of the editor (no Options card, no Live records).
        src = self._read()
        boot = src.index("// ── Boot ──")
        assert src.index("var _CHART_OPTS") < boot
        assert src.index("function _chartOptsHtml") < boot
        assert src.index("function _chartViewKind") < boot
        assert src.count("var _CHART_OPTS") == 1
        assert src.count("function _chartOptsHtml") == 1

    def test_state_carries_chart_keys(self):
        src = self._read()
        assert 'chart:        v.chart||""' in src
        assert 'trend:' in src
        assert 'pivot:' in src

    def test_save_payload_includes_chart_keys(self):
        src = self._read()
        assert "trend:q.trend" in src
        assert "chart:q.chart" in src

    def test_preview_shows_chart(self):
        src = self._read()
        assert "chart = " in src

    def test_live_preview_uses_adhoc_endpoint(self):
        # Group/trend/pivot editor state must run through the real query
        # pipeline (charts included), not the raw /browse/run record scan.
        src = self._read()
        assert "/api/query-builder/run" in src
        assert "av('/static/js/widgets.js')" in src

    def test_no_local_summarybar_collision(self):
        # widgets.js owns summaryBar; a local redefinition would shadow it
        # and break renderGroup's summary strip.
        src = self._read()
        assert "function summaryBar" not in src


class TestAdhocQuery:
    def test_group_with_chart(self):
        _seed_expenses()
        r = svc.run_adhoc_query({"where": ["type=expense"], "group": "category",
                                 "chart": "bar"})
        assert r["kind"] == "group"
        assert r["chart"] == "bar"
        assert r["rows"]

    def test_trend_with_chart_and_y(self):
        _seed_expenses()
        r = svc.run_adhoc_query({"where": ["type=expense"], "trend": "3",
                                 "chart": "line", "y": "total"})
        assert r["kind"] == "trend"
        assert r["chart"] == "line"
        assert r["y"] == "total"

    def test_pivot_from_comma_string(self):
        _seed_expenses()
        r = svc.run_adhoc_query({"where": ["type=expense"],
                                 "pivot": "category, month"})
        assert r["kind"] == "pivot"
        assert r["query_pivot"] == ["category", "month"]

    def test_invalid_chart_raises(self):
        _seed_expenses()
        with pytest.raises(PTOSError):
            svc.run_adhoc_query({"where": ["type=expense"], "group": "category",
                                 "chart": "pie"})

    def test_chart_on_records_raises(self):
        _seed_expenses()
        with pytest.raises(PTOSError):
            svc.run_adhoc_query({"where": ["type=expense"], "chart": "bar"})

    def test_plain_cfg_falls_back_to_records(self):
        _seed_expenses()
        r = svc.run_adhoc_query({"where": ["type=expense"]})
        assert r["kind"] == "records"
        assert "chart" not in r

    def test_where_and_expr_merge(self):
        _seed_expenses()
        r = svc.run_adhoc_query({"where": ["type=expense"],
                                 "expr": "category=food", "group": "category"})
        assert r["kind"] == "group"
        assert r["rows"], "AND-merged filter should still match seeded food record"

    def test_empty_chart_means_no_chart(self):
        _seed_expenses()
        r = svc.run_adhoc_query({"where": ["type=expense"], "group": "category",
                                 "chart": ""})
        assert r["kind"] == "group"
        assert "chart" not in r


class TestAdhocWebRoute:
    def test_run_returns_adhoc_payload(self):
        _seed_expenses()
        from ptos_web import app
        resp = app.test_client().post(
            "/api/query-builder/run",
            json={"where": ["type=expense"], "group": "category",
                  "chart": "bar", "name": "(unsaved)"})
        payload = resp.get_json()
        assert payload["ok"] is True
        assert payload["data"]["kind"] == "group"
        assert payload["data"]["chart"] == "bar"
        assert payload["data"]["query_name"] == "(unsaved)"

    def test_bad_chart_is_user_error(self):
        _seed_expenses()
        from ptos_web import app
        resp = app.test_client().post(
            "/api/query-builder/run",
            json={"where": ["type=expense"], "group": "category",
                  "chart": "pie"})
        payload = resp.get_json()
        assert payload["ok"] is False
        assert "pie" in payload["error"]


class TestStartersShipCharts:
    def test_starter_queries_have_chart_keys(self):
        with open(STARTER_QUERIES, encoding="utf-8") as f:
            text = f.read()
        assert 'chart = "hbar"' in text
        assert 'chart = "bar"' in text

    def test_starter_charts_are_valid(self):
        import tomllib
        with open(STARTER_QUERIES, "rb") as f:
            data = tomllib.load(f)
        charts = {k: v["chart"] for k, v in data.items()
                  if isinstance(v, dict) and "chart" in v}
        assert charts, "starters should ship chart examples"
        for name, chart in charts.items():
            entry = data[name]
            view = ("group" if entry.get("group")
                    else "trend" if entry.get("trend")
                    else "pivot" if entry.get("pivot") else None)
            assert view, f"{name} has chart but no group/trend/pivot"
            assert chart in svc._CHART_BY_VIEW[view], \
                f"{name}: chart={chart} invalid for {view}"
