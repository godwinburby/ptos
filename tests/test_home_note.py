"""Tests for the home note (Phase 3 of the home-note spec).

D1–D4 + D6: first-visit creation, the generated template and its
gating, cleared/missing fallbacks, reset-with-backup, the rename /
delete hooks, `@home` time substitution, span/hide_on keys, the
/home/set and /home/reset routes, and static pins on home_note.js and
its wiring (no CDN, renderMarkdown not marked.parse, single
mountBatch, _greeting gone).
"""
import json
import os
import re
import shutil
import subprocess
import tomllib

import tomli_w

import pytest

import ptos
import ptos_service as svc

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _client():
    from ptos_web import app
    return app.test_client()


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


def _home_content():
    note = svc.svc_read_file("Home.md")
    assert note is not None, "Home.md was not created"
    return note["content"]


def _note_source(html):
    m = re.search(
        r'<script type="application/json" id="home-note-source">'
        r"(.*?)</script>", html, re.S)
    assert m, "home-note-source blob missing"
    return json.loads(m.group(1))


def _batch(bodies, context=None):
    payload = {"items": [{"id": i, "body": b} for i, b in enumerate(bodies)]}
    if context is not None:
        payload["context"] = context
    resp = _client().post("/api/widgets/resolve", json=payload).get_json()
    assert resp.get("ok") is True
    return resp["results"]


class TestFirstVisit:
    def test_creates_home_note_from_template(self):
        assert _client().get("/").status_code == 200
        content = _home_content()
        assert "# {{greeting}}, {{name}}" in content
        assert 'view = "todo_summary"' in content
        assert 'view = "journal"' in content
        assert 'view = "capture"' in content
        assert 'view = "records"' in content
        assert svc.get_home_page() == "Home.md"

    def test_home_route_serves_note_mode_with_created_banner(self):
        body = _client().get("/").get_data(as_text=True)
        assert 'id="home-note-source"' in body
        assert 'id="home-widget-specs"' not in body
        assert "Your home page is now a note you can edit." in body

    def test_second_load_has_no_created_banner(self):
        _client().get("/")
        body = _client().get("/").get_data(as_text=True)
        assert "Your home page is now a note you can edit." not in body

    def test_blob_carries_path_content_and_params(self):
        _client().get("/")
        src = _note_source(_client().get("/").get_data(as_text=True))
        assert src["path"] == "Home.md"
        assert src["source"] == "note"
        assert "# {{greeting}}" in src["content"]
        assert isinstance(src["params"], dict)
        assert isinstance(src["rev"], str) and src["rev"]

    def test_custom_page_is_served_and_default_not_created(self):
        svc.svc_save_file("Start.md", "# Start\n")
        svc.set_home_page("Start.md")
        body = _client().get("/").get_data(as_text=True)
        assert 'id="home-note-source"' in body
        src = _note_source(body)
        assert src["path"] == "Start.md"
        assert "# Start" in src["content"]
        assert not os.path.isfile(ptos._safe_path("Home.md"))


class TestTemplateGating:
    def _bare(self):
        _set_queries({})
        os.makedirs(os.path.dirname(ptos.PRESETS_PATH), exist_ok=True)
        with open(ptos.PRESETS_PATH, "w", encoding="utf-8") as f:
            f.write("")
        ptos._invalidate("presets")

    def test_dashboard_fence_only_when_configured(self):
        self._bare()
        _client().get("/")
        assert 'view = "dashboard"' not in _home_content()

    def test_dashboard_fence_with_default_name(self):
        _set_queries({"dashboards": {"money": {"metrics": []}}})
        _client().get("/")
        c = _home_content()
        assert 'view = "dashboard"' in c
        assert 'name = "money"' in c
        assert "per_query" not in c

    def test_threshold_fence_absent_when_not_configured(self):
        self._bare()
        _client().get("/")
        assert 'view = "threshold"' not in _home_content()

    def test_threshold_fence_when_configured(self):
        _set_queries({"threshold.budget": {
            "metric": "m1", "direction": "max", "target": 10}})
        _client().get("/")
        assert 'view = "threshold"' in _home_content()

    def test_due_fence_absent_when_not_configured(self):
        self._bare()
        _client().get("/")
        assert 'view = "due"' not in _home_content()

    def test_due_fence_when_configured(self):
        _set_queries({"due.default": {"days": 7}})
        _client().get("/")
        content = _home_content()
        assert 'view = "due"' in content
        assert 'name = "default"' in content
        assert "limit = 5" in content

    def test_quick_add_gates(self):
        self._bare()
        _client().get("/")
        c = _home_content()
        assert 'view = "quick_add"' not in c
        assert 'view = "quick_add_multi"' not in c

    def test_sections_present_in_order(self):
        _client().get("/")
        c = _home_content()
        heads = [line for line in c.split("\n") if line.startswith("## ")]
        assert heads == ["## Overview", "## Needs your attention",
                         "## Quick add", "## Today"]


