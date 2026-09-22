"""
tests/test_scoped_writes.py  —  Tests for scoped query TOML write functions.

The core guarantee: touching one entry leaves every other section untouched.
"""

import os
import pytest
import textwrap

import ptos
import ptos_service as svc
from ptos import PTOSError


def _write_queries(content):
    with open(ptos.QUERIES_PATH, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content))
    ptos._invalidate_all()


def _read():
    return svc._load_queries_toml()


_FULL_TOML = """\
[expenses]
where = "type=expense"
time = "this-month"

[income]
where = "type=income"
time = "all"

[metrics.food_ratio]
ratio = ["expenses", "income"]

[dashboards.fin]
metrics = ["expenses", "income"]

[my_alias]
alias = "expenses"

[board.kanban]
columns = ["task"]
time_window = "this-month"

[habit.meditation]
filters = ["type=habit name=meditation"]
weeks = 12

[calendar.expenses]
filters = ["type=expense"]
time_window = "this-month"

[threshold.spending]
metric = "expenses"
direction = "max"
time = "this-month"

[due.tasks]
type = "todo"
key = "due"

[project.jobsearch]
label = "Find a Job"
"""


class TestIsolation:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        _write_queries(_FULL_TOML)

    def test_save_query_entry_leaves_others(self):
        svc.save_query_entry("expenses", {"where": "type=expense AND tag=food", "time": "tm"})
        data = _read()
        assert data["expenses"]["where"] == "type=expense AND tag=food"
        assert data["income"]["where"] == "type=income"
        assert data["metrics"]["food_ratio"]["ratio"] == ["expenses", "income"]
        assert data["dashboards"]["fin"]["metrics"] == ["expenses", "income"]
        assert data["my_alias"]["alias"] == "expenses"
        assert data["board.kanban"]["columns"] == ["task"]
        assert data["habit.meditation"]["filters"] == ["type=habit name=meditation"]
        assert data["calendar.expenses"]["filters"] == ["type=expense"]
        assert data["threshold.spending"]["direction"] == "max"
        assert data["due.tasks"]["type"] == "todo"
        assert data["project.jobsearch"]["label"] == "Find a Job"

    def test_save_metric_leaves_others(self):
        svc.save_metric("food_ratio", {"kind": "sum", "base": "expenses", "time": "tm"})
        data = _read()
        assert data["metrics"]["food_ratio"]["sum"] == "expenses"
        assert data["metrics"]["food_ratio"]["time"] == "tm"
        assert data["expenses"]["where"] == "type=expense"
        assert data["income"]["where"] == "type=income"
        assert data["dashboards"]["fin"]["metrics"] == ["expenses", "income"]

    def test_save_dashboard_leaves_others(self):
        svc.save_dashboard("fin", {"metrics": ["income"], "groups": {"Rev": ["income"]}})
        data = _read()
        assert data["dashboards"]["fin"]["metrics"] == ["income"]
        assert data["dashboards"]["fin"]["groups"] == {"Rev": ["income"]}
        assert data["expenses"]["where"] == "type=expense"
        assert data["metrics"]["food_ratio"]["ratio"] == ["expenses", "income"]

    def test_save_alias_leaves_others(self):
        svc.save_alias("my_alias", {"alias": "income"})
        data = _read()
        assert data["my_alias"]["alias"] == "income"
        assert data["expenses"]["where"] == "type=expense"
        assert data["metrics"]["food_ratio"]["ratio"] == ["expenses", "income"]

    def test_save_board_leaves_others(self):
        svc.save_board("kanban", {"columns": ["task", "expense"], "time_window": "tm"})
        data = _read()
        assert data["board.kanban"]["columns"] == ["task", "expense"]
        assert data["board.kanban"]["time_window"] == "tm"
        assert data["expenses"]["where"] == "type=expense"
        assert data["habit.meditation"]["weeks"] == 12

    def test_save_habit_leaves_others(self):
        svc.save_habit("meditation", {"filters": ["type=habit name=meditation"], "weeks": 24})
        data = _read()
        assert data["habit.meditation"]["weeks"] == 24
        assert data["expenses"]["where"] == "type=expense"
        assert data["board.kanban"]["columns"] == ["task"]

    def test_save_calendar_leaves_others(self):
        svc.save_calendar("expenses", {"filters": ["type=expense"], "time_window": "tm"})
        data = _read()
        assert data["calendar.expenses"]["time_window"] == "tm"
        assert data["expenses"]["where"] == "type=expense"
        assert data["threshold.spending"]["direction"] == "max"

    def test_save_threshold_leaves_others(self):
        svc.save_threshold("spending", {"metric": "expenses", "direction": "max", "time": "tm"})
        data = _read()
        assert data["threshold.spending"]["time"] == "tm"
        assert data["expenses"]["where"] == "type=expense"
        assert data["project.jobsearch"]["label"] == "Find a Job"

    def test_save_due_leaves_others(self):
        svc.save_due("tasks", {"type": "todo", "key": "due", "days": 7})
        data = _read()
        assert data["due.tasks"]["days"] == 7
        assert data["expenses"]["where"] == "type=expense"

    def test_save_project_leaves_others(self):
        svc.save_project("jobsearch", {"label": "Job Hunt", "todo_project": "jobs"})
        data = _read()
        assert data["project.jobsearch"]["label"] == "Job Hunt"
        assert data["project.jobsearch"]["todo_project"] == "jobs"
        assert data["expenses"]["where"] == "type=expense"
        assert data["board.kanban"]["columns"] == ["task"]


