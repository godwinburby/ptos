import datetime as dt
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


class TestResolveEmbedNewKindsInference:
    def test_board_inferred(self):
        _clean()
        _set_queries(_rich_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "demo"})
        assert r["kind"] == "board"
        assert r["board_name"] == "demo"
        assert r["link"] == "/board?board=demo"

    def test_habit_inferred(self):
        _clean()
        _set_queries(_rich_queries())
        r = svc.resolve_embed({"name": "med"})
        assert r["kind"] == "habit"
        assert r["habit_name"] == "med"
        assert r["link"] == "/habits"

    def test_calendar_inferred(self):
        _clean()
        _set_queries(_rich_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "personal"})
        assert r["kind"] == "calendar"
        assert r["calendar_name"] == "personal"

    def test_calendar_embed_uses_display_fields(self):
        _clean()
        q = _base_queries()
        q["calendar.personal"] = {"filters": ["type=expense"],
                                  "display_fields": ["category", "amount"]}
        _set_queries(q)
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "personal", "view": "calendar"})
        assert r["kind"] == "calendar"
        cells = [c for w in r["weeks"] for c in w if c]
        rec = next(c for c in cells if c["records"])["records"][0]
        assert rec["fields"] == ["food", "100"]

    def test_calendar_all_records_view(self):
        _clean()
        _set_queries(_rich_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "__all__"})
        assert r["kind"] == "calendar"
        assert r["link"] == "/calendar"

    def test_due_named_inferred(self):
        _clean()
        _set_queries(_rich_queries())
        r = svc.resolve_embed({"name": "weekly"})
        assert r["kind"] == "due"

    def test_due_default_inferred(self):
        _clean()
        _set_queries(_rich_queries())
        _seed_due_expenses()
        r = svc.resolve_embed({"name": "default"})
        assert r["kind"] == "due"
        assert r["link"] == "/due"
        assert r["count"] == 2

    def test_due_double_default_token(self):
        _clean()
        _set_queries(_rich_queries())
        r = svc.resolve_embed({"name": "__DEFAULT__"})
        assert r["kind"] == "due"

    def test_project_inferred(self):
        _clean()
        _set_queries(_rich_queries())
        r = svc.resolve_embed({"name": "wob"})
        assert r["kind"] == "project"
        assert r["link"] == "/projects"


class TestResolveEmbedNewKindsDispatch:
    def test_board_carries_counts_and_rollups(self):
        _clean()
        _set_queries(_rich_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "demo", "view": "board"})
        assert r["counts"]["expense"] == 2
        assert r["columns"] == ["expense"]
        assert r["rollup_op"] == "count"

    def test_habit_carries_streak_and_months(self):
        _clean()
        _set_queries(_rich_queries())
        r = svc.resolve_embed({"name": "med", "view": "habit"})
        assert r["streak"] == 0
        assert isinstance(r["months"], list) and r["months"]
        assert "date" in r["months"][-1]["days"][0] or r["months"][-1]["days"][0] is None

    def test_calendar_month_from_from_date(self):
        _clean()
        _set_queries(_rich_queries())
        r = svc.resolve_embed({"name": "personal", "from_date": "2026-01-15"})
        assert r["year"] == 2026
        assert r["month"] == 1

    def test_calendar_month_from_time(self):
        _clean()
        _set_queries(_rich_queries())
        r = svc.resolve_embed({"name": "personal", "time": "2026-02"})
        assert r["year"] == 2026
        assert r["month"] == 2

    def test_calendar_default_month_is_current(self):
        _clean()
        _set_queries(_rich_queries())
        r = svc.resolve_embed({"name": "personal"})
        assert r["year"] == dt.date.today().year
        assert r["month"] == dt.date.today().month

    def test_due_ignores_time_spec(self):
        _clean()
        _set_queries(_rich_queries())
        _seed_due_expenses()
        base = svc.resolve_embed({"name": "default"})
        with_time = svc.resolve_embed({"name": "default", "time": "all",
                                       "from_date": "2000-01-01",
                                       "to_date": "2099-12-31"})
        assert with_time["count"] == base["count"]
        assert with_time["link"] == "/due"

    def test_due_limit_truncates_rows(self):
        _clean()
        _set_queries(_rich_queries())
        _seed_due_expenses()
        r = svc.resolve_embed({"name": "default", "limit": 1})
        assert len(r["rows"]) == 1
        assert r["count"] == 1

    def test_project_shape(self):
        _clean()
        _set_queries(_rich_queries())
        d = ptos.today().strftime("%Y-%m-%d")
        _write_records([f"{d} type=expense amount=50 category=food tag=wob"])
        r = svc.resolve_embed({"name": "wob", "view": "project"})
        assert r["name"] == "wob"
        assert r["label"] == "World of Birds"
        assert r["record_count"] == 1
        assert r["drift"] == "ok"
        assert r["stale_days"] == 0

    def test_project_unknown_raises(self):
        _clean()
        _set_queries(_rich_queries())
        with pytest.raises(PTOSError):
            svc.resolve_embed({"name": "notaproject"})


