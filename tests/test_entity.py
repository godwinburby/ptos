import os
import datetime as dt
import tomli_w
import ptos
import ptos_cli
import ptos_service as svc
import pytest


def _write_records(lines):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    with open(os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log"),
              "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _clean_cache():
    ptos._CACHE.clear()


class TestQuoteFilterValue:
    def test_plain_value_untouched(self):
        assert ptos.quote_filter_value("vka7") == "vka7"
        assert ptos.quote_filter_value("cerena") == "cerena"
        assert ptos.quote_filter_value(100) == "100"

    def test_spaced_value_quoted(self):
        assert ptos.quote_filter_value("cerena binu") == '"cerena binu"'

    def test_parens_quoted(self):
        assert ptos.quote_filter_value("john (jr)") == '"john (jr)"'

    def test_value_with_double_quote_uses_single_quotes(self):
        assert ptos.quote_filter_value('say "hi" now') == "'say \"hi\" now'"

    def test_value_with_both_quotes_left_alone(self):
        v = 'a"b\'c d'
        assert ptos.quote_filter_value(v) == v

    def test_round_trips_through_the_filter_parser(self):
        kv = {"name": "cerena binu"}
        assert ptos.apply_where(
            kv, [f"name={ptos.quote_filter_value('cerena binu')}"])
        assert not ptos.apply_where(
            {"name": "cerena"}, [f"name={ptos.quote_filter_value('cerena binu')}"])
        assert not ptos.apply_where(
            kv, [f"name={ptos.quote_filter_value('cerena')}"])


class TestGetEntityData:
    def test_basic_entity(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense client_code=vka7 amount=100 note=repair",
            f"{today} type=income client_code=vka7 amount=500 note=refund",
            f"{today} type=journal client_code=vka7 note=meeting",
        ])
        data = svc.get_entity_data("client_code", "vka7")
        assert data["field"] == "client_code"
        assert data["value"] == "vka7"
        assert data["label"] == "vka7"
        assert data["count"] == 3
        assert "expense" in data["types"]
        assert "income" in data["types"]
        assert "journal" in data["types"]
        assert data["types"]["expense"] == 1
        assert data["types"]["income"] == 1
        assert data["types"]["journal"] == 1

    def test_name_detection(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense client_code=abc name=Alice amount=100",
            f"{today} type=income client_code=abc amount=500",
        ])
        data = svc.get_entity_data("client_code", "abc")
        assert data["label"] == "Alice"

    def test_no_name_falls_back_to_value(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense client_code=xyz amount=100",
        ])
        data = svc.get_entity_data("client_code", "xyz")
        assert data["label"] == "xyz"

    def test_total_amount(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense client_code=e1 amount=1000",
            f"{today} type=expense client_code=e1 amount=2500",
        ])
        data = svc.get_entity_data("client_code", "e1")
        assert data["total_amount"] == 3500

    def test_type_filter(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense client_code=vka7 amount=100",
            f"{today} type=income client_code=vka7 amount=500",
        ])
        data = svc.get_entity_data("client_code", "vka7", type_filter="expense")
        assert data["count"] == 1
        assert data["type_filter"] == "expense"
        assert "expense" in data["types"]
        assert "income" not in data["types"]

    def test_empty_entity(self):
        _clean_cache()
        _write_records([])
        data = svc.get_entity_data("client_code", "nobody")
        assert data["count"] == 0
        assert data["types"] == {}
        assert data["label"] == "nobody"

    def test_numeric_fields_detected(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense client_code=e1 amount=1000",
            f"{today} type=expense client_code=e1 amount=2500",
        ])
        data = svc.get_entity_data("client_code", "e1")
        assert "amount" in data["numeric_fields"]
        assert data["numeric_fields"]["amount"] == 3500

    def test_amount_by_type(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=income client_code=vka7 amount=95750",
            f"{today} type=expense client_code=vka7 amount=10000",
        ])
        data = svc.get_entity_data("client_code", "vka7")
        assert data["amount_by_type"]["income"] == 95750
        assert data["amount_by_type"]["expense"] == 10000

    def test_value_with_spaces(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f'{today} type=expense client_code=c1 name="cerena binu" amount=100',
            f"{today} type=expense client_code=c2 name=cerena amount=50",
            f'{today} type=expense client_code=c3 name="binu thomas" amount=10',
        ])
        data = svc.get_entity_data("name", "cerena binu")
        assert data["count"] == 1
        assert data["records"][0]["client_code"] == "c1"
        assert data["label"] == "cerena binu"

    def test_value_with_spaces_stays_exact(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f'{today} type=expense client_code=c1 name="cerena binu" amount=100',
            f"{today} type=expense client_code=c2 name=cerena amount=50",
        ])
        data = svc.get_entity_data("name", "cerena")
        assert data["count"] == 1
        assert data["records"][0]["client_code"] == "c2"

    def test_value_with_spaces_type_filter(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f'{today} type=expense client_code=c1 name="cerena binu" amount=100',
            f'{today} type=income client_code=c1 name="cerena binu" amount=500',
        ])
        data = svc.get_entity_data("name", "cerena binu", type_filter="expense")
        assert data["count"] == 1
        assert data["types"] == {"expense": 1}