class TestDeleteIsolation:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        _write_queries(_FULL_TOML)

    def test_delete_query_entry_leaves_others(self):
        svc.delete_query_entry("expenses")
        data = _read()
        assert "expenses" not in data
        assert data["income"]["where"] == "type=income"
        assert data["metrics"]["food_ratio"]["ratio"] == ["expenses", "income"]
        assert data["dashboards"]["fin"]["metrics"] == ["expenses", "income"]
        assert data["my_alias"]["alias"] == "expenses"
        assert data["board.kanban"]["columns"] == ["task"]

    def test_delete_metric_leaves_others(self):
        svc.delete_metric("food_ratio")
        data = _read()
        assert "food_ratio" not in data.get("metrics", {})
        assert data["expenses"]["where"] == "type=expense"
        assert data["income"]["where"] == "type=income"
        assert data["dashboards"]["fin"]["metrics"] == ["expenses", "income"]

    def test_delete_dashboard_leaves_others(self):
        svc.delete_dashboard("fin")
        data = _read()
        assert "fin" not in data.get("dashboards", {})
        assert data["expenses"]["where"] == "type=expense"
        assert data["metrics"]["food_ratio"]["ratio"] == ["expenses", "income"]

    def test_delete_alias_leaves_others(self):
        svc.delete_alias("my_alias")
        data = _read()
        assert "my_alias" not in data
        assert data["expenses"]["where"] == "type=expense"

    def test_delete_board_leaves_others(self):
        svc.delete_board("kanban")
        data = _read()
        assert "board.kanban" not in data
        assert data["expenses"]["where"] == "type=expense"
        assert data["habit.meditation"]["weeks"] == 12

    def test_delete_habit_leaves_others(self):
        svc.delete_habit("meditation")
        data = _read()
        assert "habit.meditation" not in data
        assert data["expenses"]["where"] == "type=expense"
        assert data["board.kanban"]["columns"] == ["task"]

    def test_delete_calendar_leaves_others(self):
        svc.delete_calendar("expenses")
        data = _read()
        assert "calendar.expenses" not in data
        assert data["expenses"]["where"] == "type=expense"
        assert data["threshold.spending"]["direction"] == "max"

    def test_delete_threshold_leaves_others(self):
        svc.delete_threshold("spending")
        data = _read()
        assert "threshold.spending" not in data
        assert data["expenses"]["where"] == "type=expense"
        assert data["project.jobsearch"]["label"] == "Find a Job"

    def test_delete_due_leaves_others(self):
        svc.delete_due("tasks")
        data = _read()
        assert "due.tasks" not in data
        assert data["expenses"]["where"] == "type=expense"

    def test_delete_project_leaves_others(self):
        svc.delete_project("jobsearch")
        data = _read()
        assert "project.jobsearch" not in data
        assert data["expenses"]["where"] == "type=expense"
        assert data["board.kanban"]["columns"] == ["task"]


