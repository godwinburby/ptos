"""Tests for the widget kind registry (ptos_widgets)."""
import ast
import os

import pytest
import tomli_w

import ptos
import ptos_widgets as pw
import ptos_service as svc
from ptos_service import PTOSError


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


@pytest.fixture(autouse=True)
def _isolate_registry():
    saved_w = dict(pw._WIDGETS)
    saved_a = dict(pw._VIEW_ALIASES)
    yield
    pw._WIDGETS.clear()
    pw._WIDGETS.update(saved_w)
    pw._VIEW_ALIASES.clear()
    pw._VIEW_ALIASES.update(saved_a)


def _noop_resolver(spec, name, time, from_date, to_date):
    return {"kind": "test"}, "/test"


class TestRegistryMechanics:
    def test_register_and_get_kind(self):
        pw.register("t1", _noop_resolver, infer_order=1)
        e = pw.get_kind("t1")
        assert e is not None
        assert e["kind"] == "t1"
        assert e["resolve"] is _noop_resolver

    def test_view_aliases_route_to_canonical_kind(self):
        pw.register("q2", _noop_resolver, views=("records", "group", "pivot", "trend"))
        for v in ("q2", "records", "group", "pivot", "trend", "RECORDS"):
            assert pw.get_kind(v)["kind"] == "q2"

    def test_get_kind_unknown_returns_none(self):
        assert pw.get_kind("nope") is None
        assert pw.get_kind(None) is None
        assert pw.get_kind("") is None

    def test_reregistration_overwrites(self):
        def other(spec, name, time, from_date, to_date):
            return {"kind": "other"}, "/other"
        pw.register("t3", _noop_resolver)
        pw.register("t3", other)
        assert pw.get_kind("t3")["resolve"] is other

    def test_register_rejects_non_callable(self):
        with pytest.raises(ValueError):
            pw.register("bad", 42)

    def test_register_rejects_blank_kind(self):
        with pytest.raises(ValueError):
            pw.register("  ", _noop_resolver)

    def test_kinds_sorted_by_infer_order_then_name(self):
        pw._WIDGETS.clear()
        pw._VIEW_ALIASES.clear()
        pw.register("zzz", _noop_resolver, infer_order=1)
        pw.register("aaa", _noop_resolver, infer_order=1)
        pw.register("late", _noop_resolver, infer_order=50)
        names = [e["kind"] for e in pw.kinds()]
        assert names == ["aaa", "zzz", "late"]

    def test_needs_name_default_true(self):
        pw.register("t4", _noop_resolver)
        assert pw.get_kind("t4")["needs_name"] is True
        pw.register("t5", _noop_resolver, needs_name=False)
        assert pw.get_kind("t5")["needs_name"] is False


class TestKeyWhitelists:
    def test_unknown_keys_sorted(self):
        pw.register("t6", _noop_resolver, keys=("extra",))
        e = pw.get_kind("t6")
        assert pw.unknown_keys(e, {"name": "x", "zz": 1, "aa": 2,
                                   "extra": 3}) == ["aa", "zz"]

    def test_common_keys_always_allowed(self):
        pw.register("t7", _noop_resolver)
        e = pw.get_kind("t7")
        spec = dict.fromkeys(pw.COMMON_KEYS, "v")
        assert pw.unknown_keys(e, spec) == []

    def test_kind_keys_extend_common(self):
        pw.register("t8", _noop_resolver, keys=("chart",))
        e = pw.get_kind("t8")
        assert "chart" in pw.allowed_keys(e)
        assert pw.unknown_keys(e, {"chart": "bar"}) == []

    def test_query_kind_allows_chart_metric_does_not(self):
        q = pw.get_kind("query")
        m = pw.get_kind("metric")
        assert pw.unknown_keys(q, {"chart": "bar"}) == []
        assert pw.unknown_keys(m, {"chart": "bar"}) == ["chart"]


class TestInference:
    def test_infer_kinds_order_and_ambiguity(self):
        pw._WIDGETS.clear()
        pw._VIEW_ALIASES.clear()
        pw.register("first", _noop_resolver, infer_order=10,
                    owns_name=lambda n, q: n in q)
        pw.register("second", _noop_resolver, infer_order=20,
                    owns_name=lambda n, q: n in q)
        pw.register("skipme", _noop_resolver)
        assert pw.infer_kinds("hit", {"hit": {}}) == ["first", "second"]
        assert pw.infer_kinds("miss", {}) == []

    def test_builtin_inference_order_via_registry(self):
        assert [e["kind"] for e in pw.kinds()
                if e["infer_order"] < 99] == [
            "dashboard", "metric", "threshold", "board", "habit",
            "calendar", "due", "project", "todo", "query"]


