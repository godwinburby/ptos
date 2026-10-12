import os
import tomli_w
import pytest

import ptos
import ptos_service as svc
from ptos_service import PTOSError


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


def _base_queries():
    return {
        "exp": {"where": "type=expense", "time": "this-month"},
        "spend_by_cat": {"where": "type=expense", "time": "this-month",
                         "group": "category"},
        "spend_trend": {"where": "type=expense", "time": "this-month",
                        "trend": 6},
        "metrics": {"total_spend": {"sum": "exp"}},
        "dashboards": {"money": {"metrics": ["total_spend"]}},
        "threshold.spend": {"metric": "exp", "agg": "sum", "sum_field": "amount",
                            "value": 1000, "direction": "max",
                            "time": "this-month"},
    }


def _seed_two_expenses():
    d = ptos.today().strftime("%Y-%m-%d")
    _write_records([
        f"{d} type=expense amount=100 category=food",
        f"{d} type=expense amount=250 category=transport",
    ])


class TestResolveEmbedInference:
    def test_query_inferred_from_base_query(self):
        _clean()
        _set_queries(_base_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "exp"})
        assert r["kind"] == "records"
        assert r["count"] == 2
        assert r["link"] == "/queries?run=exp"
        assert r["title"] == "exp"

    def test_group_query(self):
        _clean()
        _set_queries(_base_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "spend_by_cat"})
        assert r["kind"] == "group"

    def test_trend_query(self):
        _clean()
        _set_queries(_base_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "spend_trend"})
        assert r["kind"] == "trend"

    def test_metric_inferred(self):
        _clean()
        _set_queries(_base_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "total_spend"})
        assert r["kind"] == "metric"
        assert r["link"] == "/queries?run=total_spend&kind=m"

    def test_dashboard_inferred(self):
        _clean()
        _set_queries(_base_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "money"})
        assert r["kind"] == "dashboard"
        assert r["link"] == "/queries?run=money&kind=d"

    def test_threshold_inferred(self):
        _clean()
        _set_queries(_base_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "spend"})
        assert r["kind"] == "threshold"
        assert len(r["thresholds"]) == 1
        assert r["thresholds"][0]["name"] == "spend"
        assert r["link"] == "/thresholds"


class TestResolveEmbedOptions:
    def test_explicit_view_overrides_inference(self):
        _clean()
        _set_queries(_base_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"view": "query", "name": "exp"})
        assert r["kind"] == "records"

    def test_title_override(self):
        _clean()
        _set_queries(_base_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "exp", "title": "My expenses"})
        assert r["title"] == "My expenses"

    def test_time_override(self):
        _clean()
        _set_queries(_base_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "exp", "time": "all"})
        assert r["kind"] == "records"

    def test_limit_truncates_records(self):
        _clean()
        _set_queries(_base_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "exp", "limit": 1})
        assert len(r["records"]) == 1
        assert r["count"] == 1

    def test_bad_limit_raises(self):
        _clean()
        _set_queries(_base_queries())
        _seed_two_expenses()
        with pytest.raises(PTOSError):
            svc.resolve_embed({"name": "exp", "limit": "lots"})


class TestResolveEmbedErrors:
    def test_missing_name(self):
        with pytest.raises(PTOSError):
            svc.resolve_embed({})

    def test_unknown_name(self):
        _clean()
        _set_queries(_base_queries())
        with pytest.raises(PTOSError):
            svc.resolve_embed({"name": "nope"})

    def test_unknown_view(self):
        _clean()
        _set_queries(_base_queries())
        with pytest.raises(PTOSError):
            svc.resolve_embed({"view": "karate", "name": "exp"})

    def test_non_dict_spec(self):
        with pytest.raises(PTOSError):
            svc.resolve_embed("nope")