class TestValidation:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        _write_queries(_FULL_TOML)

    def test_invalid_name_rejected(self):
        with pytest.raises(PTOSError, match="lowercase"):
            svc.save_query_entry("Bad Name!", {})

    def test_reserved_name_rejected_for_query(self):
        with pytest.raises(PTOSError, match="reserved"):
            svc.save_query_entry("metrics", {})

    def test_reserved_name_rejected_for_alias(self):
        with pytest.raises(PTOSError, match="reserved"):
            svc.save_alias("dashboards", {"alias": "foo"})

    def test_empty_name_rejected(self):
        with pytest.raises(PTOSError, match="lowercase"):
            svc.save_board("", {"columns": ["task"]})

    def test_delete_nonexistent_query_raises(self):
        with pytest.raises(PTOSError, match="not found"):
            svc.delete_query_entry("nonexistent")

    def test_delete_nonexistent_board_raises(self):
        with pytest.raises(PTOSError, match="not found"):
            svc.delete_board("nonexistent")

    def test_delete_nonexistent_metric_raises(self):
        with pytest.raises(PTOSError, match="not found"):
            svc.delete_metric("nonexistent")

    def test_delete_nonexistent_dashboard_raises(self):
        with pytest.raises(PTOSError, match="not found"):
            svc.delete_dashboard("nonexistent")

    def test_delete_nonexistent_project_raises(self):
        with pytest.raises(PTOSError, match="not found"):
            svc.delete_project("nonexistent")

    def test_delete_nonexistent_habit_raises(self):
        with pytest.raises(PTOSError, match="not found"):
            svc.delete_habit("nonexistent")

    def test_delete_nonexistent_calendar_raises(self):
        with pytest.raises(PTOSError, match="not found"):
            svc.delete_calendar("nonexistent")

    def test_delete_nonexistent_threshold_raises(self):
        with pytest.raises(PTOSError, match="not found"):
            svc.delete_threshold("nonexistent")

    def test_delete_nonexistent_due_raises(self):
        with pytest.raises(PTOSError, match="not found"):
            svc.delete_due("nonexistent")

    def test_delete_nonexistent_alias_raises(self):
        with pytest.raises(PTOSError, match="not found"):
            svc.delete_alias("nonexistent")


class TestRoundTrip:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))

    def test_query_round_trip(self):
        svc.save_query_entry("my_q", {"where": "type=task", "time": "tm", "group": ["type"]})
        data = _read()
        assert data["my_q"]["where"] == "type=task"
        assert data["my_q"]["time"] == "tm"
        assert data["my_q"]["group"] == ["type"]

    def test_metric_round_trip(self):
        svc.save_metric("rev", {"kind": "sum", "base": "income", "time": "tm"})
        data = _read()
        assert data["metrics"]["rev"]["sum"] == "income"
        assert data["metrics"]["rev"]["time"] == "tm"

    def test_metric_ratio_round_trip(self):
        svc.save_metric("ratio1", {"kind": "ratio", "base": "income", "base2": "expense"})
        data = _read()
        assert data["metrics"]["ratio1"]["ratio"] == ["income", "expense"]

    def test_dashboard_round_trip(self):
        svc.save_dashboard("d1", {"metrics": ["m1", "m2"], "groups": {"G": ["m1"]}})
        data = _read()
        assert data["dashboards"]["d1"]["metrics"] == ["m1", "m2"]
        assert data["dashboards"]["d1"]["groups"] == {"G": ["m1"]}

    def test_board_round_trip(self):
        svc.save_board("kb", {"columns": ["task", "expense"], "time_window": "tm", "limit": 10})
        data = _read()
        assert data["board.kb"]["columns"] == ["task", "expense"]
        assert data["board.kb"]["time_window"] == "tm"
        assert data["board.kb"]["limit"] == 10

    def test_board_rejects_empty_columns(self):
        with pytest.raises(PTOSError, match="non-empty columns"):
            svc.save_board("kb", {"columns": []})

    def test_habit_round_trip(self):
        svc.save_habit("run", {"filters": ["type=habit name=run"], "weeks": 8, "toggleable": False})
        data = _read()
        assert data["habit.run"]["filters"] == ["type=habit name=run"]
        assert data["habit.run"]["weeks"] == 8
        assert data["habit.run"]["toggleable"] is False

    def test_habit_rejects_empty_filters(self):
        with pytest.raises(PTOSError, match="non-empty filters"):
            svc.save_habit("h", {"filters": []})

    def test_calendar_round_trip(self):
        svc.save_calendar("exp", {"filters": ["type=expense"], "time_window": "tm"})
        data = _read()
        assert data["calendar.exp"]["filters"] == ["type=expense"]
        assert data["calendar.exp"]["time_window"] == "tm"

    def test_calendar_rejects_empty_filters(self):
        with pytest.raises(PTOSError, match="non-empty filters"):
            svc.save_calendar("c", {"filters": []})

    def test_threshold_round_trip(self):
        svc.save_threshold("spend", {"metric": "expenses", "direction": "max", "value": 1000, "unit": "$"})
        data = _read()
        assert data["threshold.spend"]["metric"] == "expenses"
        assert data["threshold.spend"]["direction"] == "max"
        assert data["threshold.spend"]["value"] == 1000
        assert data["threshold.spend"]["unit"] == "$"

    def test_threshold_rejects_empty_metric(self):
        with pytest.raises(PTOSError, match="must have a metric"):
            svc.save_threshold("t", {"metric": ""})

    def test_due_round_trip(self):
        svc.save_due("td", {"type": "todo", "key": "due", "days": 7})
        data = _read()
        assert data["due.td"]["type"] == "todo"
        assert data["due.td"]["days"] == 7

    def test_project_round_trip(self):
        svc.save_project("reno", {"label": "Reno", "todo_project": "reno", "tag_filters": ["home"]})
        data = _read()
        assert data["project.reno"]["label"] == "Reno"
        assert data["project.reno"]["todo_project"] == "reno"
        assert data["project.reno"]["tag_filters"] == ["home"]

    def test_project_rejects_empty_label(self):
        with pytest.raises(PTOSError, match="label is required"):
            svc.save_project("p", {"label": ""})

    def test_alias_round_trip(self):
        svc.save_alias("a1", {"alias": "my_target"})
        data = _read()
        assert data["a1"]["alias"] == "my_target"

    def test_alias_rejects_empty_target(self):
        with pytest.raises(PTOSError, match="target is required"):
            svc.save_alias("a", {"alias": ""})