class TestBuiltinKindsRegistered:
    def test_all_builtin_views_resolve(self):
        for view in ("dashboard", "metric", "threshold", "query",
                     "records", "group", "pivot", "trend", "board",
                     "habit", "calendar", "due", "project", "todo",
                     "todo_summary", "journal", "capture", "quick_add",
                     "quick_add_multi"):
            assert pw.get_kind(view) is not None, view

    def test_builtin_needs_name(self):
        nameless = {"todo", "threshold", "records", "todo_summary",
                    "journal", "capture", "quick_add", "quick_add_multi",
                    "time_picker"}
        for e in pw.kinds():
            if e["kind"] in nameless:
                assert e["needs_name"] is False, e["kind"]
            else:
                assert e["needs_name"] is True, e["kind"]

    def test_query_carries_chart_key(self):
        assert pw.get_kind("query")["keys"] == frozenset({"chart"})

    def test_records_carries_where_and_chart_keys(self):
        assert pw.get_kind("records")["keys"] == frozenset({"where", "chart"})


class TestResolveEmbedEnforcement:
    def test_unknown_key_raises_with_allowed_list(self):
        ptos._CACHE.clear()
        _set_queries({"exp": {"where": "type=expense", "time": "all"}})
        with pytest.raises(PTOSError) as ei:
            svc.resolve_embed({"name": "exp", "bogus": 1})
        msg = str(ei.value)
        assert "does not accept" in msg
        assert "bogus" in msg
        assert "allowed" in msg

    def test_chart_accepted_on_query_kind(self):
        ptos._CACHE.clear()
        _set_queries({"exp": {"where": "type=expense", "time": "all",
                              "group": "category"}})
        r = svc.resolve_embed({"name": "exp", "chart": "bar"})
        assert r["kind"] == "group"

    def test_unknown_view_still_raises(self):
        ptos._CACHE.clear()
        _set_queries({"exp": {"where": "type=expense", "time": "all"}})
        with pytest.raises(PTOSError):
            svc.resolve_embed({"name": "exp", "view": "bogus"})


class TestImportDirection:
    def test_ptos_widgets_imports_no_product_modules(self):
        path = os.path.join(os.path.dirname(ptos.__file__), "ptos_widgets.py")
        tree = ast.parse(open(path, encoding="utf-8").read())
        banned = {"ptos", "ptos_service", "ptos_web", "ptos_todo",
                  "ptos_cli", "flask"}
        seen = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    seen.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                seen.add(node.module.split(".")[0])
        assert not (seen & banned), seen & banned


def _client():
    from ptos_web import app
    return app.test_client()


def _batch(items):
    return _client().post("/api/widgets/resolve", json={"items": items})


def _registered_widget_bodies():
    candidates = svc.get_embed_candidates()
    candidate_key = {
        "dashboard": "dashboards", "metric": "metrics",
        "board": "boards", "habit": "habits", "calendar": "calendars",
        "due": "due", "project": "projects", "query": "queries",
    }
    bodies = []
    for entry in pw.kinds():
        spec = {"view": entry["kind"]}
        key = candidate_key.get(entry["kind"])
        if entry["needs_name"]:
            names = candidates.get(key) or []
            assert names, "starter workspace has no saved " + entry["kind"]
            spec["name"] = names[0]
        bodies.append(tomli_w.dumps(spec))
    return bodies