class TestFallback:
    def test_invalid_home_path_falls_back_and_warns_once(self, monkeypatch, caplog):
        monkeypatch.setattr(svc, "_home_page_raw", lambda: "../outside.md")
        monkeypatch.setattr(svc, "_HOME_PAGE_INVALID_LOGGED", False)
        assert svc.get_home_page() is None
        assert svc.get_home_page() is None
        assert sum("Ignoring invalid [home] page value" in r.message
                   for r in caplog.records) == 1
        result = svc.svc_get_home_note()
        assert result == {"mode": "fallback", "reason": "invalid"}
        assert not os.path.exists(ptos._safe_path("Home.md"))

    def test_cleared_setting_falls_back_without_creating(self):
        _client().get("/")
        svc.clear_home_page()
        body = _client().get("/").get_data(as_text=True)
        assert 'id="home-widget-specs"' in body
        assert 'id="home-note-source"' not in body
        svc.svc_delete("Home.md")
        body = _client().get("/").get_data(as_text=True)
        assert 'id="home-widget-specs"' in body
        assert not os.path.isfile(ptos._safe_path("Home.md"))
        assert "gone" not in body

    def test_missing_configured_note_falls_back_with_banner(self):
        svc.set_home_page("Ghost.md")
        body = _client().get("/").get_data(as_text=True)
        assert 'id="home-widget-specs"' in body
        assert "The home page note is gone" in body
        assert not os.path.isfile(ptos._safe_path("Ghost.md"))
        assert svc.get_home_page() == "Ghost.md"


class TestReset:
    def test_reset_rewrites_and_backs_up(self):
        _client().get("/")
        svc.svc_save_file("Home.md", "# my edits\n")
        res = _client().post("/api/home/reset", json={}).get_json()
        assert res["ok"] is True
        assert res["path"] == "Home.md"
        assert res["backup"], "backup path missing"
        assert os.path.isfile(ptos._safe_path(res["backup"]))
        assert svc.svc_read_file(res["backup"])["content"] == "# my edits\n"
        assert "# {{greeting}}" in _home_content()
        assert svc.get_home_page() == "Home.md"

    def test_reset_without_note_has_no_backup(self):
        svc.set_home_page("")
        res = _client().post("/api/home/reset", json={}).get_json()
        assert res["ok"] is True
        assert res["backup"] is None
        assert os.path.isfile(ptos._safe_path("Home.md"))
        assert svc.get_home_page() == "Home.md"

    def test_reset_requires_json_body(self):
        resp = _client().post("/api/home/reset")
        assert resp.status_code == 400


class TestSetRoute:
    def test_set_existing_note(self):
        svc.svc_save_file("Dash.md", "# Dash\n")
        res = _client().post("/api/home/set",
                             json={"path": "Dash.md"}).get_json()
        assert res["ok"] is True
        assert res["path"] == "Dash.md"
        assert svc.get_home_page() == "Dash.md"

    def test_set_missing_note_400(self):
        resp = _client().post("/api/home/set", json={"path": "Ghost.md"})
        assert resp.status_code == 400
        assert "Note not found" in resp.get_json()["error"]

    def test_set_path_escape_400(self):
        resp = _client().post("/api/home/set", json={"path": "../x.md"})
        assert resp.status_code == 400

    def test_set_requires_json_body(self):
        resp = _client().post("/api/home/set")
        assert resp.status_code == 400


