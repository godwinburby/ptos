"""Tests for the widget catalog: gallery metadata, options, validation."""
import tomllib

import pytest
import tomli_w

import ptos
import ptos_widgets as pw
import ptos_service as svc
from ptos_service import PTOSError

BUILTIN_KINDS = (
    "dashboard", "metric", "threshold", "board", "habit", "calendar",
    "due", "project", "todo", "query", "records", "todo_summary",
    "journal", "capture", "quick_add", "quick_add_multi",
)


def _set_queries(d):
    with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
        tomli_w.dump(d, w.stream)
    ptos._invalidate_all()


def _client():
    from ptos_web import app
    return app.test_client()


class TestRegistryMetadata:
    def test_builtin_kinds_registered(self):
        kinds = {e["kind"] for e in pw.kinds()}
        assert set(BUILTIN_KINDS) <= kinds

    @pytest.mark.parametrize("kind", BUILTIN_KINDS)
    def test_kind_has_gallery_metadata(self, kind):
        e = pw.get_kind(kind)
        assert e["label"]
        assert e["description"]
        assert e["icon"]
        assert e["category"] in {c["id"] for c in pw.CATEGORIES}
        assert e["fields"]

    @pytest.mark.parametrize("kind", BUILTIN_KINDS)
    def test_fields_cover_whitelist_exactly(self, kind):
        e = pw.get_kind(kind)
        declared = {f["key"] for f in e["fields"]}
        assert declared == pw.allowed_keys(e)

    @pytest.mark.parametrize("kind", BUILTIN_KINDS)
    def test_field_types_and_labels_valid(self, kind):
        e = pw.get_kind(kind)
        for f in e["fields"]:
            assert f["type"] in pw.FIELD_TYPES
            assert f["label"]

    @pytest.mark.parametrize("kind", BUILTIN_KINDS)
    def test_named_kinds_have_saved_item_name(self, kind):
        e = pw.get_kind(kind)
        if not e["named"]:
            return
        name_field = pw.field_map(e).get("name")
        assert name_field is not None
        assert name_field["type"] == "saved_item"
        assert str(name_field.get("options_from", "")).startswith("saved.")

    @pytest.mark.parametrize("kind", BUILTIN_KINDS)
    def test_needs_name_kinds_require_name(self, kind):
        e = pw.get_kind(kind)
        if not e["needs_name"]:
            return
        assert pw.field_map(e)["name"].get("required") is True

    @pytest.mark.parametrize("kind", BUILTIN_KINDS)
    def test_interactive_default_only_for_mounted_kinds(self, kind):
        e = pw.get_kind(kind)
        if kind in ("todo", "records", "habit"):
            assert e["interactive_default"] is True
        else:
            assert e["interactive_default"] is False

    def test_categories_in_spec_order(self):
        assert [c["id"] for c in pw.CATEGORIES] == [
            "tasks", "tables", "numbers", "goals", "capture", "projects"]

    def test_every_category_used_by_some_kind(self):
        used = {e["category"] for e in pw.kinds() if e["category"]}
        assert used == {c["id"] for c in pw.CATEGORIES}

    def test_register_rejects_unknown_category(self):
        with pytest.raises(ValueError, match="unknown category"):
            pw.register("badcat", lambda *a: ({}, ""), category="nope")

    def test_register_rejects_field_whitelist_mismatch(self):
        fields = tuple(
            {"key": k, "label": k, "type": "text"}
            for k in ("view", "name", "time", "from_date", "to_date",
                      "title", "limit"))
        with pytest.raises(ValueError, match="missing fields"):
            pw.register("badfields", lambda *a: ({}, ""), keys=("x",),
                        fields=fields)

    def test_register_rejects_bad_field_type(self):
        fields = tuple(
            {"key": k, "label": k, "type": "text"}
            for k in ("view", "name", "time", "from_date", "to_date",
                      "title", "limit"))
        with pytest.raises(ValueError, match="unknown type"):
            pw.register("badtype", lambda *a: ({}, ""),
                        fields=fields + ({"key": "extra", "label": "E",
                                          "type": "nope"},))

    def test_starters_have_unique_ids_per_kind(self):
        for e in pw.kinds():
            ids = [s["id"] for s in e.get("starters") or ()]
            assert len(ids) == len(set(ids))


class TestTodoMetadataMatchesRuntime:
    """The form's select options mirror the resolver's validation sets."""

    def test_due_options_match_todo_due_values(self):
        opts = set(pw.field_map(pw.get_kind("todo"))["due"]["options"])
        assert opts == set(svc.TODO_DUE_VALUES)
        assert opts == {"overdue", "today", "tomorrow", "upcoming",
                        "someday", "none", "week"}

    def test_groupby_options_match_todo_groupbys(self):
        opts = set(pw.field_map(pw.get_kind("todo"))["groupby"]["options"])
        assert opts == set(svc._TODO_GROUPBYS)

    def test_sort_options_match_todo_sorts(self):
        opts = set(pw.field_map(pw.get_kind("todo"))["sort"]["options"])
        assert opts == {s for s in svc._TODO_SORTS if s}


