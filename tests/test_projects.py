"""
tests/test_projects.py  —  Tests for the Project Drift Review page
"""

import datetime as dt, os, pytest, textwrap
import ptos
import ptos_todo
import ptos_service as svc
from ptos_web import app


TODAY = dt.date.today()
TODAY_S = TODAY.isoformat()
YESTERDAY = (TODAY - dt.timedelta(days=1)).isoformat()
TOMORROW = (TODAY + dt.timedelta(days=1)).isoformat()
MONTH_AGO = (TODAY - dt.timedelta(days=30)).isoformat()
OLD = (TODAY - dt.timedelta(days=90)).isoformat()


@pytest.fixture(autouse=True)
def _clear_cache():
    ptos._CACHE.clear()


def _write_todo(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _write_queries(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content))


def _write_record(path, line):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


class TestGetProjects:
    def test_empty_queries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        result = ptos.get_projects()
        assert result == {}

    def test_reads_project_sections(self, tmp_path, monkeypatch):
        qpath = tmp_path / "queries.toml"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(qpath))
        _write_queries(qpath, '''
            ["project.jobsearch"]
            label = "Find a Job"
            todo_project = "jobsearch"

            ["project.reno"]
            label = "Renovate House"
        ''')
        result = ptos.get_projects()
        assert "jobsearch" in result
        assert "reno" in result
        assert result["jobsearch"]["label"] == "Find a Job"
        assert result["jobsearch"]["todo_project"] == "jobsearch"

    def test_ignores_non_project_sections(self, tmp_path, monkeypatch):
        qpath = tmp_path / "queries.toml"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(qpath))
        _write_queries(qpath, '''
            ["habit.meditation"]
            filters = ["type=habit"]

            ["project.jobsearch"]
            label = "Find a Job"

            [my_query]
            where = "type=expense"
        ''')
        result = ptos.get_projects()
        assert len(result) == 1
        assert "jobsearch" in result


