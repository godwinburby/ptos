"""Tests for the live home page (Phase 3 of the live-widgets spec).

The home route bakes its widget specs into #home-widget-specs as
[{section, kind, body}] and home_widgets.js resolves them in one batch.
There is no JS test runner, so the client pins are static scans; the
server side is tested through the rendered blob and the batch endpoint.
"""
import json
import os
import re
import tomllib

import tomli_w

import ptos
import ptos_service as svc


def _set_queries(d):
    with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
        tomli_w.dump(d, w.stream)
    ptos._invalidate_all()


def _write_records(lines):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    year = ptos.today().year
    with open(os.path.join(ptos.RECORDS_DIR, f"{year}.log"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _client():
    from ptos_web import app
    return app.test_client()


def _home_specs(query_string=""):
    body = _client().get("/" + query_string).get_data(as_text=True)
    m = re.search(
        r'<script type="application/json" id="home-widget-specs">'
        r"(.*?)</script>", body, re.S)
    assert m, "home-widget-specs blob missing"
    return json.loads(m.group(1)), body


def _by_kind(specs, kind, section=None):
    return [s for s in specs
            if s["kind"] == kind
            and (section is None or s["section"] == section)]


def _parse_body(spec):
    return tomllib.loads(spec["body"])


def _batch(bodies):
    resp = _client().post("/api/widgets/resolve", json={
        "items": [{"id": i, "body": b} for i, b in enumerate(bodies)]
    }).get_json()
    assert resp.get("ok") is True
    return resp["results"]


def _wipe_queries():
    _set_queries({})


class TestHomeSpecBlob:
    def test_empty_workspace_default_specs(self):
        _wipe_queries()
        specs, _ = _home_specs()
        kinds = [s["kind"] for s in specs]
        assert "todo_summary" in kinds
        assert "journal" in kinds
        assert "capture" in kinds
        assert "records" in kinds
        assert not _by_kind(specs, "dashboard")
        assert not _by_kind(specs, "threshold")
        assert not _by_kind(specs, "due")
        assert not _by_kind(specs, "quick_add_multi")

    def test_sections_are_the_four_known_ones(self):
        specs, _ = _home_specs()
        assert set(s["section"] for s in specs) <= {
            "overview", "attention", "quickadd", "today"}

    def test_records_default_is_today_with_limit_8(self):
        specs, _ = _home_specs()
        r = _parse_body(_by_kind(specs, "records")[0])
        assert r["time"] == "td"
        assert r["title"] == "Today's Records"
        assert r["limit"] == 8
        assert r["where"] == []

    def test_records_with_time_window_carries_title(self):
        specs, _ = _home_specs("?time=lm")
        r = _parse_body(_by_kind(specs, "records")[0])
        assert r["time"] == "lm"
        assert r["title"].startswith("Records · ")
        assert "limit" in r and r["limit"] == 8

    def test_records_with_from_date_uses_range(self):
        specs, _ = _home_specs("?from_date=2026-01-01&to_date=2026-01-31")
        r = _parse_body(_by_kind(specs, "records")[0])
        assert r["from_date"] == "2026-01-01"
        assert r["to_date"] == "2026-01-31"
        assert "time" not in r
        assert r["title"].startswith("Records · ")

    def test_due_spec_when_configured(self):
        _set_queries({"due.default": {"days": 7}})
        specs, _ = _home_specs()
        due = _by_kind(specs, "due", "attention")
        assert len(due) == 1
        d = _parse_body(due[0])
        assert d["name"] == "default"
        assert d["title"] == "Overdue Records"
        assert d["limit"] == 5

    def test_due_unknown_name_falls_back_to_default(self):
        _set_queries({"due.default": {"days": 7}})
        specs, _ = _home_specs("?due=ghost")
        assert _parse_body(_by_kind(specs, "due")[0])["name"] == "default"

    def test_threshold_spec_when_configured(self):
        _set_queries({"threshold.budget": {
            "metric": "m1", "direction": "max", "target": 10}})
        specs, _ = _home_specs()
        thr = _by_kind(specs, "threshold", "overview")
        assert len(thr) == 1
        assert _parse_body(thr[0])["title"] == "Thresholds"

    def test_quick_add_gated_on_frequent_presets(self):
        presets_path = ptos.PRESETS_PATH
        os.makedirs(os.path.dirname(presets_path), exist_ok=True)
        with open(presets_path, "w", encoding="utf-8") as f:
            for i in range(3):
                f.write(f'[presets.p{i}]\ntype = "expense"\nuse_count = {3 - i}\n')
        ptos._invalidate("presets")
        specs, _ = _home_specs()
        qa = _by_kind(specs, "quick_add", "quickadd")
        assert len(qa) == 1
        assert _parse_body(qa[0])["title"] == "Quick Add"

    def test_quick_add_multi_gated_on_multi_presets(self, monkeypatch):
        monkeypatch.setattr(svc, "get_multi_presets",
                            lambda: {"morning": "a, b"})
        specs, _ = _home_specs()
        multi = _by_kind(specs, "quick_add_multi", "quickadd")
        assert len(multi) == 1
        assert _parse_body(multi[0])["title"] == "Quick Add (multi)"

    def test_todo_summary_and_journal_always_present(self):
        specs, _ = _home_specs()
        assert len(_by_kind(specs, "todo_summary", "attention")) == 1
        assert len(_by_kind(specs, "journal", "attention")) == 1
        assert _parse_body(_by_kind(specs, "todo_summary")[0])["title"] == "Todos"
        assert _parse_body(_by_kind(specs, "journal")[0])["title"] == "Journal"

    def test_capture_always_present(self):
        specs, _ = _home_specs()
        assert len(_by_kind(specs, "capture", "quickadd")) == 1


class TestHomeDashboardGating:
    def _seed_dashboard(self):
        _set_queries({
            "dashboards": {"money": {"metrics": []}},
        })

    def test_dashboard_spec_only_when_configured(self):
        self._seed_dashboard()
        specs, _ = _home_specs()
        db = _by_kind(specs, "dashboard", "overview")
        assert len(db) == 1
        d = _parse_body(db[0])
        assert d["name"] == "money"
        assert d["per_query"] is True
        assert "time" not in d

    def test_dashboard_time_window_replaces_per_query(self):
        self._seed_dashboard()
        specs, _ = _home_specs("?time=lm")
        d = _parse_body(_by_kind(specs, "dashboard")[0])
        assert d["time"] == "lm"
        assert "per_query" not in d

    def test_dashboard_from_date_replaces_per_query(self):
        self._seed_dashboard()
        specs, _ = _home_specs("?from_date=2026-02-01&to_date=2026-02-28")
        d = _parse_body(_by_kind(specs, "dashboard")[0])
        assert d["from_date"] == "2026-02-01"
        assert "per_query" not in d

    def test_threshold_follows_time_pick(self):
        _set_queries({"threshold.budget": {
            "metric": "m1", "direction": "max", "target": 10}})
        specs, _ = _home_specs("?time=ty")
        d = _parse_body(_by_kind(specs, "threshold")[0])
        assert d["time"] == "ty"

    def test_custom_time_is_passed_through(self):
        self._seed_dashboard()
        specs, _ = _home_specs("?time=month&custom_time=2026-03")
        d = _parse_body(_by_kind(specs, "dashboard")[0])
        assert d["time"] == "2026-03"


class TestHomeTemplate:
    def _seed_dashboard(self):
        _set_queries({"dashboards": {"money": {"metrics": []}}})

    def test_no_data_placeholder_without_dashboards(self):
        _wipe_queries()
        _, body = _home_specs()
        assert "No data" in body
        assert 'data-home-section="overview"' in body

    def test_four_section_containers(self):
        _, body = _home_specs()
        for section in ("overview", "attention", "quickadd", "today"):
            assert 'data-home-section="%s"' % section in body, section

    def test_widget_scripts_loaded_versioned(self):
        from ptos_web import app
        body = app.test_client().get("/").get_data(as_text=True)
        for name in ("record_table.js", "widgets.js", "widget_host.js",
                     "home_widgets.js"):
            assert "/static/js/%s?v=" % name in body, name

    def test_time_select_has_default_option(self):
        self._seed_dashboard()
        from ptos_web import app
        body = app.test_client().get("/").get_data(as_text=True)
        assert ">Default</option>" in body

    def test_due_selector_when_multiple_configs(self):
        _set_queries({"due.default": {"days": 7},
                      "due.work": {"days": 3}})
        from ptos_web import app
        body = app.test_client().get("/").get_data(as_text=True)
        assert "changeDue(this.value)" in body


class TestHomeSpecsResolve:
    def test_todo_summary_resolves(self):
        d = _batch(['view = "todo_summary"\ntitle = "Todos"'])[0]
        assert d["ok"] is True
        assert d["data"]["kind"] == "todo_summary"
        assert d["data"]["title"] == "Todos"
        assert d["data"]["link"] == "/todo"

    def test_journal_resolves(self):
        d = _batch(['view = "journal"'])[0]
        assert d["ok"] is True
        assert d["data"]["kind"] == "journal"

    def test_capture_resolves(self):
        d = _batch(['view = "capture"'])[0]
        assert d["ok"] is True
        assert d["data"]["kind"] == "capture"

    def test_records_nameless_resolves_with_where(self):
        ptos._CACHE.clear()
        today = ptos.today().strftime("%Y-%m-%d")
        _write_records([f"{today} type=expense amount=10 category=food"])
        d = _batch(['view = "records"\nwhere = ["type=expense"]\n'
                    'limit = 5\ntime = "td"'])[0]
        assert d["ok"] is True
        data = d["data"]
        assert data["kind"] == "records"
        assert data["count"] == 1
        assert data["link"] == "/browse"
        assert "field_types" in data

    def test_records_where_string_is_accepted(self):
        ptos._CACHE.clear()
        today = ptos.today().strftime("%Y-%m-%d")
        _write_records([f"{today} type=expense amount=10 category=food"])
        d = _batch(['view = "records"\nwhere = "type=expense"\n'
                    'time = "td"'])[0]
        assert d["ok"] is True
        assert d["data"]["count"] == 1

    def test_records_invalid_where_raises(self):
        d = _batch(['view = "records"\nwhere = 42'])[0]
        assert d["ok"] is False

    def test_threshold_nameless_respects_home_filter(self, monkeypatch):
        ptos._CACHE.clear()
        _set_queries({"threshold.budget": {
            "metric": "m1", "direction": "max", "target": 10},
            "threshold.secret": {
            "metric": "m1", "direction": "max", "target": 5}})
        real = ptos.get_config

        def cfg_with_filter():
            c = dict(real())
            c["home"] = dict(c.get("home") or {}, thresholds=["budget"])
            return c

        monkeypatch.setattr(ptos, "get_config", cfg_with_filter)
        d = _batch(['view = "threshold"'])[0]
        assert d["ok"] is True
        names = [t["name"] for t in d["data"]["thresholds"]]
        assert "budget" in names
        assert "secret" not in names
        assert d["data"]["link"] == "/thresholds"

    def test_home_records_body_matches_today_window(self):
        specs, _ = _home_specs()
        body = _by_kind(specs, "records")[0]["body"]
        ptos._CACHE.clear()
        today = ptos.today().strftime("%Y-%m-%d")
        _write_records([f"{today} type=expense amount=5 category=food",
                        "2020-01-01 type=expense amount=9 category=food"])
        d = _batch([body])[0]
        assert d["ok"] is True
        assert d["data"]["count"] == 1


class TestHomeWidgetsJsPins:
    def _js(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return open(os.path.join(root, "web_static", "js",
                                 "home_widgets.js"), encoding="utf-8").read()

    def _host_js(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return open(os.path.join(root, "web_static", "js",
                                 "widget_host.js"), encoding="utf-8").read()

    def test_uses_mount_batch_not_per_item_fetch(self):
        src = self._js()
        assert "mountBatch(items" in src
        assert "/api/widgets/resolve" not in src

    def test_reads_the_spec_blob(self):
        assert "home-widget-specs" in self._js()

    def test_interactive_kinds_are_the_four_action_widgets(self):
        src = self._js()
        m = re.search(r"var INTERACTIVE = \{([^}]*)\}", src)
        assert m, "INTERACTIVE map missing"
        assert "records" in m.group(1)
        assert "capture" in m.group(1)
        assert "quick_add" in m.group(1)
        assert "quick_add_multi" in m.group(1)
        assert "todo" not in m.group(1)

    def test_registers_bare_renderers(self):
        src = self._js()
        for kind in ("dashboard", "threshold", "due"):
            assert 'register("%s"' % kind in src, kind
        assert "{ bare: true }" in src

    def test_quick_add_chip_still_navigates_to_add_screen(self):
        src = self._js()
        m = re.search(r"chip = '<a href=\"/add\?preset=' \+ encodeURIComponent\(name\) \+ '"
                      r'[^;]*;', src)
        assert m, "non-instant quick-add chip markup missing"
        chip = m.group(0)
        assert 'href="/add?preset=' in chip
        assert "onclick" not in chip, (
            "non-instant chip must not carry an inline onclick — it blocked "
            "the anchor's navigation to /add?preset= (home quick-add regression)")

    def test_quick_add_chip_click_does_not_prevent_default(self):
        src = self._js()
        m = re.search(r'if \(chip\.classList\.contains\("preset-chip"\)\) \{[^}]*\}', src)
        assert m, "preset-chip click branch missing"
        branch = m.group(0)
        assert "preventDefault" not in branch
        assert "return false" not in branch

    def test_mount_batch_exported_from_widget_host(self):
        assert "mountBatch: mountBatch" in self._host_js()

    def test_widget_host_supports_pregresolving(self):
        src = self._host_js()
        assert "opts.error" in src
        assert "opts.data" in src
        assert "paint(opts.data)" in src