class TestNewFile:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))

    def test_save_creates_file(self):
        assert not os.path.exists(ptos.QUERIES_PATH)
        svc.save_query_entry("new_q", {"where": "type=task"})
        assert os.path.exists(ptos.QUERIES_PATH)
        data = _read()
        assert data["new_q"]["where"] == "type=task"


class TestPreserveUnknownFields:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))

    def test_query_preserves_unknown_fields(self):
        _write_queries('[my_q]\nwhere = "type=task"\ncustom_key = "preserved"\n')
        svc.save_query_entry("my_q", {"where": "type=task AND tag=x"})
        data = _read()
        assert data["my_q"]["where"] == "type=task AND tag=x"
        assert data["my_q"]["custom_key"] == "preserved"

    def test_board_preserves_unknown_fields(self):
        _write_queries('[board.kb]\ncolumns = ["task"]\ncustom_key = "preserved"\n')
        svc.save_board("kb", {"columns": ["task", "expense"]})
        data = _read()
        assert data["board.kb"]["columns"] == ["task", "expense"]
        assert data["board.kb"]["custom_key"] == "preserved"

    def test_threshold_preserves_unknown_fields(self):
        _write_queries('[threshold.sp]\nmetric = "exp"\ncustom_key = "preserved"\n')
        svc.save_threshold("sp", {"metric": "exp", "direction": "max"})
        data = _read()
        assert data["threshold.sp"]["metric"] == "exp"
        assert data["threshold.sp"]["custom_key"] == "preserved"


class TestDispatchRoute:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        _write_queries(_FULL_TOML)

    def test_save_query_via_route(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/query-builder/query",
                           json={"name": "expenses", "cfg": {"where": "type=task", "time": "tm"},
                                 "action": "save"})
        data = resp.get_json()
        assert data["ok"] is True
        stored = _read()
        assert stored["expenses"]["where"] == "type=task"

    def test_delete_query_via_route(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/query-builder/query",
                           json={"name": "expenses", "action": "delete"})
        data = resp.get_json()
        assert data["ok"] is True
        stored = _read()
        assert "expenses" not in stored

    def test_save_board_via_route(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/query-builder/board",
                           json={"name": "kanban", "cfg": {"columns": ["task"], "time_window": "tm"},
                                 "action": "save"})
        data = resp.get_json()
        assert data["ok"] is True
        stored = _read()
        assert stored["board.kanban"]["time_window"] == "tm"

    def test_delete_board_via_route(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/query-builder/board",
                           json={"name": "kanban", "action": "delete"})
        data = resp.get_json()
        assert data["ok"] is True
        stored = _read()
        assert "board.kanban" not in stored

    def test_unknown_kind_rejected(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/query-builder/foobar",
                           json={"name": "x", "action": "save"})
        data = resp.get_json()
        assert data["ok"] is False
        assert "Unknown kind" in data["error"]

    def test_empty_name_rejected(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/query-builder/query",
                           json={"name": "", "action": "save"})
        data = resp.get_json()
        assert data["ok"] is False

    def test_delete_nonexistent_via_route(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/query-builder/query",
                           json={"name": "nonexistent", "action": "delete"})
        data = resp.get_json()
        assert data["ok"] is False
        assert "not found" in data["error"]