class TestEntityWebRoute:
    def test_entity_page_basic(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense client_code=vka7 name=thankam amount=100",
            f"{today} type=income client_code=vka7 amount=500",
        ])
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/entity?field=client_code&value=vka7")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "client_code=vka7" in html
        assert "thankam" in html

    def test_entity_page_missing_params(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/entity")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Look up" in html

    def test_entity_page_with_type_filter(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense client_code=vka7 amount=100",
            f"{today} type=income client_code=vka7 amount=500",
        ])
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/entity?field=client_code&value=vka7&type=expense")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "expense" in html

    def test_entity_api_run(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/entity/run",
                           json={"field": "client_code", "value": "vka7"})
        data = resp.get_json()
        assert data["ok"] is True
        assert "/entity?field=client_code&value=vka7" in data["redirect"]

    def test_entity_api_run_missing_fields(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/entity/run", json={})
        data = resp.get_json()
        assert data["ok"] is False
        assert "required" in data["error"].lower()

    def test_entity_api_run_encodes_spaced_value(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/entity/run",
                           json={"field": "name", "value": "cerena binu"})
        data = resp.get_json()
        assert data["ok"] is True
        assert data["redirect"].startswith("/entity?")
        assert "value=cerena+binu" in data["redirect"]

    def test_entity_page_value_with_spaces(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f'{today} type=expense client_code=c1 name="cerena binu" amount=100',
            f"{today} type=expense client_code=c2 name=cerena amount=50",
        ])
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/entity", query_string={"field": "name",
                                                   "value": "cerena binu"})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "cerena binu" in html
        assert "client_code" in html
        assert "value=cerena%20binu" in html
        assert "entity_name_cerena%20binu" in html
        assert "value=cerena binu" not in html


class TestFunnelStrip:
    def test_board_has_columns(self):
        _clean_cache()
        today = dt.date.today()
        queries = ptos.get_queries()
        queries["board.test_funnel"] = {
            "columns": ["expense", "income"],
            "time_window": "this-month",
        }
        with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
            tomli_w.dump(queries, w.stream)
        ptos._invalidate_all()

        _write_records([
            f"{today} type=expense client_code=a1 amount=100",
            f"{today} type=expense client_code=a2 amount=200",
            f"{today} type=income client_code=a1 amount=500",
        ])
        data = svc.get_board_data("test_funnel")
        assert data["columns"] == ["expense", "income"]
        assert data["counts"]["expense"] == 2
        assert data["counts"]["income"] == 1

    def test_board_funnel_strip_rendered(self):
        _clean_cache()
        today = dt.date.today()
        queries = ptos.get_queries()
        queries["board.test_funnel2"] = {
            "columns": ["expense", "income"],
            "time_window": "this-month",
        }
        with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
            tomli_w.dump(queries, w.stream)
        ptos._invalidate_all()

        _write_records([
            f"{today} type=expense client_code=a1 amount=100",
            f"{today} type=income client_code=a1 amount=500",
        ])
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/board?board=test_funnel2")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "funnel-strip" in html
        assert "expense" in html
        assert "income" in html