class TestResolveEmbedCollisions:
    def _collision_queries(self):
        return {
            "prescription": {"where": "type=expense", "time": "this-month"},
            "calendar.prescription": {"filters": ["type=expense"]},
        }

    def test_ambiguous_name_raises_with_candidates(self):
        _clean()
        _set_queries(self._collision_queries())
        with pytest.raises(PTOSError) as ei:
            svc.resolve_embed({"name": "prescription"})
        msg = str(ei.value)
        assert "multiple sections" in msg
        assert "calendar" in msg and "query" in msg
        assert "view" in msg

    def test_collision_resolved_by_explicit_view_query(self):
        _clean()
        _set_queries(self._collision_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "prescription", "view": "query"})
        assert r["kind"] == "records"
        assert r["count"] == 2

    def test_collision_resolved_by_explicit_view_calendar(self):
        _clean()
        _set_queries(self._collision_queries())
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "prescription", "view": "calendar"})
        assert r["kind"] == "calendar"
        assert r["calendar_name"] == "prescription"

    def test_metric_query_collision_raises(self):
        _clean()
        _set_queries({
            "total": {"where": "type=expense", "time": "this-month"},
            "metrics": {"total": {"sum": "exp"}},
        })
        with pytest.raises(PTOSError) as ei:
            svc.resolve_embed({"name": "total"})
        msg = str(ei.value)
        assert "metric" in msg and "query" in msg

    def test_single_owner_still_inferred(self):
        _clean()
        _set_queries({"calendar.prescription": {"filters": ["type=expense"]}})
        _seed_two_expenses()
        r = svc.resolve_embed({"name": "prescription"})
        assert r["kind"] == "calendar"
        assert r["calendar_name"] == "prescription"


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

    def test_habit_serializes(self):
        _clean()
        _set_queries(_rich_queries())
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/embed/resolve",
                           json={"body": 'name = "med"'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["data"]["kind"] == "habit"

    def test_calendar_serializes(self):
        _clean()
        _set_queries(_rich_queries())
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/embed/resolve",
                           json={"body": 'name = "personal"'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["data"]["kind"] == "calendar"

    def test_project_serializes(self):
        _clean()
        _set_queries(_rich_queries())
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/embed/resolve",
                           json={"body": 'name = "wob"'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["data"]["kind"] == "project"


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
        "due.default": {"type": "expense", "key": "category", "days": 3},
        "due.weekly": {"type": "expense", "key": "category", "days": 7},
        "project.wob": {"label": "World of Birds", "tag_filters": ["tag=wob"]},
    }


def _seed_due_expenses(days_ago=5):
    d = (ptos.today() - dt.timedelta(days=days_ago)).strftime("%Y-%m-%d")
    _write_records([
        f"{d} type=expense amount=100 category=food",
        f"{d} type=expense amount=250 category=transport",
    ])


class TestEmbedCandidates:
    def test_groups(self):
        _clean()
        _set_queries(_rich_queries())
        c = svc.get_embed_candidates()
        assert c["queries"] == ["exp"]
        assert c["metrics"] == ["total_spend"]
        assert c["dashboards"] == ["money"]
        assert c["thresholds"] == ["spend"]
        assert c["boards"] == ["demo"]
        assert c["habits"] == ["med"]
        assert c["calendars"] == ["personal"]
        assert c["due"] == ["default", "weekly"]
        assert c["projects"] == ["wob"]

    def test_due_default_sorted_first(self):
        _clean()
        _set_queries(_rich_queries())
        c = svc.get_embed_candidates()
        assert c["due"][0] == "default"
        assert sorted(c["due"])[0] == "default"

    def test_excludes_alias_and_userspace_sections(self):
        _clean()
        _set_queries(_rich_queries())
        c = svc.get_embed_candidates()
        for bad in ("my_alias", "board.demo", "habit.med",
                    "calendar.personal", "due.default", "threshold.spend",
                    "project.wob"):
            assert bad not in c["queries"]

    def test_empty_queries(self):
        _clean()
        _set_queries({})
        c = svc.get_embed_candidates()
        assert c == {"queries": [], "metrics": [], "dashboards": [],
                     "thresholds": [], "boards": [], "habits": [],
                     "calendars": [], "due": [], "projects": []}


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
        assert kinds["b"] == ["demo"]
        assert kinds["h"] == ["med"]
        assert kinds["c"] == ["personal"]
        assert kinds["u"] == ["default", "weekly"]
        assert kinds["p"] == ["wob"]

    def test_time_options_present_and_filtered(self):
        _clean()
        _set_queries(_rich_queries())
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/embed/candidates")
        data = resp.get_json()
        assert "time_options" in data
        values = [t["value"] for t in data["time_options"]]
        assert "tm" in values
        assert "lm" in values
        assert "ty" in values
        assert "all" in values
        for bad in ("year", "month", "date", "range"):
            assert bad not in values, bad
        for entry in data["time_options"]:
            assert "label" in entry
            assert "value" in entry


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

    def test_slash_menu_inserts_explicit_view(self):
        path = os.path.join(_REPO_ROOT, "web_static", "js", "slash_embed.js")
        with open(path, encoding="utf-8") as f:
            js = f.read()
        for mapping in ('"query"', '"metric"', '"dashboard"', '"threshold"',
                        '"board"', '"habit"', '"calendar"', '"due"',
                        '"project"'):
            assert mapping in js, mapping
        assert "'view = " + '"' in js
        assert "item.view" in js
        assert "item.name" in js
        assert "item.name" in js

    def test_embed_cards_are_read_only(self):
        # The preview is a render of the finished page. Every edit / move /
        # add control lives in Blocks mode (md_blocks.js), so the preview
        # mounter keeps no source and writes nothing back.
        path = os.path.join(_REPO_ROOT, "web_static", "js", "embeds.js")
        with open(path, encoding="utf-8") as f:
            js = f.read()
        assert "window.mountEmbeds = function (pane)" in js
        for gone in ("function swapRegions", "function replaceRegion",
                     "_wireReorder", "_swapWith", "_moveBy", "_editWidget",
                     "_applyEdit", "_cancelEdit", "_fenceLines",
                     "window.swapEmbedRegions", "window.replaceEmbedRegion",
                     "srcEl", "draggable"):
            assert gone not in js, gone
        # embedRegions stays — Blocks mode cuts fences with it.
        assert "function embedRegions" in js
        assert "window.embedRegions = embedRegions" in js

    def test_preview_card_shows_title_and_link_only(self):
        path = os.path.join(_REPO_ROOT, "web_static", "js", "embeds.js")
        with open(path, encoding="utf-8") as f:
            js = f.read()
        assert "md-embed-title" in js
        assert "md-embed-link" in js
        for gone in ("md-embed-move-up", "md-embed-move-down", "md-embed-edit\"",
                     "md-embed-refresh", "Edit this widget", "_headActions",
                     "_wireActions"):
            assert gone not in js, gone

    def test_preview_ships_no_control_css(self):
        # The preview keeps only its render styles; the edit box, refresh and
        # move buttons are gone. (The md-embed-edit-{hint,save,cancel} trio
        # stays because md_blocks.js reuses it.)
        path = os.path.join(_REPO_ROOT, "web_templates",
                            "_markdown_editor.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        for gone in (".md-embed.dragging", ".md-embed.drag-over",
                     ".md-embed-move", ".md-embed-refresh", ".md-embed-edit {",
                     ".md-embed-edit-box", ".md-embed-actions"):
            assert gone not in html, gone
        for cls in (".md-embed {", ".md-embed-head", ".md-embed-title",
                    ".md-embed-link", ".md-embed-body",
                    ".md-embed-edit-hint", ".md-embed-edit-save",
                    ".md-embed-edit-cancel"):
            assert cls in html, cls

    def test_editor_passes_pane_only_to_mountembeds(self):
        path = os.path.join(_REPO_ROOT, "web_templates",
                            "_markdown_editor.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        assert "mountEmbeds(pane)" in html
        assert "mountEmbeds(pane, src" not in html

    def test_toolbar_insert_view_button_calls_slash_menu(self):
        path = os.path.join(_REPO_ROOT, "web_templates",
                            "_markdown_editor.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        assert 'id="btn-insert"' in html
        assert "openSlashMenu(document.getElementById('{{ _eid }}'))" in html

    def test_slash_menu_exports_open_slash_menu(self):
        path = os.path.join(_REPO_ROOT, "web_static", "js", "slash_embed.js")
        with open(path, encoding="utf-8") as f:
            js = f.read()
        assert "window.openSlashMenu = function (el)" in js
        assert 'prefix + "/" + val.slice(pos)' in js
        assert 'dispatchEvent(new Event("input", { bubbles: true }))' in js
        assert "el.setSelectionRange(caret, caret)" in js

    def test_open_slash_menu_cancels_pending_blur_close(self):
        path = os.path.join(_REPO_ROOT, "web_static", "js", "slash_embed.js")
        with open(path, encoding="utf-8") as f:
            js = f.read()
        assert "list._blurTimer = setTimeout" in js
        assert "clearTimeout(list._blurTimer)" in js
        assert "document.activeElement === el" in js
        assert 'window.setMode("edit")' in js

    def test_queries_page_uses_shared_renderers(self):
        path = os.path.join(_REPO_ROOT, "web_templates", "queries.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        assert "av('/static/js/widgets.js')" in html
        assert "function renderResult" not in html
        assert "function renderDashboard" not in html

    def test_widgets_ships_new_kind_renderers(self):
        path = os.path.join(_REPO_ROOT, "web_static", "js", "widgets.js")
        with open(path, encoding="utf-8") as f:
            js = f.read()
        for fn in ("renderBoard", "renderHabit", "renderCalendar",
                   "renderDue", "renderProject"):
            assert f"function {fn}" in js, fn
        for case in ('case "board"', 'case "habit"', 'case "calendar"',
                     'case "due"', 'case "project"'):
            assert case in js, case

    def test_calendar_embed_lists_records_in_cells(self):
        path = os.path.join(_REPO_ROOT, "web_static", "js", "widgets.js")
        with open(path, encoding="utf-8") as f:
            js = f.read()
        start = js.index("function renderCalendar")
        end = js.index("function renderDue")
        cal = js[start:end]
        assert "cell.records" in cal
        assert "r.fields" in cal
        assert "emb-calc-chip" in cal
        assert "emb-cal-rec-grid" in cal
        assert "emb-cal-day-list" in cal
        assert "emb-cal-rec" in cal

    def test_calendar_embed_shows_per_day_details(self):
        path = os.path.join(_REPO_ROOT, "web_static", "js", "widgets.js")
        with open(path, encoding="utf-8") as f:
            js = f.read()
        start = js.index("function renderCalendar")
        end = js.index("function renderDue")
        cal = js[start:end]
        assert "emb-cal-day-list" in cal
        assert "emb-cal-day-head" in cal
        assert "emb-cal-browse" in cal
        assert "r.note" in cal
        assert "emb-cal-rec-note" in cal
        assert "/browse?time=range" in cal
        assert "_pad2" in cal

    def test_markdown_editor_ships_embed_css(self):
        path = os.path.join(_REPO_ROOT, "web_templates",
                            "_markdown_editor.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        for cls in (".emb-chip", ".emb-cal", ".emb-due-row",
                    ".emb-heat", ".emb-stat", ".emb-calc-cell",
                    ".emb-cal-day-list", ".emb-cal-day",
                    ".emb-cal-day-head", ".emb-cal-browse",
                    ".emb-cal-rec", ".emb-cal-rec-note"):
            assert cls in html, cls

    def test_slash_menu_supports_time_window(self):
        path = os.path.join(_REPO_ROOT, "web_static", "js", "slash_embed.js")
        with open(path, encoding="utf-8") as f:
            js = f.read()
        assert "_TIME_CAPABLE" in js
        assert "_openTimeStep" in js
        assert 'time = "' in js
        assert "_pendingItem" in js
        for kind in ("query", "metric", "dashboard", "threshold",
                     "board", "habit", "calendar"):
            assert kind in js, kind
        assert "due" not in js.split("_TIME_CAPABLE")[1].split("}")[0]
        assert "project" not in js.split("_TIME_CAPABLE")[1].split("}")[0]
        assert "list._mode = \"time\"" in js
        assert "list._mode = \"embed\"" in js

    def test_embed_error_card_keeps_its_name_but_no_edit(self):
        path = os.path.join(_REPO_ROOT, "web_static", "js", "embeds.js")
        with open(path, encoding="utf-8") as f:
            js = f.read()
        assert "function _paintError" in js
        # a failed resolve still paints a card with the widget's name from
        # its TOML so you can tell which fence broke; the fix is Blocks mode
        assert "_paintError(container, res.error)" in js
        assert '"Failed to load widget"' in js
        assert "error: String(e)" in js
        assert "md-embed-title" in js
        # but no ✎ — the preview never edits
        assert "md-embed-edit" not in js

