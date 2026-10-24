"""Tests for saved todo views (["todo.NAME"] sections) and the todo widget.

Covers the _w_todo resolver (saved views, nameless default view,
inline overrides, error paths), the query_todos groupby/sort/limit/
include_done extensions, group_todos extraction, ptos.lint_todo_views,
the candidates/slash menu surfacing, save_queries_full preservation,
and the batch endpoint's todo exemption + threshold query_url
decoration (Stage 2, spec §4.1/§5).
"""
import datetime as dt
import os
import tomli_w

import pytest

import ptos
import ptos_service as svc
import ptos_widgets as pw
from ptos_service import PTOSError


def _set_queries(d):
    with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
        tomli_w.dump(d, w.stream)
    ptos._invalidate_all()


def _clean():
    ptos._CACHE.clear()


def _seed_todos(lines, done_lines=()):
    os.makedirs(os.path.dirname(ptos.TODO_PATH) or ".", exist_ok=True)
    with open(ptos.TODO_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.makedirs(os.path.dirname(ptos.DONE_PATH) or ".", exist_ok=True)
    with open(ptos.DONE_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(done_lines) + "\n")


def _today():
    return ptos.today().isoformat()


def _flat_descriptions(result):
    return [t["description"] for g in result["groups"] for t in g["todos"]]


class TestTodoViewResolution:
    def test_nameless_view_is_default_open_list(self):
        _clean()
        _set_queries({})
        _seed_todos([f"Call supplier +work due:{_today()}",
                     "Buy milk +home"])
        r = svc.resolve_embed({"view": "todo"})
        assert r["kind"] == "todo"
        assert r["link"] == "/todo"
        assert r["total_open"] == 2
        assert set(_flat_descriptions(r)) == {"Call supplier", "Buy milk"}

    def test_nameless_without_view_missing_name(self):
        _clean()
        _set_queries({})
        with pytest.raises(PTOSError) as ei:
            svc.resolve_embed({})
        assert "missing 'name'" in str(ei.value)

    def test_saved_view_filters_groups_and_titles(self):
        _clean()
        _set_queries({"todo.work_week": {
            "project": "+work", "groupby": "project",
            "title": "Work week", "limit": 5}})
        _seed_todos([f"Call supplier +work due:{_today()}",
                     "Fix sink +home"])
        r = svc.resolve_embed({"view": "todo", "name": "work_week"})
        assert r["title"] == "Work week"
        assert len(r["groups"]) == 1
        [grp] = r["groups"]
        assert grp["key"] == "proj-work"
        assert grp["label"] == "+work"
        assert [t["description"] for t in grp["todos"]] == ["Call supplier"]
        assert "project=%2Bwork" in r["link"]
        assert "groupby=project" in r["link"]

    def test_saved_view_title_overrides_kind_capitalization(self):
        _clean()
        _set_queries({"todo.q1": {"title": "Deep Work"}})
        _seed_todos(["Write spec +deep"])
        r = svc.resolve_embed({"view": "todo", "name": "q1"})
        assert r["title"] == "Deep Work"

    def test_unknown_saved_view_name(self):
        _clean()
        _set_queries({})
        with pytest.raises(PTOSError) as ei:
            svc.resolve_embed({"view": "todo", "name": "nope"})
        assert "Todo view 'nope' not found" in str(ei.value)

    def test_inline_overrides_saved_view(self):
        _clean()
        _set_queries({"todo.views": {"groupby": "project"}})
        _seed_todos(["(A) First +work", "Second +work", "Third +home"])
        r = svc.resolve_embed({"view": "todo", "name": "views",
                               "groupby": "priority"})
        keys = [g["key"] for g in r["groups"]]
        assert keys and all(k.startswith("pri-") for k in keys)

    def test_unknown_inline_key_rejected(self):
        _clean()
        _set_queries({})
        with pytest.raises(PTOSError) as ei:
            svc.resolve_embed({"view": "todo", "bogus": 1})
        msg = str(ei.value)
        assert "does not accept" in msg and "bogus" in msg

    def test_unknown_saved_key_rejected(self):
        _clean()
        _set_queries({"todo.bad": {"bogus": 1}})
        _seed_todos([])
        with pytest.raises(PTOSError) as ei:
            svc.resolve_embed({"view": "todo", "name": "bad"})
        assert "unsupported keys" in str(ei.value)
        assert "bogus" in str(ei.value)

    def test_time_keys_rejected(self):
        _clean()
        _set_queries({})
        with pytest.raises(PTOSError) as ei:
            svc.resolve_embed({"view": "todo", "time": "tm"})
        assert "do not support time" in str(ei.value)

    def test_name_infers_todo_kind(self):
        _clean()
        _set_queries({"todo.work_week": {"project": "+work"}})
        _seed_todos([f"Call +work due:{_today()}", "Home +home"])
        r = svc.resolve_embed({"name": "work_week"})
        assert r["kind"] == "todo"
        assert r["total_open"] == 1

    def test_ambiguous_name_between_todo_and_metric(self):
        _clean()
        _set_queries({"todo.balance": {"project": "+work"},
                      "metrics": {"balance": {"sum": "exp"}}})
        _seed_todos([])
        with pytest.raises(PTOSError) as ei:
            svc.resolve_embed({"name": "balance"})
        msg = str(ei.value)
        assert "multiple sections" in msg
        assert "balance" in msg
        assert 'view = "' in msg

    def test_explicit_view_wins_over_ambiguity(self):
        _clean()
        _set_queries({"todo.balance": {"project": "+work"},
                      "metrics": {"balance": {"sum": "exp"}}})
        _seed_todos([f"Fund +work due:{_today()}"])
        r = svc.resolve_embed({"name": "balance", "view": "todo"})
        assert r["kind"] == "todo"
        assert r["total_open"] == 1


class TestQueryTodosExtensions:
    def test_due_week_includes_overdue_and_next_week(self):
        _clean()
        today = ptos.today()
        _seed_todos([
            f"Overdue +p due:{(today - dt.timedelta(days=3)).isoformat()}",
            f"Later +p due:{(today + dt.timedelta(days=5)).isoformat()}",
            f"Too far +p due:{(today + dt.timedelta(days=20)).isoformat()}",
            "No due date +p",
        ])
        b = svc.query_todos(project="+p", due="week")
        descs = [t.description for k in ("overdue", "today", "tomorrow",
                                         "upcoming", "someday")
                 for t in b[k]]
        assert "Overdue" in descs
        assert "Later" in descs
        assert "Too far" not in descs
        assert "No due date" not in descs

    def test_include_done_bucket_not_counted_in_total(self):
        _clean()
        _seed_todos([f"Open +p due:{_today()}"],
                    done_lines=[f"x {_today()} 2026-01-01 Finished +p"])
        b = svc.query_todos(project="+p", include_done=True)
        assert b["total_open"] == 1
        assert [t.description for t in b["done"]] == ["Finished"]

    def test_done_bucket_respects_filters(self):
        _clean()
        _seed_todos(["Open +p"],
                    done_lines=[f"x {_today()} 2026-01-01 Kept +p",
                                f"x {_today()} 2026-01-01 Other +q"])
        b = svc.query_todos(project="+p", include_done=True)
        assert [t.description for t in b["done"]] == ["Kept"]

    def test_groupby_none_yields_single_flat_group(self):
        _clean()
        _seed_todos(["First +p", "Second +q"])
        b = svc.query_todos(groupby="none")
        assert [g[0] for g in b["grouped"]] == ["all"]
        assert len(b["grouped"][0][3]) == 2

    def test_sort_most_orders_groups_by_size(self):
        _clean()
        _seed_todos(["A +big", "B +big", "C +big", "D +small"])
        b = svc.query_todos(groupby="project", sort="most")
        assert [g[0] for g in b["grouped"]][:2] == ["proj-big", "proj-small"]
        b2 = svc.query_todos(groupby="project", sort="fewest")
        assert b2["grouped"][0][0] == "proj-small"

    def test_limit_truncates_grouped_todos(self):
        _clean()
        _seed_todos(["A +p", "B +p", "C +p"])
        b = svc.query_todos(groupby="project", limit=2)
        assert sum(len(g[3]) for g in b["grouped"]) == 2
        assert b["total_open"] == 3

    def test_group_todos_none_mode_present(self):
        _clean()
        _seed_todos(["Solo +p"])
        b = svc.query_todos(groupby="none")
        grouped = svc.group_todos(b, "none", {})
        assert grouped[0][1] == ""
        assert [t.description for t in grouped[0][3]] == ["Solo"]


class TestTodoWidgetPayload:
    def test_json_carries_raw_line_for_expect(self):
        _clean()
        _set_queries({})
        _seed_todos(["(A) Call supplier +work"])
        r = svc.resolve_embed({"view": "todo"})
        t = r["groups"][0]["todos"][0]
        assert t["raw_line"] == "(A) Call supplier +work"
        assert t["priority"] == "A"
        assert t["projects"] == ["+work"]

    def test_limit_truncates_open_groups_keeps_done_whole(self):
        _clean()
        _set_queries({})
        _seed_todos(["A +p", "B +p"],
                    done_lines=["x 2026-01-02 2026-01-01 D1 +p",
                                "x 2026-01-02 2026-01-01 D2 +p"])
        r = svc.resolve_embed({"view": "todo", "limit": 1,
                               "groupby": "project",
                               "include_done": True})
        groups = {g["key"]: g for g in r["groups"]}
        assert len(groups["proj-p"]["todos"]) == 1
        assert len(groups["done"]["todos"]) == 2
        assert r["total_open"] == 2

    def test_done_group_last_even_when_sort_applies(self):
        _clean()
        _seed_todos(["A +big", "B +big", "C +small"],
                    done_lines=["x 2026-01-02 2026-01-01 Done +p"])
        r = svc.resolve_embed({"view": "todo", "groupby": "project",
                               "sort": "most", "include_done": True})
        assert r["groups"][-1]["key"] == "done"

    def test_hide_routines_inline_flag(self):
        _clean()
        _seed_todos(["Daily stretch +routine", "Real task +p"])
        shown = svc.resolve_embed({"view": "todo"})
        assert "Daily stretch" in _flat_descriptions(shown)
        hidden = svc.resolve_embed({"view": "todo", "hide_routines": True})
        assert "Daily stretch" not in _flat_descriptions(hidden)

    def test_bad_groupby_sort_limit_add_rejected(self):
        _clean()
        _set_queries({})
        _seed_todos([])
        with pytest.raises(PTOSError) as ei:
            svc.resolve_embed({"view": "todo", "groupby": "banana"})
        assert "groupby" in str(ei.value)
        with pytest.raises(PTOSError) as ei:
            svc.resolve_embed({"view": "todo", "sort": "banana"})
        assert "sort" in str(ei.value)
        with pytest.raises(PTOSError) as ei:
            svc.resolve_embed({"view": "todo", "limit": "lots"})
        assert "limit" in str(ei.value)
        with pytest.raises(PTOSError) as ei:
            svc.resolve_embed({"view": "todo", "add": "yes"})
        assert "add" in str(ei.value)

    def test_widget_matches_page_query(self):
        _clean()
        _seed_todos([f"Call +work due:{_today()}",
                     "(A) Ship +work", "Home +home"])
        page = svc.query_todos(project="+work")
        page_lines = [t.raw_line for k in ("overdue", "today", "tomorrow",
                                           "upcoming", "someday")
                      for t in page[k]]
        r = svc.resolve_embed({"view": "todo", "project": "+work"})
        widget_lines = [t["raw_line"] for g in r["groups"]
                        for t in g["todos"] if t["description"] != "Done"]
        assert sorted(widget_lines) == sorted(page_lines)
        assert r["total_open"] == page["total_open"]


class TestTodoViewLint:
    def test_clean_views_no_warnings(self):
        assert ptos.lint_todo_views({
            "todo.work_week": {"project": "+work", "groupby": "priority",
                               "sort": "most", "limit": 10, "add": True,
                               "title": "Work", "hide_routines": True}}) == []
        assert ptos.lint_todo_views({}) == []
        assert ptos.lint_todo_views(None) == []

    def test_bad_section_flags_every_problem(self):
        warns = ptos.lint_todo_views({"todo.bad": {
            "bogus": 1, "groupby": "banana", "sort": "sideways",
            "limit": "lots", "add": "yes"}})
        joined = "\n".join(warns)
        assert "unsupported key(s) bogus" in joined
        assert "unknown groupby 'banana'" in joined
        assert "unknown sort 'sideways'" in joined
        assert "'limit' must be a whole number" in joined
        assert "'add' must be true or false" in joined

    def test_empty_section_name_flagged(self):
        warns = ptos.lint_todo_views({"todo.": {"project": "+x"}})
        assert any("empty name" in w for w in warns)

    def test_non_dict_sections_ignored(self):
        assert ptos.lint_todo_views({"todo.x": "nope"}) == []
        assert ptos.lint_todo_views({"board.x": {"bogus": 1}}) == []

    def test_doctor_reports_broken_view(self):
        _clean()
        _set_queries({"todo.bad": {"bogus": 1}})
        errors, warnings, messages, fixes = ptos.doctor_check()
        assert any("todo view 'bad'" in w for w in warnings)


class TestTodoViewCandidatesAndMenus:
    def test_candidates_list_saved_views_sorted(self):
        _clean()
        _set_queries({"todo.zeta": {"project": "+z"},
                      "todo.alpha": {"project": "+a"},
                      "todo.notdict": "x",
                      "exp": {"where": "type=expense", "time": "all"}})
        c = svc.get_embed_candidates()
        assert c["todos"] == ["alpha", "zeta"]
        assert "todo.zeta" not in c["queries"]

    def test_candidates_route_includes_todo_group(self):
        _clean()
        _set_queries({"todo.work_week": {"project": "+work"}})
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/embed/candidates")
        data = resp.get_json()
        assert data["ok"]
        grp = [g for g in data["groups"] if g["kind"] == "v"]
        assert len(grp) == 1
        assert grp[0]["label"] == "Todo views"
        assert grp[0]["items"] == ["work_week"]

    def test_get_todo_view_names(self):
        _clean()
        _set_queries({"todo.b": {}, "todo.a": {}, "board.x": {}})
        assert svc.get_todo_view_names() == ["a", "b"]


class TestTodoViewSavePreservation:
    def test_save_queries_full_preserves_todo_sections(self):
        _clean()
        _set_queries({"todo.work_week": {"project": "+work",
                                         "groupby": "project"},
                      "exp": {"where": "type=expense", "time": "all"}})
        svc.save_queries_full({}, {}, {})
        q = ptos.get_queries()
        assert q["todo.work_week"] == {"project": "+work",
                                       "groupby": "project"}

    def test_todo_key_skipped_in_base_query_loop(self):
        _clean()
        _set_queries({"todo.work_week": {"project": "+work"}})
        svc.save_queries_full({
            "exp": {"where": "type=expense", "time": "all"},
            "todo.work_week": {"project": "+work"},
        }, {}, {})
        q = ptos.get_queries()
        assert q["todo.work_week"] == {"project": "+work"}
        assert "exp" in q


class TestBatchEndpoint:
    @staticmethod
    def _client():
        from ptos_web import app
        return app.test_client()

    def test_todo_keeps_default_limit_of_twenty(self):
        _clean()
        _set_queries({})
        lines = [f"Task {i:03d} +p due:{_today()}" for i in range(150)]
        _seed_todos(lines)
        resp = self._client().post("/api/widgets/resolve",
                                   json={"items": [{"id": 1,
                                                    "body": 'view = "todo"'}]})
        data = resp.get_json()
        assert data["ok"]
        [res] = data["results"]
        assert res["ok"], res.get("error")
        shown = sum(len(g["todos"]) for g in res["data"]["groups"])
        assert shown == 20
        assert res["data"]["total_open"] == 150

    def test_records_kind_still_gets_batch_row_cap(self):
        _clean()
        _set_queries({"exp": {"where": "type=expense", "time": "all"}})
        year = ptos.today().year
        os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
        d = _today()
        with open(os.path.join(ptos.RECORDS_DIR, f"{year}.log"), "w",
                  encoding="utf-8") as f:
            for i in range(150):
                f.write(f"{d} type=expense amount={i} tag=t{i}\n")
        ptos._invalidate_all()
        resp = self._client().post("/api/widgets/resolve",
                                   json={"items": [{"id": 1,
                                                    "body": 'name = "exp"'}]})
        data = resp.get_json()
        [res] = data["results"]
        assert res["ok"], res.get("error")
        assert res["data"]["count"] == 100

    def test_threshold_rows_carry_query_url(self):
        _clean()
        _set_queries({
            "exp": {"where": "type=expense", "time": "all"},
            "threshold.spend": {"metric": "exp", "agg": "sum",
                                "sum_field": "amount", "value": 1000,
                                "direction": "max", "time": "this-month"}})
        resp = self._client().post(
            "/api/widgets/resolve",
            json={"items": [{"id": 1,
                             "body": 'name = "spend"\nview = "threshold"'}]})
        data = resp.get_json()
        [res] = data["results"]
        assert res["ok"], res.get("error")
        rows = res["data"]["thresholds"]
        assert rows and rows[0]["query_url"].startswith("/queries?run=")
        assert "kind=" in rows[0]["query_url"]

    def test_legacy_embed_resolve_threshold_is_decorated_for_live_preview(self):
        _clean()
        _set_queries({
            "exp": {"where": "type=expense", "time": "all"},
            "threshold.spend": {"metric": "exp", "agg": "sum",
                                "sum_field": "amount", "value": 1000,
                                "direction": "max", "time": "this-month"}})
        resp = self._client().post("/api/embed/resolve",
                                   json={"body": 'name = "spend"\n'
                                                 'view = "threshold"'})
        data = resp.get_json()
        assert data["ok"]
        assert data["data"]["thresholds"][0]["query_url"].startswith(
            "/queries?run=")

    def test_bad_todo_view_fails_item_not_batch(self):
        _clean()
        _set_queries({})
        resp = self._client().post(
            "/api/widgets/resolve",
            json={"items": [{"id": 1, "body": 'view = "todo"\nname = "nope"'},
                            {"id": 2, "body": 'view = "todo"'}]})
        data = resp.get_json()
        assert data["ok"]
        assert data["results"][0]["ok"] is False
        assert "not found" in data["results"][0]["error"]
        assert data["results"][1]["ok"] is True


class TestStaticPins:
    def _repo(self, *parts):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(root, *parts)

    def test_query_builder_boots_skip_todo_sections(self):
        with open(self._repo("web_templates", "query_builder.html"),
                  encoding="utf-8") as f:
            src = f.read()
        assert 'k.startsWith("todo.")' in src

    def test_qb_banner_does_not_claim_todo_sections(self):
        with open(self._repo("web_templates", "query_builder.html"),
                  encoding="utf-8") as f:
            src = f.read()
        i = src.find("var handledPrefixes")
        assert i != -1
        line = src[i:src.find("\n", i)]
        assert "todo." not in line

    def test_slash_menu_maps_todo_group(self):
        with open(self._repo("web_static", "js", "slash_embed.js"),
                  encoding="utf-8") as f:
            src = f.read()
        assert 'v: "todo"' in src

    def test_starter_ships_commented_todo_example(self):
        with open(self._repo("starters", "starter_queries.toml"),
                  encoding="utf-8") as f:
            src = f.read()
        assert '["todo.NAME"]' in src

    def test_cli_lint_reaches_todo_views(self):
        with open(self._repo("ptos_cli.py"), encoding="utf-8") as f:
            src = f.read()
        assert "lint_todo_views" in src

    def test_registry_has_single_todo_registration(self):
        with open(self._repo("ptos_service.py"), encoding="utf-8") as f:
            src = f.read()
        assert src.count('reg("todo"') == 1
        assert 'reg("todo", _w_todo' in src


class TestWidgetHostClient:
    """Stage 2 Step D — widget_host.js + renderer client-layer pins."""

    def _js(self, name):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "web_static", "js", name),
                  encoding="utf-8") as f:
            return f.read()

    def test_exports_widget_registry(self):
        src = self._js("widget_host.js")
        assert "window.PtosWidgets" in src
        for member in ("register:", "mount:", "mountAll:"):
            assert member in src

    def test_no_global_element_ids(self):
        src = self._js("widget_host.js")
        assert "getElementById" not in src
        assert 'id="' not in src
        assert ".id =" not in src

    def test_fetches_through_widget_batch_endpoint(self):
        src = self._js("widget_host.js")
        assert '_post("/api/widgets/resolve"' in src
        assert '_post("/api/embed/resolve"' not in src
        assert 'fetch("/api/embed' not in src

    def test_registers_interactive_kinds(self):
        src = self._js("widget_host.js")
        for kind in ('register("todo"', 'register("records"', 'register("habit"'):
            assert kind in src

    def test_writes_todo_and_habit_endpoints(self):
        src = self._js("widget_host.js")
        for ep in ("/todo/complete", "/todo/undo", "/todo/add",
                   "/api/habit/toggle"):
            assert ep in src

    def test_single_stamped_style_block(self):
        src = self._js("widget_host.js")
        assert 'style[data-ph-style]' in src
        assert 'getElementById' not in src

    def test_todo_rows_render_from_widgets_js(self):
        src = self._js("widgets.js")
        assert "function renderTodo" in src
        assert 'case "todo"' in src
        assert "return renderTodo(d)" in src
        assert "data-raw" in src

    def test_threshold_rows_are_links(self):
        src = self._js("widgets.js")
        assert "thr-link" in src

    def test_habit_cells_carry_toggle_attributes(self):
        src = self._js("widgets.js")
        for attr in ("data-date", 'data-stat="streak"', 'data-stat="days"',
                     "data-toggleable"):
            assert attr in src

    def test_due_rows_link_to_record_editor(self):
        src = self._js("widgets.js")
        assert "/edit?filepath=" in src

    def test_record_table_takes_container_option_and_destroy(self):
        src = self._js("record_table.js")
        assert "opts.container || ge(cid)" in src
        assert "self.destroy" in src
        host = self._js("widget_host.js")
        assert "container: wrap" in host
        assert "rt.destroy()" in host