class TestRenameDeleteHooks:
    def test_file_rename_follows(self):
        _client().get("/")
        svc.svc_rename("Home.md", "Start")
        assert svc.get_home_page() == "Start.md"
        assert os.path.isfile(ptos._safe_path("Start.md"))

    def test_folder_rename_follows(self):
        svc.svc_create_folder("", "Pages")
        svc.svc_save_file("Pages/Home.md", "# in folder\n")
        svc.set_home_page("Pages/Home.md")
        svc.svc_rename("Pages", "Doc")
        assert svc.get_home_page() == "Doc/Home.md"

    def test_unrelated_rename_leaves_setting(self):
        _client().get("/")
        svc.svc_save_file("Other.md", "# other\n")
        svc.svc_rename("Other.md", "Another")
        assert svc.get_home_page() == "Home.md"

    def test_delete_home_note_clears_setting(self):
        _client().get("/")
        svc.svc_delete("Home.md")
        assert svc.get_home_page() is None
        body = _client().get("/").get_data(as_text=True)
        assert 'id="home-widget-specs"' in body

    def test_delete_folder_containing_home_clears_setting(self):
        svc.svc_create_folder("", "Pages")
        svc.svc_save_file("Pages/Home.md", "# in folder\n")
        svc.set_home_page("Pages/Home.md")
        svc.svc_delete("Pages")
        assert svc.get_home_page() is None

    def test_delete_unrelated_leaves_setting(self):
        _client().get("/")
        svc.svc_save_file("Other.md", "# other\n")
        svc.svc_delete("Other.md")
        assert svc.get_home_page() == "Home.md"


class TestHomeTimeContext:
    def test_at_home_without_context_resolves_tm(self):
        today = ptos.today().strftime("%Y-%m-%d")
        _write_records([f"{today} type=expense amount=10 category=food",
                        "2020-01-01 type=expense amount=9 category=food"])
        d = _batch(['view = "records"\nwhere = ["type=expense"]\n'
                    'time = "@home"'])[0]
        assert d["ok"] is True
        assert d["data"]["count"] == 1

    def test_at_home_with_context_uses_it(self):
        today = ptos.today().strftime("%Y-%m-%d")
        _write_records([f"{today} type=expense amount=10 category=food"])
        d = _batch(['view = "records"\nwhere = ["type=expense"]\n'
                    'time = "@home"'],
                   context={"time": "td"})[0]
        assert d["ok"] is True
        assert d["data"]["count"] == 1

    def test_at_home_with_range_context(self):
        _write_records(["2026-01-10 type=expense amount=10 category=food",
                        "2026-02-10 type=expense amount=9 category=food"])
        d = _batch(['view = "records"\nwhere = ["type=expense"]\n'
                    'time = "@home"'],
                   context={"time": "range", "from_date": "2026-01-01",
                            "to_date": "2026-01-31"})[0]
        assert d["ok"] is True
        assert d["data"]["count"] == 1

    def test_at_home_context_replaces_default_window(self):
        t = ptos.today()
        today = t.strftime("%Y-%m-%d")
        if t.month > 1:
            old = t.replace(month=1, day=2)
            expected_year = 2
        else:
            old = t.replace(year=t.year - 1, month=12, day=2)
            expected_year = 1
        _write_records([f"{today} type=expense amount=10 category=food",
                        f"{old.strftime('%Y-%m-%d')} type=expense amount=9 "
                        "category=food"])
        body = ('view = "records"\nwhere = ["type=expense"]\n'
                'time = "@home"')
        month = _batch([body])[0]
        assert month["ok"] is True
        assert month["data"]["count"] == 1
        year = _batch([body], context={"time": "ty"})[0]
        assert year["ok"] is True
        assert year["data"]["count"] == expected_year

    def test_explicit_time_ignores_context(self):
        today = ptos.today().strftime("%Y-%m-%d")
        _write_records([f"{today} type=expense amount=10 category=food"])
        d = _batch(['view = "records"\nwhere = ["type=expense"]\n'
                    'time = "td"'],
                   context={"time": "ty"})[0]
        assert d["ok"] is True
        assert d["data"]["count"] == 1

    def test_time_options_include_at_home(self):
        opts = svc.get_widget_options("time")
        assert "@home" in opts
        assert opts[0] == "@home"