class TestFieldErrors:
    def test_valid_todo_spec_has_no_errors(self):
        e = pw.get_kind("todo")
        assert pw.field_errors(e, {"view": "todo", "due": "today"}) == []

    def test_bad_due_value(self):
        e = pw.get_kind("todo")
        errs = pw.field_errors(e, {"view": "todo", "due": "bogus"})
        assert [x["field"] for x in errs] == ["due"]

    def test_limit_must_be_number(self):
        e = pw.get_kind("records")
        errs = pw.field_errors(e, {"view": "records", "limit": "5"})
        assert [x["field"] for x in errs] == ["limit"]

    def test_add_must_be_bool(self):
        e = pw.get_kind("todo")
        errs = pw.field_errors(e, {"view": "todo", "add": "yes"})
        assert [x["field"] for x in errs] == ["add"]

    def test_required_name_flag(self):
        e = pw.get_kind("dashboard")
        errs = pw.field_errors(e, {"view": "dashboard"},
                               include_required=True)
        assert [x["field"] for x in errs] == ["name"]
        assert pw.field_errors(e, {"view": "dashboard"},
                               include_required=False) == []

    def test_unknown_keys_skipped(self):
        e = pw.get_kind("metric")
        assert pw.field_errors(e, {"view": "metric", "nope": 1},
                               include_required=False) == []

    def test_chips_membership_when_static_options(self):
        e = pw.get_kind("todo")
        errs = pw.field_errors(e, {"view": "todo", "priority": "Zzz"})
        assert errs == []  # priority has options_from — membership not static


class TestWidgetOptions:
    def test_todo_projects_and_contexts(self):
        os_path = ptos.TODO_PATH
        with open(os_path, "a", encoding="utf-8") as f:
            f.write("(A) 2026-01-01 Call supplier +HearingCare @phone\n")
        assert "+HearingCare" in svc.get_widget_options("todo.projects")
        assert "@phone" in svc.get_widget_options("todo.contexts")

    def test_todo_priorities_default_when_unconfigured(self, monkeypatch):
        monkeypatch.setattr(svc, "get_config", lambda: {})
        assert svc.get_widget_options("todo.priorities") == ["A", "B", "C", "D"]

    def test_todo_priorities_from_labels(self, monkeypatch):
        monkeypatch.setattr(
            svc, "get_config",
            lambda: {"todo": {"priority_labels": {"X": "eXtra",
                                                  "Y": "Why"}}})
        assert svc.get_widget_options("todo.priorities") == ["X", "Y"]

    def test_time_source_has_standard_codes(self):
        codes = svc.get_widget_options("time")
        for c in ("td", "yd", "tw", "lw", "tm", "lm", "tq", "lq", "ty",
                  "ly", "all"):
            assert c in codes

    def test_schema_types(self):
        types = svc.get_widget_options("schema.types")
        assert "expense" in types

    def test_schema_fields_for_type(self):
        fields = svc.get_widget_options("schema.fields:expense")
        assert "amount" in fields
        assert "date" in fields

    def test_saved_metric_and_query_and_dashboard(self):
        assert "food_ratio" in svc.get_widget_options("saved.metric")
        assert "expenses_this_month" in svc.get_widget_options("saved.query")
        assert "default" in svc.get_widget_options("saved.dashboard")

    def test_saved_calendar_includes_global_view_first(self):
        cal = svc.get_widget_options("saved.calendar")
        assert cal[0] == "__all__"
        assert "personal" in cal

    def test_saved_due_default_first(self):
        assert svc.get_widget_options("saved.due")[0] == "default"

    def test_saved_todo_views_empty_on_starter_data(self):
        assert svc.get_widget_options("saved.todo") == []

    def test_unknown_source_raises(self):
        with pytest.raises(PTOSError, match="Unknown option source"):
            svc.get_widget_options("bogus")

    def test_saved_unknown_kind_raises(self):
        with pytest.raises(PTOSError, match="Unknown option source"):
            svc.get_widget_options("saved.nope")


class TestWidgetCatalog:
    def test_shape(self):
        cat = svc.get_widget_catalog()
        assert [c["id"] for c in cat["categories"]] == [
            "tasks", "tables", "numbers", "goals", "capture", "projects"]
        kinds = {k["kind"]: k for k in cat["kinds"]}
        assert set(BUILTIN_KINDS) <= set(kinds)
        for k in kinds.values():
            assert k["label"]
            assert k["description"]
            assert k["icon"]
            assert k["category"] in {c["id"] for c in cat["categories"]}
            assert isinstance(k["fields"], list) and k["fields"]
            assert isinstance(k["named"], bool)

    def test_starters_visible_with_starter_data(self):
        ids = {s["id"] for s in svc.get_widget_catalog()["starters"]}
        assert {"tasks_today", "tasks_overdue", "tasks_week", "tasks_top",
                "tasks_by_project"} <= ids
        assert {"thresholds_month", "due_default", "records_today",
                "records_month", "capture_box", "quick_add_bar",
                "quick_add_multi_bar"} <= ids

    def test_starters_parse_and_carry_kind(self):
        for s in svc.get_widget_catalog()["starters"]:
            spec = tomllib.loads(s["body"])
            assert spec.get("view")
            assert s["kind"] in {e["kind"] for e in pw.kinds()}
            assert s["category"] in {c["id"] for c in pw.CATEGORIES}

    def test_named_starters_hidden_when_item_missing(self, monkeypatch):
        empty = {k: [] for k in ("queries", "metrics", "dashboards",
                                 "thresholds", "boards", "habits",
                                 "calendars", "due", "projects", "todos")}
        monkeypatch.setattr(svc, "get_embed_candidates", lambda: empty)
        ids = {s["id"] for s in svc.get_widget_catalog()["starters"]}
        # due_default names "default" — hidden without that section
        assert "due_default" not in ids
        # inline-filter starters name no saved item — always visible
        assert "tasks_today" in ids
        assert "thresholds_month" in ids

    def test_every_starter_resolves_on_starter_data(self):
        for s in svc.get_widget_catalog()["starters"]:
            data = svc.resolve_embed(tomllib.loads(s["body"]))
            assert data, s["id"]