class TestQueryTodoFilterValidation:
    @staticmethod
    def _descs(b):
        return [t.description for k in ("overdue", "today", "tomorrow",
                                        "upcoming", "someday") for t in b[k]]

    @staticmethod
    def _client():
        from ptos_web import app
        return app.test_client()

    def test_bare_project_matches_prefixed(self):
        _clean()
        _seed_todos(["Alpha +work", "Beta +play"])
        assert self._descs(svc.query_todos(project="work")) == ["Alpha"]
        assert self._descs(svc.query_todos(project="+work")) == ["Alpha"]

    def test_project_prefix_exclusion_still_works(self):
        _clean()
        _seed_todos(["Alpha +work", "Beta +play"])
        assert self._descs(svc.query_todos(project="-work")) == ["Beta"]

    def test_project_and_context_case_insensitive(self):
        _clean()
        _seed_todos(["Alpha +Work", "Gamma @Office"])
        assert self._descs(svc.query_todos(project="work")) == ["Alpha"]
        assert self._descs(svc.query_todos(project="WORK")) == ["Alpha"]
        assert self._descs(svc.query_todos(context="office")) == ["Gamma"]
        assert self._descs(svc.query_todos(context="@Office")) == ["Gamma"]

    def test_hyphenated_names_match_exactly(self):
        _clean()
        _seed_todos(["Alpha +big-project", "Beta +big"])
        assert self._descs(svc.query_todos(project="big-project")) == ["Alpha"]
        assert self._descs(svc.query_todos(project="big")) == ["Beta"]

    def test_bare_context_matches_at_prefixed(self):
        _clean()
        _seed_todos(["Call boss @office", "Buy milk @shop"])
        assert self._descs(svc.query_todos(context="office")) == ["Call boss"]
        assert self._descs(svc.query_todos(context="@office")) == ["Call boss"]

    def test_invalid_due_raises_field_error(self):
        _clean()
        _seed_todos(["Alpha +p"])
        with pytest.raises(PTOSError, match="due"):
            svc.query_todos(due="nextcentury")

    def test_invalid_priority_raises_field_error(self):
        _clean()
        _seed_todos(["Alpha +p"])
        with pytest.raises(PTOSError, match="priority"):
            svc.query_todos(priority="zz")
        with pytest.raises(PTOSError, match="priority"):
            svc.query_todos(priority="AB")
        with pytest.raises(PTOSError, match="priority"):
            svc.query_todos(priority="1")

    def test_due_is_case_insensitive_and_empty_means_unfiltered(self):
        _clean()
        _seed_todos([f"Today +p due:{_today()}", "Later +q"])
        assert self._descs(svc.query_todos(due="TODAY")) == ["Today"]
        assert self._descs(svc.query_todos(due="today")) == ["Today"]
        got = self._descs(svc.query_todos(due="", priority=""))
        assert sorted(got) == ["Later", "Today"]

    def test_priority_list_matches_any_letter(self):
        _clean()
        _seed_todos(["(A) High +p", "(B) Med +p", "(C) Low +p"])
        got = self._descs(svc.query_todos(project="+p",
                                          priority=["A", "b"]))
        assert sorted(got) == ["High", "Med"]

    def test_page_invalid_due_shows_error_banner(self):
        _clean()
        _seed_todos(["Alpha +p"])
        resp = self._client().get("/todo?due=bogus")
        assert resp.status_code == 200
        assert b"must be one of" in resp.data

    def test_batch_todo_widget_invalid_due_returns_item_error(self):
        _clean()
        resp = self._client().post(
            "/api/widgets/resolve",
            json={"items": [
                {"id": 1, "body": 'view = "todo"\ndue = "bogus"'},
                {"id": 2, "body": 'view = "todo"'}]})
        data = resp.get_json()
        assert data["ok"]
        res1, res2 = data["results"]
        assert res1["ok"] is False
        assert "due" in res1.get("error", "")
        assert res2["ok"], res2.get("error")