class TestEmbedWebRoute:
    def test_ok(self):
        _clean()
        _set_queries(_base_queries())
        _seed_two_expenses()
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/embed/resolve",
                           json={"body": 'name = "exp"'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["data"]["kind"] == "records"

    def test_invalid_toml(self):
        _clean()
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/embed/resolve", json={"body": "name = "})
        data = resp.get_json()
        assert data["ok"] is False
        assert "toml" in data["error"].lower()

    def test_empty_body(self):
        _clean()
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/embed/resolve", json={"body": "  "})
        data = resp.get_json()
        assert data["ok"] is False

    def test_unknown_name(self):
        _clean()
        _set_queries(_base_queries())
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/embed/resolve",
                           json={"body": 'name = "nope"'})
        data = resp.get_json()
        assert data["ok"] is False
        assert "nope" in data["error"]


def _rich_queries():
    return {
        "exp": {"where": "type=expense", "time": "this-month"},
        "my_alias": {"alias": "exp"},
        "metrics": {"total_spend": {"sum": "exp"}},
        "dashboards": {"money": {"metrics": ["total_spend"]}},
        "threshold.spend": {"metric": "exp", "agg": "sum",
                            "sum_field": "amount", "value": 1000,
                            "direction": "max", "time": "this-month"},
        "board.demo": {"columns": ["expense"]},
        "habit.med": {"filters": ["type=habit"]},
        "calendar.personal": {"filters": ["type=expense"]},
        "due.default": {"where": "status=applied"},
    }


class TestEmbedCandidates:
    def test_groups(self):
        _clean()
        _set_queries(_rich_queries())
        c = svc.get_embed_candidates()
        assert c["queries"] == ["exp"]
        assert c["metrics"] == ["total_spend"]
        assert c["dashboards"] == ["money"]
        assert c["thresholds"] == ["spend"]

    def test_excludes_alias_and_userspace_sections(self):
        _clean()
        _set_queries(_rich_queries())
        c = svc.get_embed_candidates()
        for bad in ("my_alias", "board.demo", "habit.med",
                    "calendar.personal", "due.default", "threshold.spend"):
            assert bad not in c["queries"]

    def test_empty_queries(self):
        _clean()
        _set_queries({})
        c = svc.get_embed_candidates()
        assert c == {"queries": [], "metrics": [], "dashboards": [],
                     "thresholds": []}


class TestEmbedCandidatesRoute:
    def test_ok(self):
        _clean()
        _set_queries(_rich_queries())
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/embed/candidates")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        kinds = {g["kind"]: g["items"] for g in data["groups"]}
        assert kinds["q"] == ["exp"]
        assert kinds["m"] == ["total_spend"]
        assert kinds["d"] == ["money"]
        assert kinds["t"] == ["spend"]


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestEmbedMarkup:
    def test_editor_loads_assets_via_av(self):
        path = os.path.join(_REPO_ROOT, "web_templates",
                            "_markdown_editor.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        assert "av('/static/js/widgets.js')" in html
        assert "av('/static/js/embeds.js')" in html
        assert "av('/static/js/slash_embed.js')" in html
        assert "mountEmbeds" in html
        assert "attachSlashEmbed" in html

    def test_slash_menu_ships_format_helpers(self):
        path = os.path.join(_REPO_ROOT, "web_static", "js", "slash_embed.js")
        with open(path, encoding="utf-8") as f:
            js = f.read()
        for label in ("Heading 1", "Heading 2", "Heading 3", "Bulleted list",
                      "Numbered list", "Task list", "Quote", "Code block",
                      "Divider", "Table", "Bold", "Italic", "Strikethrough",
                      "Inline code", "Link"):
            assert label in js, label
        assert '"f"' in js
        assert 'label: "Format"' in js

    def test_queries_page_uses_shared_renderers(self):
        path = os.path.join(_REPO_ROOT, "web_templates", "queries.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        assert "av('/static/js/widgets.js')" in html
        assert "function renderResult" not in html
        assert "function renderDashboard" not in html
