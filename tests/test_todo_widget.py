"""
tests/test_todo_widget.py  —  Tests for saved todo views (["todo.NAME"] sections) and the todo widget.

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


def _yesterday():
    return (ptos.today() - dt.timedelta(days=1)).isoformat()


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

    def test_todo_page_loads_saved_view_for_editing(self):
        import json
        import re
        _clean()
        _set_queries({"todo.work_week": {
            "project": "+work", "groupby": "project", "sort": "most",
            "title": "Work week", "hide_routines": True,
        }})
        _seed_todos([f"Call supplier +work due:{_today()}", "Fix sink +home"])
        from ptos_web import app
        response = app.test_client().get("/todo?view=work_week")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert '"selected_view": "work_week"' in html
        spec_match = re.search(
            r'<script type="application/json" id="page-spec">(.*?)</script>',
            html, re.S)
        data_match = re.search(
            r'<script type="application/json" id="page-data">(.*?)</script>',
            html, re.S)
        spec = json.loads(spec_match.group(1))
        data = json.loads(data_match.group(1))
        assert 'name = "work_week"' in spec["body"]
        descriptions = [todo["description"] for group in data["groups"]
                        for todo in group["todos"]]
        assert descriptions == ["Call supplier"]

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

    def test_empty_saved_view_name_uses_inline_filters(self):
        _clean()
        _set_queries({"todo.": {"project": "+x"}})
        # Empty name should be treated as "no saved view", using inline filters
        r = svc.resolve_embed({"view": "todo", "name": "", "project": "+x"})
        # Should use inline filter +x, not the saved view "todo."
        assert r["filters"]["project"] == "+x"
        # The saved view "todo." should not be used
        assert "project" not in r.get("saved_view", {})

    def test_non_dict_saved_view_rejected(self):
        _clean()
        _set_queries({"todo.x": "nope"})
        with pytest.raises(PTOSError) as ei:
            svc.resolve_embed({"view": "todo", "name": "x"})
        assert "Todo view settings must be an object" in str(ei.value)


class TestQueryTodosExtensions:
    @staticmethod
    def _descs(b):
        return [t.description for k in ("overdue", "today", "tomorrow",
                                        "upcoming", "someday") for t in b[k]]

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
                                         "upcoming", "someday") for t in b[k]]
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

    def test_bare_project_matches_prefixed(self):
        _clean()
        _seed_todos(["Alpha +work", "Beta +play"])
        assert self._descs(svc.query_todos(project="work")) == ["Alpha"]
        assert self._descs(svc.query_todos(project="+work")) == ["Alpha"]

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
        from ptos_web import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.get("/todo?due=bogus")
            assert resp.status_code == 200
            assert b"must be one of" in resp.data

    def test_batch_todo_widget_invalid_due_returns_item_error(self):
        _clean()
        from ptos_web import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.post(
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


class TestTodoArea:
    @staticmethod
    def _descs(b):
        return [t.description for k in ("overdue", "today", "tomorrow",
                                        "upcoming", "someday") for t in b[k]]

    def test_query_todos_filters_by_area(self):
        _clean()
        _seed_todos(["Water plants area:home", "Ship invoice area:work",
                     "No area task"])
        # Area token preserved in description
        assert self._descs(svc.query_todos(area="work")) == ["Ship invoice area:work"]
        assert svc.query_todos(area="work")["total_open"] == 1

    def test_query_todos_area_empty_or_none_is_unfiltered(self):
        _clean()
        _seed_todos(["Water plants area:home", "Ship invoice area:work"])
        # Area token preserved in description
        assert sorted(self._descs(svc.query_todos(area=None))) == [
            "Ship invoice area:work", "Water plants area:home"]
        assert sorted(self._descs(svc.query_todos(area=""))) == [
            "Ship invoice area:work", "Water plants area:home"]

    def test_query_todos_rejects_bad_area_slug(self):
        _clean()
        _seed_todos(["Water plants area:home"])
        with pytest.raises(PTOSError, match="area"):
            svc.query_todos(area="Work Area")
        with pytest.raises(PTOSError, match="area"):
            svc.query_todos(area="Work")

    def test_saved_view_area_key_filters(self):
        _clean()
        _set_queries({"todo.work": {"area": "work"}})
        _seed_todos(["Water plants area:home", "Ship invoice area:work"])
        r = svc.resolve_embed({"view": "todo", "name": "work"})
        # Area token preserved in description
        assert _flat_descriptions(r) == ["Ship invoice area:work"]
        assert r["filters"] == {"area": "work"}
        assert "area=work" in r["link"]

    def test_inline_area_overrides_saved_view(self):
        _clean()
        _set_queries({"todo.home_stuff": {"area": "home"}})
        _seed_todos(["Water plants area:home", "Ship invoice area:work"])
        r = svc.resolve_embed({"view": "todo", "name": "home_stuff",
                               "area": "work"})
        # Area token preserved in description
        assert _flat_descriptions(r) == ["Ship invoice area:work"]

    def test_area_with_no_matches_is_empty_not_error(self):
        _clean()
        _seed_todos(["Water plants area:home"])
        r = svc.resolve_embed({"view": "todo", "area": "work"})
        assert r["groups"] == []
        assert r["total_open"] == 0

    def test_todo_summary_area_key(self):
        _clean()
        _seed_todos([f"Late work area:work due:{_yesterday()}",
                     f"Late home area:home due:{_yesterday()}",
                     "Open work area:work"])
        r = svc.resolve_embed({"view": "todo_summary", "area": "work"})
        assert r["kind"] == "todo_summary"
        assert r["overdue"] == 1
        assert r["due_today"] == 0
        assert "area=work" in r["link"]

    def test_todo_summary_rejects_bad_area(self):
        _clean()
        _seed_todos(["Late work area:work"])
        with pytest.raises(PTOSError, match="area"):
            svc.resolve_embed({"view": "todo_summary", "area": "Not A Slug"})

    def test_get_todo_areas_sorted_unique(self):
        _clean()
        _seed_todos(["Beta area:work", "Alpha area:home",
                     "Gamma area:work"])
        assert svc.get_todo_areas() == ["home", "work"]

    def test_widget_options_exposes_todo_areas(self):
        _clean()
        _seed_todos(["Beta area:work", "Alpha area:home"])
        assert svc.get_widget_options("todo.areas") == ["home", "work"]

    def test_lint_accepts_area_key(self):
        assert ptos.lint_todo_views({"todo.work": {"area": "work"}}) == []


class TestTodoPageArea:
    """The shell Todos page carries the area filter, the area list and the
    quick-add area token."""

    @staticmethod
    def _page(args=None):
        import json
        import re
        from ptos_web import app
        response = app.test_client().get("/todo", query_string=args or {})
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        spec = json.loads(re.search(
            r'<script type="application/json" id="page-spec">(.*?)</script>',
            html, re.S).group(1))
        data = json.loads(re.search(
            r'<script type="application/json" id="page-data">(.*?)</script>',
            html, re.S).group(1))
        state = json.loads(re.search(
            r"window\.PTOS_PAGE = (\{.*\});", html, re.S).group(1))
        return html, spec, data, state

    def test_area_param_filters_the_page_and_is_echoed(self):
        _clean()
        _seed_todos(["Ship invoice area:work", "Water plants area:home"])
        _html, spec, data, state = self._page({"area": "work"})
        assert 'area = "work"' in spec["body"]
        # Area token preserved in description
        descriptions = [todo["description"] for group in data["groups"]
                        for todo in group["todos"]]
        assert descriptions == ["Ship invoice area:work"]
        assert state["todo"]["filters"]["area"] == "work"

    def test_page_exposes_the_list_of_areas(self):
        _clean()
        _seed_todos(["Ship invoice area:work", "Water plants area:home"])
        # Schema options order: work, finance, relationship, health, spirituality, career, business, family
        _html, _spec, _data, state = self._page()
        assert state["todo"]["areas"] == ["work", "finance", "relationship", "health", "spirituality", "career", "business", "family"]

    def test_invalid_area_slug_is_reported_not_silently_ignored(self):
        _clean()
        _seed_todos(["Ship invoice area:work"])
        _html, _spec, _data, state = self._page({"area": "Bad Area"})
        assert "area" in (state["error"] or "").lower()


def _flat_descriptions(result):
    return [t["description"] for g in result["groups"] for t in g["todos"]]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])