class TestProjectsOverview:
    def test_empty_when_no_projects(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(tmp_path / "done.txt"))
        monkeypatch.setattr(svc, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(svc, "DONE_PATH", str(tmp_path / "done.txt"))
        _write_todo(tmp_path / "todo.txt", [])
        _write_todo(tmp_path / "done.txt", [])
        result = svc.get_projects_overview()
        assert result == []

    def test_todo_project_signals(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.myproj"]
            label = "My Project"
            todo_project = "myproj"
        ''')
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Task 1 +myproj due:{TOMORROW}",
            f"(B) {TODAY_S} Task 2 +myproj due:{TODAY_S}",
            f"(C) {YESTERDAY} Old task +myproj due:{YESTERDAY}",
            f"(A) {TODAY_S} Unrelated task +other due:{TODAY_S}",
        ])
        _write_todo(done_path, [
            f"x {TODAY_S} {YESTERDAY} Completed +myproj",
            f"x {YESTERDAY} {OLD} Old done +myproj",
        ])
        result = svc.get_projects_overview()
        assert len(result) == 1
        p = result[0]
        assert p["label"] == "My Project"
        assert p["open_todos"] == 3
        assert p["done_todos"] == 2
        assert p["overdue_todos"] == 1
        assert p["todo_added"] == 3
        assert p["todo_done"] == 2
        assert p["todo_delta"] == 1

    def test_staleness_from_records(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.expenses"]
            label = "Home Reno"
            tag_filters = ["project=reno"]
        ''')
        _write_todo(todo_path, [])
        _write_todo(done_path, [])
        # Create a record with project=reno
        record = f"{TODAY_S} type=expense project=reno amount=50 | paint"
        _write_record(os.path.join(str(tmp_path), "records", "2026.log"), record)
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        result = svc.get_projects_overview()
        assert len(result) == 1
        p = result[0]
        assert p["label"] == "Home Reno"
        assert p["record_count"] == 1
        assert p["stale_days"] == 0
        assert p["heat"] == "cool"

    def test_heat_tiers(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_todo(todo_path, [])
        _write_todo(done_path, [])

        # Cool: activity within 7 days
        _write_queries(tmp_path / "queries.toml", '''
            ["project.cool"]
            label = "Cool"
            todo_project = "cool"
        ''')
        _write_todo(todo_path, [f"(A) {TODAY_S} Task +cool due:{TODAY_S}"])
        result = svc.get_projects_overview()
        assert len(result) == 1
        assert result[0]["heat"] == "cool"

    def test_drift_stalled(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.stale"]
            label = "Stale Project"
            todo_project = "stale"
            tag_filters = ["project=old"]
        ''')
        _write_todo(todo_path, [f"(A) {OLD} Old task +stale due:{TODAY_S}"])
        _write_todo(done_path, [])
        # Record from 90 days ago
        record = f"{OLD} type=expense project=old amount=10 | old expense"
        _write_record(os.path.join(str(tmp_path), "records", "2026.log"), record)
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        result = svc.get_projects_overview()
        assert len(result) == 1
        p = result[0]
        assert p["drift"] == "stalled"
        assert p["stale_days"] > 60

    def test_notes_ref_scan(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        notes_dir = tmp_path / "notes"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos, "NOTES_DIR", str(notes_dir))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.proj1"]
            label = "Find a Job"
            todo_project = "proj1"
        ''')
        _write_todo(todo_path, [])
        _write_todo(done_path, [])
        notes_dir.mkdir(parents=True, exist_ok=True)
        (notes_dir / "job-hunt.md").write_text("# Job Hunt\nMeeting [[Find a Job]] next week\n", encoding="utf-8")
        result = svc.get_projects_overview()
        assert len(result) == 1
        p = result[0]
        assert len(p["notes"]) == 1
        assert "job-hunt.md" in p["notes"][0]["path"]

    def test_sort_by_staleness(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.fresh"]
            label = "Fresh"
            todo_project = "fresh"

            ["project.old"]
            label = "Old"
            todo_project = "old"
        ''')
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Fresh task +fresh due:{TODAY_S}",
            f"(A) {OLD} Old task +old due:{TODAY_S}",
        ])
        _write_todo(done_path, [])
        result = svc.get_projects_overview()
        assert len(result) == 2
        assert result[0]["label"] == "Old"
        assert result[1]["label"] == "Fresh"

    def test_todo_delta_positive(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.proj"]
            label = "Project"
            todo_project = "proj"
        ''')
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Task 1 +proj due:{TODAY_S}",
            f"(A) {TODAY_S} Task 2 +proj due:{TODAY_S}",
            f"(A) {TODAY_S} Task 3 +proj due:{TODAY_S}",
        ])
        _write_todo(done_path, [
            f"x {TODAY_S} {TODAY_S} Done 1 +proj",
        ])
        result = svc.get_projects_overview()
        p = result[0]
        assert p["todo_added"] == 3
        assert p["todo_done"] == 1
        assert p["todo_delta"] == 2

    def test_todo_delta_zero(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.proj"]
            label = "Project"
            todo_project = "proj"
        ''')
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Task 1 +proj due:{TODAY_S}",
        ])
        _write_todo(done_path, [
            f"x {TODAY_S} {TODAY_S} Done 1 +proj",
        ])
        result = svc.get_projects_overview()
        p = result[0]
        assert p["todo_added"] == 1
        assert p["todo_done"] == 1
        assert p["todo_delta"] == 0

    def test_notes_path_mtime(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        notes_dir = tmp_path / "notes"
        proj_notes = notes_dir / "Find a Job"
        proj_notes.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos, "NOTES_DIR", str(notes_dir))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.jobsearch"]
            label = "Find a Job"
            todo_project = "jobsearch"
            notes_path = "Find a Job"
        ''')
        _write_todo(todo_path, [])
        _write_todo(done_path, [])
        # Create a file so the folder has an mtime
        (proj_notes / "notes.md").write_text("Meeting notes", encoding="utf-8")
        result = svc.get_projects_overview()
        assert len(result) == 1
        p = result[0]
        assert p["stale_days"] == 0

    def test_drift_stale(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_todo(todo_path, [])
        _write_todo(done_path, [])

        stale_date = (TODAY - dt.timedelta(days=45)).isoformat()
        _write_queries(tmp_path / "queries.toml", '''
            ["project.stale"]
            label = "Stale"
            tag_filters = ["project=stale"]
        ''')
        record = f"{stale_date} type=expense project=stale amount=10 | old"
        _write_record(os.path.join(str(tmp_path), "records", "2026.log"), record)
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        result = svc.get_projects_overview()
        p = result[0]
        assert p["drift"] == "stale"
        assert 30 < p["stale_days"] <= 60

    def test_drift_ok(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_todo(todo_path, [])
        _write_todo(done_path, [])
        _write_queries(tmp_path / "queries.toml", '''
            ["project.ok"]
            label = "OK Project"
            tag_filters = ["project=ok"]
        ''')
        record = f"{TODAY_S} type=expense project=ok amount=10 | today"
        _write_record(os.path.join(str(tmp_path), "records", "2026.log"), record)
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        result = svc.get_projects_overview()
        p = result[0]
        assert p["drift"] == "ok"
        assert p["heat"] == "cool"


class TestProjectsPage:
    def test_empty_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(tmp_path / "done.txt"))
        monkeypatch.setattr(svc, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(svc, "DONE_PATH", str(tmp_path / "done.txt"))
        _write_todo(tmp_path / "todo.txt", [])
        _write_todo(tmp_path / "done.txt", [])
        client = app.test_client()
        resp = client.get("/projects")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "No projects configured" in html

    def test_shows_project_cards(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.jobsearch"]
            label = "Find a Job"
            todo_project = "jobsearch"
        ''')
        _write_todo(todo_path, [f"(A) {TODAY_S} Apply +jobsearch due:{TODAY_S}"])
        _write_todo(done_path, [f"x {TODAY_S} {TODAY_S} Resume updated +jobsearch"])
        client = app.test_client()
        resp = client.get("/projects")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Find a Job" in html
        assert "1 project(s)" in html

    def test_nav_entry(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(tmp_path / "done.txt"))
        monkeypatch.setattr(svc, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(svc, "DONE_PATH", str(tmp_path / "done.txt"))
        _write_todo(tmp_path / "todo.txt", [])
        _write_todo(tmp_path / "done.txt", [])
        client = app.test_client()
        resp = client.get("/")
        html = resp.get_data(as_text=True)
        assert "projects" in html.lower()


class TestProjectsInlineData:
    def test_open_todos_shown(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.p1"]
            label = "Project One"
            todo_project = "p1"
        ''')
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Apply online +p1 due:{TODAY_S}",
            f"(B) {TODAY_S} Update resume +p1 due:{TOMORROW}",
        ])
        _write_todo(done_path, [])
        client = app.test_client()
        resp = client.get("/projects")
        html = resp.get_data(as_text=True)
        assert "Apply online" in html
        assert "Update resume" in html
        assert "Todos" in html

    def test_done_todos_shown(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.p1"]
            label = "Project One"
            todo_project = "p1"
        ''')
        _write_todo(todo_path, [])
        _write_todo(done_path, [
            f"x {TODAY_S} {YESTERDAY} Sent application +p1",
        ])
        client = app.test_client()
        resp = client.get("/projects")
        html = resp.get_data(as_text=True)
        assert "Sent application" in html
        assert "Done" in html

    def test_records_shown(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.exp"]
            label = "Expenses"
            tag_filters = ["project=reno"]
        ''')
        _write_todo(todo_path, [])
        _write_todo(done_path, [])
        record = f"{TODAY_S} type=expense project=reno amount=50 | paint supplies"
        _write_record(os.path.join(str(tmp_path), "records", "2026.log"), record)
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        client = app.test_client()
        resp = client.get("/projects")
        html = resp.get_data(as_text=True)
        assert "Records" in html
        assert "paint supplies" in html

    def test_notes_shown(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        notes_dir = tmp_path / "notes"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos, "NOTES_DIR", str(notes_dir))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.p1"]
            label = "My Project"
            todo_project = "p1"
        ''')
        _write_todo(todo_path, [])
        _write_todo(done_path, [])
        notes_dir.mkdir(parents=True, exist_ok=True)
        (notes_dir / "notes.md").write_text("some content", encoding="utf-8")
        (notes_dir / "meeting.md").write_text("Meeting about [[My Project]] next week", encoding="utf-8")
        client = app.test_client()
        resp = client.get("/projects")
        html = resp.get_data(as_text=True)
        assert "Notes" in html
        assert "meeting.md" in html

    def test_journal_shown(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        journal_dir = tmp_path / "journal"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos, "JOURNAL_DIR", str(journal_dir))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.p1"]
            label = "My Project"
            todo_project = "p1"
        ''')
        _write_todo(todo_path, [])
        _write_todo(done_path, [])
        journal_dir.mkdir(parents=True, exist_ok=True)
        (journal_dir / "2026-09-15.md").write_text("Working on [[My Project]] today\n", encoding="utf-8")
        client = app.test_client()
        resp = client.get("/projects")
        html = resp.get_data(as_text=True)
        assert "Journal" in html
        assert "2026-09-15.md" in html

    def test_collapsible_sections_exist(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.p1"]
            label = "Project One"
            todo_project = "p1"
        ''')
        _write_todo(todo_path, [f"(A) {TODAY_S} Task +p1 due:{TODAY_S}"])
        _write_todo(done_path, [f"x {TODAY_S} {TODAY_S} Done task +p1"])
        client = app.test_client()
        resp = client.get("/projects")
        html = resp.get_data(as_text=True)
        assert "<details" in html
        assert "proj-section" in html

    def test_todo_due_badge_overdue(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.p1"]
            label = "Project"
            todo_project = "p1"
        ''')
        _write_todo(todo_path, [f"(A) {OLD} Overdue task +p1 due:{YESTERDAY}"])
        _write_todo(done_path, [])
        client = app.test_client()
        resp = client.get("/projects")
        html = resp.get_data(as_text=True)
        assert "overdue" in html.lower()

    def test_no_items_no_sections(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_queries(tmp_path / "queries.toml", '''
            ["project.p1"]
            label = "Empty Project"
            todo_project = "p1"
        ''')
        _write_todo(todo_path, [])
        _write_todo(done_path, [])
        client = app.test_client()
        resp = client.get("/projects")
        html = resp.get_data(as_text=True)
        assert "<details" not in html
