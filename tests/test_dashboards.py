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


class TestHomeGroupedRender:
    @pytest.fixture(autouse=True)
    def _setup(self):
        _write_queries(QUERIES)

    def test_home_renders_group_labels(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/?dashboard=mixed")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert '<div class="stat-group-label">Spend</div>' in body

    def test_home_renders_flat_when_no_groups(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/?dashboard=legacy")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert '<div class="stat-group-label">' not in body


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

    def test_string_group_value_normalized(self):
        ptos_service.save_queries_full(
            {"income": {"where": "type=income", "time": "this-month", "sum": True}},
            {},
            {"d": {"metrics": ["income"], "groups": {"Rev": "income"}}},
        )
        q = ptos.get_queries()
        assert q["dashboards"]["d"]["groups"] == {"Rev": ["income"]}