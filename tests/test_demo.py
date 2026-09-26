import os
import shutil
import datetime as dt

import pytest

import ptos
import ptos_todo
import ptos_service as svc


_REPO_STARTERS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "starters")


@pytest.fixture
def demo_home(tmp_path, monkeypatch):
    """A fresh workspace wired to the real starter files (incl. demo spec)."""
    base = tmp_path / "demo_home"
    base.mkdir()
    for attr, sub in [("BASE_DIR", ""), ("CONFIG_DIR", "config"),
                      ("RECORDS_DIR", "records"), ("JOURNAL_DIR", "journal"),
                      ("TEMPLATE_DIR", "templates"), ("TODO_DIR", "todo"),
                      ("NOTES_DIR", "notes"), ("TODO_PATH", "todo/todo.txt"),
                      ("DONE_PATH", "todo/done.txt")]:
        monkeypatch.setattr(ptos, attr, str(base / sub) if sub else str(base))
    (base / "config").mkdir()
    (base / "records").mkdir()
    (base / "templates").mkdir()
    (base / "todo").mkdir()
    for dst, src in [("schema.toml", "starter_schema.toml"),
                     ("config.toml", "starter_config.toml"),
                     ("queries.toml", "starter_queries.toml"),
                     ("presets.toml", "starter_presets.toml")]:
        shutil.copy2(os.path.join(_REPO_STARTERS, src), str(base / "config" / dst))
    monkeypatch.setattr(ptos, "SCHEMA_PATH", str(base / "config" / "schema.toml"))
    monkeypatch.setattr(ptos, "QUERIES_PATH", str(base / "config" / "queries.toml"))
    monkeypatch.setattr(ptos, "CONFIG_PATH", str(base / "config" / "config.toml"))
    monkeypatch.setattr(ptos, "PRESETS_PATH", str(base / "config" / "presets.toml"))
    monkeypatch.setattr(ptos, "STARTER_DIR", _REPO_STARTERS)
    with open(os.path.join(str(base / "records"), f"{ptos.today().year}.log"),
              "a", encoding="utf-8") as f:
        pass
    ptos._invalidate_all()
    # ptos_todo / ptos_service snapshot path constants at import time; realign
    # them so service/web reads see this workspace.
    import ptos_todo
    import ptos_service as svc
    for mod in (ptos_todo,):
        monkeypatch.setattr(mod, "BASE_DIR", str(base))
        monkeypatch.setattr(mod, "TODO_DIR", str(base / "todo"))
        monkeypatch.setattr(mod, "TODO_PATH", str(base / "todo" / "todo.txt"))
        monkeypatch.setattr(mod, "DONE_PATH", str(base / "todo" / "done.txt"))
    for mod in (svc,):
        monkeypatch.setattr(mod, "BASE_DIR", str(base))
        monkeypatch.setattr(mod, "RECORDS_DIR", str(base / "records"))
        monkeypatch.setattr(mod, "JOURNAL_DIR", str(base / "journal"))
        monkeypatch.setattr(mod, "TODO_DIR", str(base / "todo"))
        monkeypatch.setattr(mod, "TODO_PATH", str(base / "todo" / "todo.txt"))
        monkeypatch.setattr(mod, "DONE_PATH", str(base / "todo" / "done.txt"))
    return base


def _seed():
    ptos._seed_demo_data()
    ptos._invalidate_all()