class TestWidgetsBatchResolve:
    def test_every_registered_kind_resolves_over_both_http_endpoints(self):
        bodies = _registered_widget_bodies()
        for body in bodies:
            resp = _client().post("/api/embed/resolve", json={"body": body})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True, (body, data)
            assert data["data"]["kind"]

        resp = _batch([{"id": str(i), "body": body}
                       for i, body in enumerate(bodies)])
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert len(data["results"]) == len(bodies)
        assert all(item["ok"] for item in data["results"]), data["results"]

    def test_serialization_failure_isolated_and_generic(self, monkeypatch):
        import ptos_web

        class BadString:
            def __str__(self):
                raise TypeError("PrivateSerializationFailure")

        def resolve(spec, context=None):
            if spec.get("view") == "bad":
                return {"kind": "bad", "value": BadString()}
            return {"kind": "good", "value": [1, 2]}

        monkeypatch.setattr(svc, "resolve_embed", resolve)
        resp = _batch([
            {"id": "bad", "body": 'view = "bad"'},
            {"id": "good", "body": 'view = "good"'},
        ])
        assert resp.status_code == 200
        results = {item["id"]: item for item in resp.get_json()["results"]}
        assert results["bad"]["ok"] is False
        assert results["bad"]["error"] == "This widget could not be rendered"
        assert "TypeError" not in results["bad"]["error"]
        assert results["good"]["ok"] is True

        resp = _client().post("/api/embed/resolve",
                              json={"body": 'view = "bad"'})
        assert resp.status_code == 200
        error = resp.get_json()["error"]
        assert error == "This widget could not be rendered"
        assert "TypeError" not in error

    def test_ok_batch(self):
        ptos._CACHE.clear()
        _set_queries({"exp": {"where": "type=expense", "time": "all"}})
        d = ptos.today().strftime("%Y-%m-%d")
        _write_records([f"{d} type=expense amount=10 category=food"])
        resp = _batch([
            {"id": "a", "body": 'name = "exp"'},
            {"id": "b", "body": 'name = "exp"\nlimit = 1'},
        ])
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert len(data["results"]) == 2
        assert data["results"][0]["id"] == "a"
        assert data["results"][0]["ok"] is True
        assert data["results"][0]["data"]["kind"] == "records"
        assert data["results"][0]["data"]["count"] == 1
        assert data["results"][1]["data"]["count"] == 1

    def test_per_item_error_isolation(self):
        ptos._CACHE.clear()
        _set_queries({"exp": {"where": "type=expense", "time": "all"}})
        resp = _batch([
            {"id": "good", "body": 'name = "exp"'},
            {"id": "badtoml", "body": "name = "},
            {"id": "noname", "body": 'name = "nope"'},
            {"id": "empty", "body": "  "},
        ])
        data = resp.get_json()
        assert data["ok"] is True
        r = {x["id"]: x for x in data["results"]}
        assert r["good"]["ok"] is True
        assert r["badtoml"]["ok"] is False
        assert "toml" in r["badtoml"]["error"].lower()
        assert r["noname"]["ok"] is False
        assert "nope" in r["noname"]["error"]
        assert r["empty"]["ok"] is False
        assert r["empty"]["error"] == "Empty embed"

    def test_missing_items_is_400(self):
        resp = _client().post("/api/widgets/resolve", json={})
        assert resp.status_code == 400

    def test_plain_text_body_is_400(self):
        resp = _client().post("/api/widgets/resolve",
                              data='{"items": []}',
                              content_type="text/plain")
        assert resp.status_code == 400

    def test_default_row_cap(self):
        ptos._CACHE.clear()
        _set_queries({"exp": {"where": "type=expense", "time": "all"}})
        d = ptos.today().strftime("%Y-%m-%d")
        _write_records([f"{d} type=expense amount={i} category=food"
                        for i in range(120)])
        resp = _batch([{"id": "cap", "body": 'name = "exp"'}])
        item = resp.get_json()["results"][0]
        assert item["ok"] is True
        assert item["data"]["count"] == pw.DEFAULT_ROW_LIMIT
        assert len(item["data"]["records"]) == pw.DEFAULT_ROW_LIMIT

    def test_limit_honored(self):
        ptos._CACHE.clear()
        _set_queries({"exp": {"where": "type=expense", "time": "all"}})
        d = ptos.today().strftime("%Y-%m-%d")
        _write_records([f"{d} type=expense amount={i} category=food"
                        for i in range(5)])
        resp = _batch([{"id": "x", "body": 'name = "exp"\nlimit = 2'}])
        item = resp.get_json()["results"][0]
        assert item["data"]["count"] == 2

    def test_limit_above_max_is_error(self):
        ptos._CACHE.clear()
        _set_queries({"exp": {"where": "type=expense", "time": "all"}})
        resp = _batch([{"id": "x", "body": 'name = "exp"\nlimit = 501'}])
        item = resp.get_json()["results"][0]
        assert item["ok"] is False
        assert str(pw.MAX_ROW_LIMIT) in item["error"]

    def test_limit_at_max_allowed(self):
        ptos._CACHE.clear()
        _set_queries({"exp": {"where": "type=expense", "time": "all"}})
        d = ptos.today().strftime("%Y-%m-%d")
        _write_records([f"{d} type=expense amount=1 category=food"])
        resp = _batch([{"id": "x",
                        "body": f'name = "exp"\nlimit = {pw.MAX_ROW_LIMIT}'}])
        item = resp.get_json()["results"][0]
        assert item["ok"] is True

    def test_too_many_items_is_400(self):
        items = [{"id": str(i), "body": 'name = "exp"'}
                 for i in range(201)]
        resp = _batch(items)
        assert resp.status_code == 400


class TestDevWidgetsPage:
    def _client(self):
        from ptos_web import app
        return app.test_client()

    def _repo(self, *parts):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(root, *parts)

    def test_hidden_without_asset_dev(self, monkeypatch):
        import ptos_web
        monkeypatch.setattr(ptos_web, "_ASSET_DEV", False)
        assert self._client().get("/dev/widgets").status_code == 404

    def test_renders_static_and_interactive_pairs(self, monkeypatch):
        import ptos_web
        monkeypatch.setattr(ptos_web, "_ASSET_DEV", True)
        resp = self._client().get("/dev/widgets")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert html.count("data-ptos-widget ") == 10
        assert html.count('data-interactive="1"') == 5
        assert html.count('data-widget-host="dev"') == 10
        assert html.count("data-body=") == 10
        import html as html_lib
        dec = html_lib.unescape(html)
        assert 'view = "todo"' in dec
        assert "add = true" in dec
        assert 'name = "food_spend"' in dec
        assert "mountAll(document" in html

    def test_loads_widget_scripts_versioned(self, monkeypatch):
        import ptos_web
        monkeypatch.setattr(ptos_web, "_ASSET_DEV", True)
        html = self._client().get("/dev/widgets").get_data(as_text=True)
        for asset in ("/static/js/widgets.js?v=",
                      "/static/js/record_table.js?v=",
                      "/static/js/embeds.js?v=",
                      "/static/js/widget_host.js?v="):
            assert asset in html, asset

    def test_shell_never_links_dev_page(self):
        with open(self._repo("web_templates", "base.html"),
                  encoding="utf-8") as f:
            assert "/dev/widgets" not in f.read()