class TestSpanHideOn:
    def test_span_and_hide_on_resolve(self):
        d = _batch(['view = "todo_summary"\nspan = 2\n'
                    'hide_on = ["phone"]'])[0]
        assert d["ok"] is True
        assert d["data"]["kind"] == "todo_summary"

    def test_span_out_of_range_rejected(self):
        res = svc.validate_widget_spec(
            {"view": "todo_summary", "span": 3})
        assert res["ok"] is False
        assert any(e["field"] == "span" for e in res["errors"])

    def test_span_non_int_rejected(self):
        res = svc.validate_widget_spec(
            {"view": "todo_summary", "span": "2"})
        assert res["ok"] is False
        assert any(e["field"] == "span" for e in res["errors"])

    def test_hide_on_unknown_device_rejected(self):
        res = svc.validate_widget_spec(
            {"view": "todo_summary", "hide_on": ["watch"]})
        assert res["ok"] is False
        assert any(e["field"] == "hide_on" for e in res["errors"])

    def test_valid_span_and_hide_on_pass(self):
        res = svc.validate_widget_spec(
            {"view": "todo_summary", "span": 2,
             "hide_on": ["phone", "desktop"]})
        assert res["ok"] is True, res["errors"]

    def test_widget_fields_carry_span_and_hide_on(self):
        kinds = svc.get_widget_catalog()["kinds"]
        assert kinds, "no kinds in catalog"
        for k in kinds:
            keys = {f["key"] for f in k.get("fields") or []}
            assert "span" in keys, k["kind"]
            assert "hide_on" in keys, k["kind"]


class TestNotesEditorAndSettings:
    def test_notes_edit_marks_home(self):
        _client().get("/")
        body = _client().get("/notes/edit/Home.md").get_data(as_text=True)
        assert "This note is your home page." in body
        assert "Make this my home" not in body

    def test_notes_edit_offers_make_home(self):
        svc.svc_save_file("Other.md", "# other\n")
        body = _client().get("/notes/edit/Other.md").get_data(as_text=True)
        assert "Make this my home" in body
        assert "/api/home/set" in body

    def test_settings_home_card(self):
        _client().get("/")
        body = _client().get("/settings").get_data(as_text=True)
        assert 'id="sec-home"' in body
        assert "Reset home to default" in body
        assert "/api/home/reset" in body


class TestStaticPins:
    def _read(self, *parts):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return open(os.path.join(root, *parts), encoding="utf-8").read()

    def test_home_note_js_has_no_cdn(self):
        src = self._read("web_static", "js", "home_note.js")
        assert "https://" not in src
        assert "http://" not in src

    def test_home_note_js_uses_shared_renderer(self):
        src = self._read("web_static", "js", "home_note.js")
        assert "preprocessLinks" in src
        assert "renderMarkdown" in src
        assert "marked.parse" not in src
        assert "marked.setOptions" not in src

    def test_home_note_js_single_mount_batch_with_context_and_lazy(self):
        src = self._read("web_static", "js", "home_note.js")
        assert src.count(".mountBatch(") == 1
        assert 'host: "home"' in src
        assert "interactive: true" in src
        assert "context: ctx" in src
        assert "lazy: true" in src

    def test_home_note_js_exports_pure_helpers(self):
        src = self._read("web_static", "js", "home_note.js")
        assert "window.PtosHomeNote" in src
        for name in ("split", "homeContext", "applyParamNames", "widgetAttrs"):
            assert name in src, name
        assert "home-note-source" in src

    def test_widget_host_passes_context_and_defers(self):
        src = self._read("web_static", "js", "widget_host.js")
        assert "payload.context = opts.context" in src
        assert "IntersectionObserver" in src
        assert "_phPending" in src

    def test_home_template_note_mode_wiring(self):
        src = self._read("web_templates", "home.html")
        assert 'id="home-note-source"' in src
        assert 'id="home"' in src
        assert "{{ greeting }}" not in src
        assert "home_note.js" in src
        assert "md_render.js" in src

    def test_web_has_no_greeting_helper(self):
        src = self._read("ptos_web.py")
        assert "def _greeting" not in src
        assert "greeting=_greeting()" not in src

    def test_home_uses_av_for_every_asset(self):
        src = self._read("web_templates", "home.html")
        bad = re.findall(r'"/static/(?:js|vendor)/[^"]*"', src)
        assert not bad, "un-versioned static reference: %r" % bad


class TestNodeBehaviorSuite:
    @pytest.mark.skipif(shutil.which("node") is None,
                        reason="node not installed")
    def test_home_note_node_suite(self):
        path = os.path.join(REPO, "tests", "js", "home_note.test.js")
        if not os.path.isfile(path):
            pytest.skip("js suite missing")
        proc = subprocess.run(
            [shutil.which("node"), "--test", path],
            cwd=REPO, capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
