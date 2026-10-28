"""Golden snapshot of /todo page behavior (Stage 1c guard).

Pins which todos land in which bucket for every page filter, via the
rendered template context — so extracting the shared query into
ptos_service.query_todos cannot silently change the page.
"""
import datetime as dt
import os
import shutil
import subprocess

import pytest
import tomli_w

import ptos
import ptos_todo

TODAY = dt.date.today()
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _iso(offset):
    return (TODAY + dt.timedelta(days=offset)).isoformat()


OPEN_LINES = [
    "(A) Call supplier +HearingCare @phone due:" + _iso(-2),
    "(B) Urgent fix +HearingCare @phone due:" + _iso(-1),
    "Pay rent +home @errands due:" + _iso(0),
    "Gym +routine @fitness due:" + _iso(0),
    "Buy milk +home @shop due:" + _iso(1),
    "Plan trip +travel due:" + _iso(3),
    "Far away +home due:" + _iso(30),
    "Read book @reading",
    "Linked carrier +home links:expense:xyz123",
    "Hidden until later +home due:" + _iso(0) + " t:" + _iso(5),
]


@pytest.fixture(autouse=True)
def _seed(tmp_path):
    os.makedirs(ptos.TODO_DIR, exist_ok=True)
    with open(ptos.TODO_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(OPEN_LINES) + "\n")
    done_line = "x 2026-01-02 2026-01-01 Done thing +home"
    with open(ptos.DONE_PATH, "w", encoding="utf-8") as f:
        f.write(done_line + "\n")
    ptos._CACHE.clear()
    ptos_todo._TODO_LOAD_CACHE.clear()
    yield
    ptos._CACHE.clear()
    ptos_todo._TODO_LOAD_CACHE.clear()


def _todo_context(args=None):
    from flask import template_rendered
    from ptos_web import app
    captured = {}

    def _capture(sender, template, context, **extra):
        if template.name == "todo.html":
            captured.update(context)

    template_rendered.connect(_capture)
    try:
        client = app.test_client()
        query = dict(args or {})
        query["legacy"] = "1"
        resp = client.get("/todo", query_string=query)
        assert resp.status_code == 200
    finally:
        template_rendered.disconnect(_capture)
    assert captured, "todo.html did not render"
    return captured


def _descs(buckets, key):
    return [t.description for t in buckets[key]]


def _nonempty(buckets):
    return {k: _descs(buckets, k)
            for k in ("overdue", "today", "tomorrow", "upcoming", "someday")
            if buckets[k]}


class TestTodoPageGolden:
    def test_default_buckets(self):
        ctx = _todo_context()
        b = ctx["buckets"]
        assert _nonempty(b) == {
            "overdue": ["Call supplier", "Urgent fix"],
            "today": ["Gym", "Pay rent"],
            "tomorrow": ["Buy milk"],
            "upcoming": ["Plan trip"],
            "someday": ["Far away", "Linked carrier", "Read book"],
        }
        assert ctx["selected_project"] is None
        assert ctx["groupby"] == "timeline"

    def test_threshold_hidden_until_due(self):
        ctx = _todo_context()
        all_descs = []
        for key in ("overdue", "today", "tomorrow", "upcoming", "someday"):
            all_descs += _descs(ctx["buckets"], key)
        assert "Hidden until later" not in all_descs

    def test_done_todos_not_in_open_buckets(self):
        ctx = _todo_context()
        assert ctx["done_recent"][0].description == "Done thing"
        all_descs = []
        for key in ("overdue", "today", "tomorrow", "upcoming", "someday"):
            all_descs += _descs(ctx["buckets"], key)
        assert "Done thing" not in all_descs

    def test_project_include(self):
        ctx = _todo_context({"project": "home"})
        assert _nonempty(ctx["buckets"]) == {
            "today": ["Pay rent"],
            "tomorrow": ["Buy milk"],
            "someday": ["Far away", "Linked carrier"],
        }

    def test_project_exclude_routine(self):
        ctx = _todo_context({"project": "-routine"})
        assert _descs(ctx["buckets"], "today") == ["Pay rent"]

    def test_hide_routines_config_without_param(self):
        cfg_path = ptos.CONFIG_PATH
        with ptos.AtomicWrite(cfg_path, "config") as w:
            tomli_w.dump({"todo": {"hide_routines": True}}, w.stream)
        ptos._invalidate_all()
        try:
            ctx = _todo_context()
            assert _descs(ctx["buckets"], "today") == ["Pay rent"]
            assert ctx["hide_routines"] is True
        finally:
            with ptos.AtomicWrite(cfg_path, "config") as w:
                tomli_w.dump({}, w.stream)
            ptos._invalidate_all()