class TestCLIEntity:
    def test_entity_cli_basic(self, monkeypatch, capsys):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense client_code=vka7 name=thankam amount=100",
        ])
        monkeypatch.setattr("sys.argv", ["ptos", "--entity", "client_code=vka7"])
        ptos_cli.main()
        out = capsys.readouterr().out
        assert "client_code=vka7" in out
        assert "thankam" in out
        assert "1 record" in out

    def test_entity_cli_missing_equals(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["ptos", "--entity", "vka7"])
        with pytest.raises(SystemExit):
            ptos_cli.main()

    def test_entity_cli_value_with_spaces(self, monkeypatch, capsys):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f'{today} type=expense client_code=c1 name="cerena binu" amount=100',
            f"{today} type=expense client_code=c2 name=cerena amount=50",
        ])
        monkeypatch.setattr("sys.argv", ["ptos", "--entity", "name=cerena binu"])
        ptos_cli.main()
        out = capsys.readouterr().out
        assert "name=cerena binu" in out
        assert "1 record" in out
        assert "cerena binu" in out

    def test_entity_cli_quoted_value_with_spaces(self, monkeypatch, capsys):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f'{today} type=expense client_code=c1 name="cerena binu" amount=100',
        ])
        monkeypatch.setattr("sys.argv",
                            ["ptos", "--entity", 'name="cerena binu"'])
        ptos_cli.main()
        out = capsys.readouterr().out
        assert "1 record" in out
        assert "cerena binu" in out


class TestEntitySuggestions:
    def test_cross_type_fields_detected(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense domain=self category=food amount=100",
            f"{today} type=income source=salary amount=500",
            f"{today} type=expense domain=work category=supplies amount=200",
        ])
        suggestions = svc.get_entity_suggestions()
        fields = [s["field"] for s in suggestions]
        # amount on expense+income+investment = cross-type
        assert "amount" in fields
        # date/type/note excluded
        assert "date" not in fields
        assert "type" not in fields

    def test_type_count(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense domain=self category=food amount=100 project=proj_a",
            f"{today} type=income source=salary amount=500 project=proj_b",
        ])
        suggestions = svc.get_entity_suggestions()
        by_field = {s["field"]: s for s in suggestions}
        from ptos import get_schema
        n_types = len(get_schema()["types"]["allowed"])
        # amount on expense+income+investment = 3 types
        assert len(by_field["amount"]["types"]) == 3
        # project is global = all allowed types
        assert len(by_field["project"]["types"]) == n_types

    def test_value_count(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense domain=self category=food amount=100",
            f"{today} type=income source=salary amount=500",
            f"{today} type=expense domain=work category=supplies amount=200",
        ])
        suggestions = svc.get_entity_suggestions()
        by_field = {s["field"]: s for s in suggestions}
        # 3 distinct amount values: 100, 500, 200
        assert by_field["amount"]["count"] == 3

    def test_single_type_field_excluded(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense domain=self category=food amount=100 pay_method=cash",
        ])
        suggestions = svc.get_entity_suggestions()
        fields = [s["field"] for s in suggestions]
        # pay_method only on expense (1 type) → excluded
        assert "pay_method" not in fields
        # domain on expense+learning = 2 types → included
        assert "domain" in fields

    def test_empty_records(self):
        _clean_cache()
        _write_records([])
        # cross-type fields still detected from schema even with no records
        suggestions = svc.get_entity_suggestions()
        fields = [s["field"] for s in suggestions]
        assert "amount" in fields
        # but value counts are all 0
        by_field = {s["field"]: s for s in suggestions}
        assert by_field["amount"]["count"] == 0

    def test_sorted_by_type_count_desc(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense domain=self category=food amount=100 project=proj_a",
            f"{today} type=income source=salary amount=500",
        ])
        suggestions = svc.get_entity_suggestions()
        # project (global, 10 types) should come before amount (3 types)
        if len(suggestions) >= 2:
            assert len(suggestions[0]["types"]) >= len(suggestions[1]["types"])


