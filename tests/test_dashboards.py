import os
import pytest

import ptos
import ptos_service

QUERIES = """
[expenses]
where = "type=expense"
time = "this-month"
sum = true

[income]
where = "type=income"
time = "this-month"
sum = true

[metrics.food_ratio]
ratio = ["expenses", "expenses"]

[dashboards.fin]
metrics = ["income", "expenses"]
groups = { "Revenue" = ["income"], "Spend" = ["expenses"] }

[dashboards.mixed]
metrics = ["expenses", "income"]
groups = { "Spend" = ["expenses"] }

[dashboards.legacy]
metrics = ["income", "expenses"]

[dashboards.labelled]
metrics = ["expenses", "income"]
groups = { "Spend" = ["expenses"] }
ungrouped_label = "Everything else"

[dashboards.flatlabelled]
metrics = ["income", "expenses"]
ungrouped_label = "Cash flow"
"""


def _write_queries(content):
    with open(ptos.QUERIES_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    ptos._invalidate_all()


class TestGetDashboardGroups:
    @pytest.fixture(autouse=True)
    def _setup(self):
        _write_queries(QUERIES)

    def test_no_groups_returns_none(self):
        db = ptos_service.get_dashboard("legacy")
        assert db["groups"] is None
        assert [i["raw_name"] for i in db["items"]] == ["income", "expenses"]

    def test_groups_preserve_order_and_ungrouped_first(self):
        db = ptos_service.get_dashboard("mixed")
        groups = db["groups"]
        assert [g["name"] for g in groups] == ["", "Spend"]
        assert [i["raw_name"] for i in groups[0]["items"]] == ["income"]
        assert [i["raw_name"] for i in groups[1]["items"]] == ["expenses"]

    def test_groups_full_partition(self):
        db = ptos_service.get_dashboard("fin")
        groups = db["groups"]
        assert [g["name"] for g in groups] == ["Revenue", "Spend"]
        assert [i["raw_name"] for i in groups[0]["items"]] == ["income"]
        assert [i["raw_name"] for i in groups[1]["items"]] == ["expenses"]
        flat = [i["raw_name"] for i in db["items"]]
        assert flat == ["income", "expenses"]

    def test_groups_single_string_value(self):
        _write_queries(QUERIES.replace('"Spend" = ["expenses"]', '"Spend" = "expenses"'))
        db = ptos_service.get_dashboard("mixed")
        assert [i["raw_name"] for i in db["groups"][1]["items"]] == ["expenses"]

    def test_groups_only_no_metrics_key(self):
        _write_queries("""
[income]
where = "type=income"
time = "this-month"
sum = true

[dashboards.g]
groups = { "Rev" = ["income"] }
""")
        db = ptos_service.get_dashboard("g")
        assert [g["name"] for g in db["groups"]] == ["Rev"]
        assert [i["raw_name"] for i in db["groups"][0]["items"]] == ["income"]

    def test_highlight_attached_to_grouped_items(self):
        cfg = ptos.get_config()
        cfg.setdefault("dashboard", {}).setdefault("highlights", {})["fin"] = {"income": "teal"}
        ptos_service.save_config(cfg)
        db = ptos_service.get_dashboard("fin")
        assert db["groups"][0]["items"][0].get("highlight") == "teal"
        assert db["groups"][1]["items"][0].get("highlight") != "teal"

    def test_unknown_item_in_group(self):
        db = ptos_service.get_dashboard("fin")
        assert all(i["kind"] in ("metric", "query") for gp in db["groups"] for i in gp["items"])

    def test_ungrouped_label_used_for_ungrouped_name(self):
        db = ptos_service.get_dashboard("labelled")
        names = [g["name"] for g in db["groups"]]
        assert names == ["Everything else", "Spend"]
        assert [i["raw_name"] for i in db["groups"][0]["items"]] == ["income"]

    def test_blank_ungrouped_label_returns_empty(self):
        _write_queries(QUERIES.replace('ungrouped_label = "Everything else"', 'ungrouped_label = ""'))
        db = ptos_service.get_dashboard("labelled")
        assert db["groups"][0]["name"] == ""

    def test_flat_dashboard_with_ungrouped_label_returns_labeled_group(self):
        db = ptos_service.get_dashboard("flatlabelled")
        assert db["groups"] == [{"name": "Cash flow", "items": db["items"]}]
        assert [g["name"] for g in db["groups"]] == ["Cash flow"]

    def test_flat_dashboard_without_label_returns_none(self):
        _write_queries(QUERIES.replace('ungrouped_label = "Cash flow"', ''))
        db = ptos_service.get_dashboard("flatlabelled")
        assert db["groups"] is None


class TestHomeGroupedRender:
    @pytest.fixture(autouse=True)
    def _setup(self):
        _write_queries(QUERIES)

    def _resolve(self, qs):
        from ptos_web import app
        import tomli_w
        client = app.test_client()
        resp = client.get("/" + qs)
        assert resp.status_code == 200
        import json, re
        m = re.search(
            r'<script type="application/json" id="home-widget-specs">'
            r"(.*?)</script>", resp.get_data(as_text=True), re.S)
        specs = json.loads(m.group(1))
        bodies = [s["body"] for s in specs if s["kind"] == "dashboard"]
        assert bodies, "no dashboard spec emitted"
        out = client.post("/api/widgets/resolve", json={
            "items": [{"id": i, "body": b} for i, b in enumerate(bodies)]
        }).get_json()
        return out["results"][0]["data"]

    def test_home_renders_group_labels(self):
        d = self._resolve("?dashboard=mixed")
        names = [g["name"] for g in d.get("groups") or []]
        assert "Spend" in names

    def test_home_renders_flat_when_no_groups(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/?dashboard=legacy")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'stat-group-label">Overview' in body
        assert 'stat-group-label">Needs your attention' in body
        assert 'stat-group-label">Quick add' in body
        assert 'stat-group-label">Today' in body

    def test_home_renders_ungrouped_label(self):
        d = self._resolve("?dashboard=labelled")
        names = [g["name"] for g in d.get("groups") or []]
        assert "Everything else" in names

    def test_home_renders_flat_dashboard_ungrouped_label(self):
        d = self._resolve("?dashboard=flatlabelled")
        groups = d.get("groups") or []
        assert any(g["name"] == "Cash flow" for g in groups)


class TestSaveQueriesFullGroups:
    @pytest.fixture(autouse=True)
    def _setup(self):
        _write_queries(QUERIES)

    def test_roundtrip_preserves_groups(self):
        ptos_service.save_queries_full(
            {"expenses": {"where": "type=expense", "time": "this-month", "sum": True},
             "income": {"where": "type=income", "time": "this-month", "sum": True}},
            {"food_ratio": {"ratio": ["expenses", "expenses"]}},
            {"fin": {"metrics": ["income", "expenses"], "groups": {"Revenue": ["income"], "Spend": ["expenses"]}}},
        )
        q = ptos.get_queries()
        assert q["dashboards"]["fin"]["groups"] == {"Revenue": ["income"], "Spend": ["expenses"]}
        assert q["dashboards"]["fin"]["metrics"] == ["income", "expenses"]

    def test_blank_and_empty_groups_stripped(self):
        ptos_service.save_queries_full(
            {"income": {"where": "type=income", "time": "this-month", "sum": True}},
            {},
            {"d": {"metrics": ["income"], "groups": {"  ": ["income"], "Empty": [], "OK": ["income"]}}},
        )
        q = ptos.get_queries()
        assert q["dashboards"]["d"]["groups"] == {"OK": ["income"]}

    def test_no_groups_writes_metrics_only(self):
        ptos_service.save_queries_full(
            {"income": {"where": "type=income", "time": "this-month", "sum": True}},
            {},
            {"legacy": {"metrics": ["income"]}},
        )
        q = ptos.get_queries()
        assert q["dashboards"]["legacy"] == {"metrics": ["income"]}

    def test_ungrouped_label_roundtrip(self):
        ptos_service.save_queries_full(
            {"income": {"where": "type=income", "time": "this-month", "sum": True}},
            {},
            {"d": {"metrics": ["income"], "groups": {"Rev": ["income"]}, "ungrouped_label": "Other"}},
        )
        q = ptos.get_queries()
        assert q["dashboards"]["d"]["ungrouped_label"] == "Other"

    def test_blank_ungrouped_label_not_written(self):
        ptos_service.save_queries_full(
            {"income": {"where": "type=income", "time": "this-month", "sum": True}},
            {},
            {"d": {"metrics": ["income"], "ungrouped_label": ""}},
        )
        q = ptos.get_queries()
        assert "ungrouped_label" not in q["dashboards"]["d"]

    def test_string_group_value_normalized(self):
        ptos_service.save_queries_full(
            {"income": {"where": "type=income", "time": "this-month", "sum": True}},
            {},
            {"d": {"metrics": ["income"], "groups": {"Rev": "income"}}},
        )
        q = ptos.get_queries()
        assert q["dashboards"]["d"]["groups"] == {"Rev": ["income"]}


class TestMergeBehavior:
    def test_boards_survive_when_raw_boards_none(self):
        ptos_service.save_queries_full(
            {"income": {"where": "type=income", "time": "this-month"}},
            {}, {},
            raw_boards={"kanban": {"columns": ["task"], "time_window": "this-month"}},
        )
        ptos_service.save_queries_full(
            {"income": {"where": "type=income", "time": "this-month"}},
            {}, {},
            raw_boards=None,
        )
        q = ptos.get_queries()
        assert "board.kanban" in q
        assert q["board.kanban"]["columns"] == ["task"]

    def test_habits_survive_when_raw_habits_none(self):
        ptos_service.save_queries_full(
            {"income": {"where": "type=income", "time": "this-month"}},
            {}, {},
            raw_habits={"exercise": {"filters": ["type=habit"], "weeks": 8}},
        )
        ptos_service.save_queries_full(
            {"income": {"where": "type=income", "time": "this-month"}},
            {}, {},
            raw_habits=None,
        )
        q = ptos.get_queries()
        assert "habit.exercise" in q
        assert q["habit.exercise"]["weeks"] == 8

    def test_calendars_survive_when_raw_calendars_none(self):
        ptos_service.save_queries_full(
            {"income": {"where": "type=income", "time": "this-month"}},
            {}, {},
            raw_calendars={"exp": {"filters": ["type=expense"]}},
        )
        ptos_service.save_queries_full(
            {"income": {"where": "type=income", "time": "this-month"}},
            {}, {},
            raw_calendars=None,
        )
        q = ptos.get_queries()
        assert "calendar.exp" in q

    def test_match_field_round_trip(self):
        ptos_service.save_queries_full(
            {"income": {"where": "type=income", "time": "this-month"}},
            {}, {},
            raw_boards={"kanban": {"columns": ["task"], "match_field": "client_code"}},
        )
        q = ptos.get_queries()
        assert q["board.kanban"]["match_field"] == "client_code"

    def test_unknown_fields_preserved_in_entry(self):
        ptos_service.save_queries_full(
            {}, {}, {},
            raw_boards={"kanban": {"columns": ["task"]}},
        )
        ptos_service.save_queries_full(
            {}, {}, {},
            raw_boards={"kanban": {"columns": ["task"]}},
        )
        q = ptos.get_queries()
        assert q["board.kanban"]["columns"] == ["task"]

    def test_delete_does_not_wipe_boards(self):
        ptos_service.save_queries_full(
            {"exp": {"where": "type=expense", "time": "this-month"}},
            {}, {},
            raw_boards={"kanban": {"columns": ["task"]}},
            raw_habits={"exercise": {"filters": ["type=habit"], "weeks": 8}},
        )
        ptos_service.save_queries_full(
            {"exp": {"where": "type=expense", "time": "this-month"}},
            {}, {},
            raw_boards=None,
            raw_habits=None,
        )
        q = ptos.get_queries()
        assert "board.kanban" in q
        assert "habit.exercise" in q


class TestDashboardCardLinks:
    """Home stat cards deep-link to /queries. Metrics need `&kind=m` and their
    raw config name (get_metric returns only the display name)."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        _write_queries(QUERIES + '\n[dashboards.metric_db]\nmetrics = ["food_ratio"]\n')

    def test_metric_item_carries_raw_name(self):
        db = ptos_service.get_dashboard("metric_db")
        item = db["items"][0]
        assert item["kind"] == "metric"
        assert item["raw_name"] == "food_ratio"

    def test_query_item_carries_raw_name(self):
        db = ptos_service.get_dashboard("legacy")
        assert [i["raw_name"] for i in db["items"]] == ["income", "expenses"]

    def test_home_metric_card_links_with_kind(self):
        from ptos_web import app
        import json, re
        client = app.test_client()
        html = client.get("/?dashboard=metric_db").data.decode()
        m = re.search(
            r'<script type="application/json" id="home-widget-specs">'
            r"(.*?)</script>", html, re.S)
        specs = json.loads(m.group(1))
        body = [s["body"] for s in specs if s["kind"] == "dashboard"][0]
        out = client.post("/api/widgets/resolve", json={
            "items": [{"id": "d", "body": body}]}).get_json()
        item = out["results"][0]["data"]["items"][0]
        assert "/queries?run=food_ratio" in item["query_url"]
        assert "kind=m" in item["query_url"]

    def test_home_query_card_links_without_kind(self):
        from ptos_web import app
        import json, re
        client = app.test_client()
        html = client.get("/?dashboard=legacy").data.decode()
        m = re.search(
            r'<script type="application/json" id="home-widget-specs">'
            r"(.*?)</script>", html, re.S)
        specs = json.loads(m.group(1))
        body = [s["body"] for s in specs if s["kind"] == "dashboard"][0]
        out = client.post("/api/widgets/resolve", json={
            "items": [{"id": "d", "body": body}]}).get_json()
        item = out["results"][0]["data"]["items"][0]
        assert "/queries?run=income" in item["query_url"]
        assert "kind=" not in item["query_url"]