class TestTodoPageShell:
    def _shell_data(self, args=None):
        import json
        from ptos_web import app
        response = app.test_client().get("/todo", query_string=args or {})
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        match = __import__("re").search(
            r'<script type="application/json" id="page-data">(.*?)</script>',
            html, __import__("re").S)
        assert match, "todo shell did not inline widget data"
        spec_match = __import__("re").search(
            r'<script type="application/json" id="page-spec">(.*?)</script>',
            html, __import__("re").S)
        assert spec_match, "todo shell did not inline its widget spec"
        return html, json.loads(match.group(1)), json.loads(spec_match.group(1))

    def test_todo_shell_inlines_grouped_rows_and_recent_done(self):
        html, data, _spec = self._shell_data()
        assert 'id="page-widget-toolbar"' in html
        assert 'class="page-shell page-shell-todo"' in html
        assert 'todo_toolbar.js' in html
        assert 'id="todo-modal"' in html
        assert data["kind"] == "todo"
        grouped = {g["key"]: [t["description"] for t in g["todos"]]
                   for g in data["groups"]}
        assert grouped["overdue"] == ["Call supplier", "Urgent fix"]
        assert grouped["today"] == ["Gym", "Pay rent"]
        assert grouped["done"] == ["Done thing"]

    def test_todo_shell_preserves_filter_and_groupby_url(self):
        html, data, spec = self._shell_data({
            "project": "home", "context": "shop", "groupby": "priority",
            "search": "milk", "sort": "reverse"
        })
        assert "project=home" in html
        assert data["filters"] == {"project": "home", "context": "shop"}
        assert 'project = "home"' in spec["body"]
        assert 'search = "milk"' in spec["body"]
        assert 'groupby = "priority"' in spec["body"]
        assert 'sort = "reverse"' in spec["body"]
        assert len(data["groups"]) == 1
        assert data["groups"][0]["todos"][0]["description"] == "Buy milk"

    def test_todo_shell_filtered_rows_match_legacy_page(self):
        args = {"project": "home", "context": "shop", "search": "milk",
                "groupby": "priority"}
        _html, data, _spec = self._shell_data(args)
        legacy = _todo_context(args)
        expected = [todo.description for _key, _label, _color, todos in legacy["grouped"]
                    for todo in todos]
        actual = [todo["description"] for group in data["groups"]
                  for todo in group["todos"]]
        assert actual == expected

    def test_todo_legacy_page_remains_available(self):
        from ptos_web import app
        response = app.test_client().get("/todo?legacy=1")
        assert b"id=\"page-widget-toolbar\"" not in response.data
        assert b"groupby-bar" in response.data

    def test_todo_shell_node_suite(self):
        node = shutil.which("node")
        if node is None:
            message = "Node.js is required for Todo shell tests; run npm ci"
            if os.environ.get("CI"):
                pytest.fail(message)
            pytest.skip(message)
        probe = subprocess.run([node, "-e", "require.resolve('jsdom')"],
                               cwd=REPO, capture_output=True, text=True)
        if probe.returncode != 0:
            message = "jsdom is required for Todo shell tests; run npm ci"
            if os.environ.get("CI"):
                pytest.fail(message)
            pytest.skip(message)
        result = subprocess.run(
            [node, "--test", "tests/js/todo_shell.test.js"], cwd=REPO,
            capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_context_filter(self):
        ctx = _todo_context({"context": "@phone"})
        assert _nonempty(ctx["buckets"]) == {
            "overdue": ["Call supplier", "Urgent fix"],
        }

    def test_priority_filter_case_insensitive(self):
        ctx = _todo_context({"priority": "b"})
        assert _nonempty(ctx["buckets"]) == {
            "overdue": ["Urgent fix"],
        }

    def test_search_glob(self):
        ctx = _todo_context({"search": "milk"})
        assert _nonempty(ctx["buckets"]) == {
            "tomorrow": ["Buy milk"],
        }

    def test_linked_to(self):
        ctx = _todo_context({"linked_to": "expense:xyz123"})
        assert _nonempty(ctx["buckets"]) == {
            "someday": ["Linked carrier"],
        }

    def test_due_range_today(self):
        ctx = _todo_context({"due": "today"})
        assert _nonempty(ctx["buckets"]) == {
            "today": ["Gym", "Pay rent"],
        }

    def test_due_range_none_keeps_someday_bucket(self):
        ctx = _todo_context({"due": "none"})
        assert _nonempty(ctx["buckets"]) == {
            "someday": ["Far away", "Linked carrier", "Read book"],
        }

    def test_overdue_sorted_most_overdue_first(self):
        ctx = _todo_context()
        assert _descs(ctx["buckets"], "overdue") == ["Call supplier",
                                                     "Urgent fix"]