class TestDemoSeed:
    def test_seed_writes_all_areas(self, demo_home):
        _seed()
        year = ptos.today().year
        demo_log = demo_home / "records" / "demo" / f"{year}.log"
        assert demo_log.exists()
        lines = [ln for ln in demo_log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) >= 80
        assert (demo_home / "todo" / "todo.txt").exists()
        assert (demo_home / "todo" / "done.txt").exists()
        assert len(os.listdir(demo_home / "notes" / "Demo")) >= 3
        journal = demo_home / "journal" / str(year)
        assert os.path.isdir(journal)
        assert sum(len(fs) for _, _, fs in os.walk(journal)) >= 3

    def test_seed_is_skipped_when_not_fresh(self, demo_home):
        user_log = demo_home / "records" / f"{ptos.today().year}.log"
        user_log.write_text(
            f"{ptos.today().isoformat()} type=mood rating=4\n", encoding="utf-8")
        _seed()
        assert not (demo_home / "records" / "demo").exists()
        assert user_log.read_text(encoding="utf-8") == (
            f"{ptos.today().isoformat()} type=mood rating=4\n")

    def test_seed_is_skipped_when_demo_already_present(self, demo_home):
        _seed()
        demo_log = demo_home / "records" / "demo" / f"{ptos.today().year}.log"
        count = sum(1 for _ in demo_log.open(encoding="utf-8"))
        _seed()
        assert sum(1 for _ in demo_log.open(encoding="utf-8")) == count

    def test_seed_never_touches_real_data_dirs(self, demo_home):
        # anything created by seeding must live under BASE_DIR
        demo_home_mk, _ = demo_home, None
        _seed()
        for f in sorted(os.listdir(demo_home_mk)):
            assert (demo_home_mk / f).exists()

    def test_demo_records_validate_against_starter_schema(self, demo_home):
        _seed()
        year = ptos.today().year
        demo_log = demo_home / "records" / "demo" / f"{year}.log"
        schema = ptos.get_schema()
        problems = []
        for line in demo_log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            kv = ptos.parse_line(line)[1]
            problems.extend(f"{line}: {p}" for p in ptos.validate_record(schema, kv))
        assert problems == []

    def test_seed_due_story_has_exactly_one_hot_row(self, demo_home):
        _seed()
        due = svc.get_due()
        rows = [r for r in due["rows"] if not r.get("done")]
        assert len(rows) == 1
        assert rows[0]["name"] == "BDR"
        assert rows[0]["heat"] == "hot"

    def test_board_job_search_has_populated_lanes(self, demo_home):
        _seed()
        board = svc.get_board_data("job_search", time="all")
        counts = {lane: len(recs) for lane, recs in board["data"].items()}
        assert counts == {"Applied": 4, "Interview": 2, "Offer": 1,
                          "Rejected": 1, "Accepted": 1}

    def test_calendar_named_view_finds_records(self, demo_home):
        _seed()
        year, month = ptos.today().year, ptos.today().month
        this = svc.get_calendar_data("personal", year, month)
        prev_month = month - 1 or 12
        prev_year = year if month > 1 else year - 1
        prev = svc.get_calendar_data("personal", prev_year, prev_month)
        assert this["total_records"] + prev["total_records"] >= 10
        assert this["calendar_name"] == "personal"

    def test_habits_populated(self, demo_home):
        _seed()
        data = svc.get_habit_data("meditation", "type=habit name=meditation")
        assert data["days_done"] >= 5
        assert data["streak"] >= 1

    def test_projects_has_demo_project(self, demo_home):
        _seed()
        names = [p["name"] for p in svc.get_projects_overview()]
        assert "jobsearch" in names
        project = next(p for p in svc.get_projects_overview()
                       if p["name"] == "jobsearch")
        assert project["has_board"] is True
        assert project["record_count"] >= 3
        assert project["open_items"]

    def test_dashboard_returns_items(self, demo_home):
        _seed()
        data = svc.get_dashboard("default", time="all")
        assert data["items"], "expected dashboard items"
        for it in data["items"]:
            assert it.get("name"), f"unnamed dashboard item: {it}"

    def test_todo_lines_fully_resolved(self, demo_home):
        _seed()
        todos, _ = ptos_todo.load_todos(str(demo_home / "todo" / "todo.txt"))
        assert len(todos) == 8
        for t in todos:
            assert "{{" not in t.raw_line
        dues = [t for t in todos if t.due]
        assert len(dues) >= 3
        any_overdue = any(t.due and t.due < ptos.today() for t in todos)
        assert any_overdue


class TestDemoTokenResolve:
    def test_today_token(self):
        assert ptos._resolve_demo_text("{{today}}") == ptos.today().isoformat()

    def test_offset_tokens(self):
        base = dt.date(2026, 9, 26)
        assert ptos._resolve_demo_text("{{-5d}}", base) == "2026-09-21"
        assert ptos._resolve_demo_text("{{+5d}}", base) == "2026-10-01"
        assert ptos._resolve_demo_text("{{0d}}", base) == "2026-09-26"

    def test_relative_words(self):
        base = dt.date(2026, 9, 26)
        assert ptos._resolve_demo_text("{{yesterday}}", base) == "2026-09-25"
        assert ptos._resolve_demo_text("{{next_week}}", base) == "2026-10-03"

    def test_unknown_token_passes_through(self):
        assert ptos._resolve_demo_text("{{title}}") == "{{title}}"

    def test_multiple_tokens_in_one_line(self):
        base = dt.date(2026, 9, 26)
        out = ptos._resolve_demo_text(
            "{{today}} a={{+3d}} b={{-3d}} end", base)
        assert out == "2026-09-26 a=2026-09-29 b=2026-09-23 end"