class TestValidateWidgetSpec:
    def test_valid_todo_spec(self):
        res = svc.validate_widget_spec({"view": "todo", "due": "today"})
        assert res == {"ok": True, "errors": []}

    def test_bad_due_value(self):
        res = svc.validate_widget_spec({"view": "todo", "due": "bogus"})
        assert res["ok"] is False
        assert res["errors"][0]["field"] == "due"

    def test_missing_name_for_dashboard(self):
        res = svc.validate_widget_spec({"view": "dashboard"})
        assert res["ok"] is False
        assert [e["field"] for e in res["errors"]] == ["name"]

    def test_unknown_view(self):
        res = svc.validate_widget_spec({"view": "nope", "name": "x"})
        assert res["ok"] is False
        assert res["errors"][0]["field"] == "view"

    def test_unknown_key(self):
        res = svc.validate_widget_spec(
            {"view": "metric", "name": "avg_spend", "nope": 1})
        assert res["ok"] is False
        assert "nope" in [e["field"] for e in res["errors"]]

    def test_infer_owns_name(self):
        res = svc.validate_widget_spec({"name": "avg_spend"})
        assert res == {"ok": True, "errors": []}

    def test_infer_ambiguous_picks_error(self):
        _set_queries({
            "metrics": {"dup": {"sum": "amount", "where": "type=expense"}},
            "dashboards": {"dup": ["dup"]},
        })
        res = svc.validate_widget_spec({"name": "dup"})
        assert res["ok"] is False
        assert res["errors"][0]["field"] == "view"

    def test_infer_unknown_name(self):
        res = svc.validate_widget_spec({"name": "no_such_item"})
        assert res["ok"] is False
        assert res["errors"][0]["field"] == "name"

    def test_limit_above_cap(self):
        res = svc.validate_widget_spec(
            {"view": "records", "limit": 9999})
        assert res["ok"] is False
        assert res["errors"][0]["field"] == "limit"

    def test_non_dict_raises(self):
        with pytest.raises(PTOSError):
            svc.validate_widget_spec("nope")


class TestCatalogEndpoints:
    def test_catalog(self):
        r = _client().get("/api/widgets/catalog")
        assert r.status_code == 200
        j = r.get_json()
        assert j["ok"] is True
        assert len(j["kinds"]) >= len(BUILTIN_KINDS)
        assert [c["id"] for c in j["categories"]] == [
            "tasks", "tables", "numbers", "goals", "capture", "projects"]
        assert j["starters"]

    def test_options_ok(self):
        r = _client().get("/api/widgets/options?source=saved.metric")
        assert r.status_code == 200
        j = r.get_json()
        assert j["ok"] is True
        assert "food_ratio" in j["values"]

    def test_options_unknown_400(self):
        r = _client().get("/api/widgets/options?source=nope")
        assert r.status_code == 400
        assert r.get_json()["ok"] is False

    def test_validate_body_valid(self):
        r = _client().post("/api/widgets/validate",
                           json={"body": 'view = "todo"\ndue = "today"\n'})
        j = r.get_json()
        assert r.status_code == 200
        assert j == {"ok": True, "errors": []}

    def test_validate_body_bad_toml(self):
        r = _client().post("/api/widgets/validate",
                           json={"body": 'view = "todo'})
        j = r.get_json()
        assert j["ok"] is True
        assert j["errors"][0]["field"] == "body"

    def test_validate_spec_dict_with_errors(self):
        r = _client().post("/api/widgets/validate",
                           json={"spec": {"view": "todo", "due": "bogus"}})
        j = r.get_json()
        assert j["ok"] is True
        assert j["errors"][0]["field"] == "due"

    def test_validate_missing_body_400(self):
        r = _client().post("/api/widgets/validate", json={})
        assert r.status_code == 400

    def test_validate_unknown_view(self):
        r = _client().post("/api/widgets/validate",
                           json={"body": 'view = "nope"\nname = "x"\n'})
        j = r.get_json()
        assert j["errors"][0]["field"] == "view"