class TestEntityFieldValues:
    def test_basic_values(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense domain=self category=food amount=100",
            f"{today} type=income source=salary amount=500",
            f"{today} type=expense domain=work category=supplies amount=200",
        ])
        values, total = svc.get_entity_field_values("amount")
        assert total == 3
        assert set(values) == {"100", "500", "200"}

    def test_returns_all_values(self):
        _clean_cache()
        today = dt.date.today()
        lines = [f"{today} type=expense domain=self category=food amount={i}" for i in range(25)]
        _write_records(lines)
        values, total = svc.get_entity_field_values("amount")
        assert total == 25
        assert len(values) == 25

    def test_frequency_ordering(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense domain=self category=food amount=100",
            f"{today} type=expense domain=self category=food amount=100",
            f"{today} type=expense domain=self category=food amount=100",
            f"{today} type=income source=salary amount=500",
        ])
        values, total = svc.get_entity_field_values("amount")
        assert values[0] == "100"
        assert total == 2

    def test_field_not_in_records(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense domain=self category=food amount=100",
        ])
        values, total = svc.get_entity_field_values("nonexistent")
        assert total == 0
        assert values == []

    def test_empty_records(self):
        _clean_cache()
        _write_records([])
        values, total = svc.get_entity_field_values("amount")
        assert total == 0
        assert values == []

    def test_api_endpoint(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense domain=self category=food amount=100",
            f"{today} type=income source=salary amount=500",
        ])
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/entity/field-values/amount")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["field"] == "amount"
        assert data["total"] == 2
        assert set(data["values"]) == {"100", "500"}

    def test_api_endpoint_with_time(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense domain=self category=food amount=100",
        ])
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/entity/field-values/amount?time=ty")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1


class TestEntityFieldValuesErrorReporting:
    """A failed lookup must be distinguishable from a field with no values.

    The web value panel renders an empty chip list for both, which previously
    made a dead endpoint look exactly like "this field has no values".
    """

    def test_api_error_absent_on_success(self, monkeypatch):
        _clean_cache()
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/entity/field-values/amount")
        assert resp.status_code == 200
        assert resp.get_json()["error"] is None

    def test_api_reports_error_when_lookup_raises(self, monkeypatch):
        _clean_cache()

        def _boom(field, time="ty"):
            raise RuntimeError("scan exploded")

        monkeypatch.setattr(svc, "get_entity_field_values", _boom)
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/entity/field-values/amount")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["error"] == "scan exploded"
        assert data["values"] == []
        assert data["total"] == 0
        assert data["field"] == "amount"

    def test_api_error_is_logged(self, monkeypatch, caplog):
        _clean_cache()

        def _boom(field, time="ty"):
            raise RuntimeError("scan exploded")

        monkeypatch.setattr(svc, "get_entity_field_values", _boom)
        from ptos_web import app
        with caplog.at_level("ERROR", logger="ptos_web"):
            app.test_client().get("/api/entity/field-values/amount")
        assert any("scan exploded" in r.getMessage() or "field-values" in r.getMessage()
                   for r in caplog.records)

    def test_api_repeatable_across_requests(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([
            f"{today} type=expense domain=self category=food amount=100",
            f"{today} type=expense domain=work category=fuel amount=250",
            f"{today} type=income source=salary amount=500",
        ])
        from ptos_web import app
        client = app.test_client()
        seen = []
        for _ in range(3):
            data = client.get("/api/entity/field-values/amount").get_json()
            seen.append((data["values"], data["total"], data["error"]))
        assert seen[0] == seen[1] == seen[2]
        assert seen[0][1] == 3


class TestEntityValuePanelMarkup:
    """Contract the inline value-panel JS depends on.

    There is no JS test runner in this project, so these pin the markup/CSS
    hooks the script needs so a template edit cannot silently break it.
    """

    def _landing_html(self):
        from ptos_web import app
        return app.test_client().get("/entity").get_data(as_text=True)

    def test_status_node_present(self):
        html = self._landing_html()
        assert 'id="entity-val-status"' in html
        assert "entity-val-status" in html
        assert ".entity-val-status.error" in html

    def test_chip_toggle_wiring(self):
        from ptos_service import get_entity_suggestions
        from ptos_web import app
        html = app.test_client().get("/entity").get_data(as_text=True)
        # the script the chips call into must be exposed on window
        assert "window.toggleField = toggleField" in html
        assert "function toggleField" in html
        assert "loadValues" in html
        assert "AbortController" in html
        # chips carry the field they toggle
        assert 'onclick="toggleField(' in html
        assert "data-field=" in html

    def test_landing_page_has_panel_nodes(self):
        html = self._landing_html()
        for node_id in ("entity-val-panel", "entity-val-chips", "entity-val-datalist",
                        "entity-val-more", "entity-val-total", "entity-val-field",
                        "entity-val-text", "entity-field", "entity-chips"):
            assert f'id="{node_id}"' in html, node_id