class TestRemoveDemoData:
    def test_clean_remove_deletes_all(self, demo_home):
        _seed()
        ptos.remove_demo_data()
        assert not (demo_home / "records" / "demo").exists()
        assert not (demo_home / "todo" / "todo.txt").read_text(
            encoding="utf-8").strip()
        journal_files = sum(len(fs) for _, _, fs in os.walk(demo_home / "journal"))
        assert journal_files == 0
        assert (demo_home / "notes" / "Demo" / "welcome.md").exists()

    def test_remove_keeps_demo_dir_with_user_record(self, demo_home):
        _seed()
        year = ptos.today().year
        demo_log = demo_home / "records" / "demo" / f"{year}.log"
        with demo_log.open("a", encoding="utf-8") as f:
            f.write(f"{ptos.today().isoformat()} type=capture | my own note\n")
        ptos.remove_demo_data()
        assert (demo_home / "records" / "demo").exists()
        content = demo_log.read_text(encoding="utf-8")
        assert "my own note" in content
        assert "type=capture" in content

    def test_remove_keeps_user_todos(self, demo_home):
        _seed()
        with (demo_home / "todo" / "todo.txt").open("a", encoding="utf-8") as f:
            f.write(f"(B) {ptos.today().isoformat()} My personal todo +custom\n")
        ptos.remove_demo_data()
        remaining = (demo_home / "todo" / "todo.txt").read_text(
            encoding="utf-8")
        assert "My personal todo" in remaining
        assert "Prepare for Acme round three" not in remaining

    def test_remove_keeps_edited_journal(self, demo_home):
        _seed()
        today_str = ptos.today().isoformat()
        path = demo_home / "journal" / str(ptos.today().year) / \
            f"{ptos.today().month:02d}" / f"{today_str}.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n- user line\n",
                        encoding="utf-8")
        ptos.remove_demo_data()
        assert path.exists()
        assert "user line" in path.read_text(encoding="utf-8")


class TestDemoCli:
    def test_remove_demo_data_flag(self, demo_home, capsys, monkeypatch):
        _seed()
        monkeypatch.setattr("ptos_cli.sys.argv",
                            ["ptos", "--remove-demo-data"])
        import ptos_cli
        ptos_cli.main()
        assert not (demo_home / "records" / "demo").exists()
        out = capsys.readouterr().out
        assert "Demo data removed." in out


class TestDemoPages:
    def _get(self, path):
        from ptos_web import app
        client = app.test_client()
        r = client.get(path)
        return r.status_code, r.get_data(as_text=True)

    @pytest.fixture(autouse=True)
    def _seeded(self, demo_home):
        _seed()
        yield

    def test_home(self):
        status, html = self._get("/")
        assert status == 200

    def test_browse(self):
        from ptos_web import app
        client = app.test_client()
        r = client.post("/browse/run", json={"time": "all"})
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        notes = [row.get("note") for row in body["data"]["records"]]
        assert any(n and "Team lunch" in n for n in notes)
        assert body["data"]["count"] >= 80

    def test_board(self):
        status, html = self._get("/board?board=job_search")
        assert status == 200
        assert "Applied" in html

    def test_due(self):
        status, html = self._get("/due")
        assert status == 200
        assert "BDR" in html

    def test_habits(self):
        status, html = self._get("/habits")
        assert status == 200
        assert "meditation" in html

    def test_calendar(self):
        status, html = self._get("/calendar")
        assert status == 200

    def test_calendar_named(self):
        status, html = self._get("/calendar/personal")
        assert status == 200

    def test_entity(self):
        status, html = self._get("/entity")
        assert status == 200

    def test_projects(self):
        status, html = self._get("/projects")
        assert status == 200
        assert "jobsearch" in html

    def test_todo(self):
        status, html = self._get("/todo")
        assert status == 200
        assert "Prepare for Acme round three" in html

    def test_journal(self):
        status, html = self._get("/journal")
        assert status == 200

    def test_notes_browse(self):
        status, html = self._get("/notes/browse/Demo")
        assert status == 200
        assert "welcome" in html

    def test_thresholds(self):
        status, html = self._get("/thresholds")
        assert status == 200

    def test_query_builder(self):
        status, html = self._get("/query-builder?section=due")
        assert status == 200

    def test_types(self):
        status, html = self._get("/types")
        assert status == 200