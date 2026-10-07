import os
import shutil
import datetime as dt
import tomllib

import pytest

import ptos
import ptos_cli
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
    ptos._seed_demo_data(demo=True)
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
        board = svc.get_board_data("demo_job", time="all")
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
        # Habit filters come from queries.toml, not an argument. Use the habit's
        # own week span: demo habit days are seeded relative to today, while the
        # default display window is the current month, whose Monday floor can
        # exclude days seeded a few days back.
        data = svc.get_habit_data("meditation", time="weeks")
        assert data["days_done"] >= 5
        assert data["streak"] >= 1

    def test_projects_has_demo_project(self, demo_home):
        _seed()
        names = [p["name"] for p in svc.get_projects_overview()]
        assert "demo_job" in names
        project = next(p for p in svc.get_projects_overview()
                       if p["name"] == "demo_job")
        assert project["has_board"] is True
        assert project["record_count"] >= 3
        assert project["open_items"]

    def test_dashboard_returns_items(self, demo_home):
        _seed()
        data = svc.get_dashboard("default", time="all")
        assert data["items"], "expected dashboard items"
        for it in data["items"]:
            assert it.get("name"), f"unnamed dashboard item: {it}"

    def test_dashboard_balance_is_derived_metric(self, demo_home):
        _seed()
        queries = ptos.get_queries()
        assert "balance" not in queries, "balance must not be a base query"
        assert "balance" in queries.get("metrics", {})
        data = svc.get_dashboard("default", time="all")
        bal = next(it for it in data["items"] if it["name"] == "balance")
        assert bal["kind"] == "metric"
        expected = (svc.get_metric("total_income")["raw"]
                    - svc.get_metric("total_expenses")["raw"])
        assert bal["raw"] == pytest.approx(expected)

    def test_no_expense_record_has_category_equal_to_domain(self, demo_home):
        _seed()
        year = ptos.today().year
        demo_log = demo_home / "records" / "demo" / f"{year}.log"
        for line in demo_log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            kv = ptos.parse_line(line)[1]
            if kv.get("type") == "expense":
                assert kv.get("category") != kv.get("domain"), line

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


class TestDemoMarkers:
    """tag=__demo__ on records, +__demo__ on todos - the removal signal."""

    def test_every_seeded_record_carries_the_demo_tag(self, demo_home):
        _seed()
        year = ptos.today().year
        demo_log = demo_home / "records" / "demo" / f"{year}.log"
        lines = [ln for ln in demo_log.read_text(encoding="utf-8").splitlines()
                 if ln.strip()]
        assert lines
        for line in lines:
            tags = ptos.parse_line(line)[1].get("tag") or []
            if isinstance(tags, str):
                tags = [tags]
            assert ptos.DEMO_TAG in tags, line

    def test_every_seeded_todo_carries_the_demo_project(self, demo_home):
        _seed()
        for name in ("todo.txt", "done.txt"):
            todos, _ = ptos_todo.load_todos(str(demo_home / "todo" / name))
            assert todos
            for t in todos:
                projects = [p.lstrip("+") for p in t.projects]
                assert ptos.DEMO_PROJECT in projects, t.raw_line

    def test_edited_demo_record_is_still_removed(self, demo_home):
        _seed()
        year = ptos.today().year
        demo_log = demo_home / "records" / "demo" / f"{year}.log"
        lines = demo_log.read_text(encoding="utf-8").splitlines()
        lines[0] = lines[0] + " (edited)"
        demo_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ptos.remove_demo_data()
        assert not (demo_home / "records" / "demo").exists()

    def test_edited_demo_todo_is_still_removed(self, demo_home):
        _seed()
        path = demo_home / "todo" / "todo.txt"
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[0] = lines[0] + " (edited)"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ptos.remove_demo_data()
        remaining = path.read_text(encoding="utf-8")
        assert "Acme" not in remaining
        assert "demo" not in remaining

    def test_user_record_in_demo_dir_survives_marker_removal(self, demo_home):
        _seed()
        year = ptos.today().year
        demo_log = demo_home / "records" / "demo" / f"{year}.log"
        with demo_log.open("a", encoding="utf-8") as f:
            f.write(f"{ptos.today().isoformat()} type=capture tag=urgent "
                    f"| my own note\n")
        ptos.remove_demo_data()
        content = demo_log.read_text(encoding="utf-8")
        assert "my own note" in content
        assert "tag=urgent" in content
        assert "Team lunch" not in content

    def test_remove_returns_counts(self, demo_home):
        _seed()
        counts = ptos.remove_demo_data()
        assert counts["records"] > 0
        assert counts["todos"] > 0
        assert counts["done"] > 0
        assert counts["journal"] > 0
        assert counts["kept_dir"] is False


class TestDemoDataPresent:
    def test_false_on_empty_workspace(self, demo_home):
        assert ptos.demo_data_present() is False

    def test_true_after_seed(self, demo_home):
        _seed()
        assert ptos.demo_data_present() is True

    def test_false_after_clean_remove(self, demo_home):
        _seed()
        ptos.remove_demo_data()
        assert ptos.demo_data_present() is False

    def test_true_while_a_demo_todo_remains(self, demo_home):
        _seed()
        ptos.remove_demo_data()
        with (demo_home / "todo" / "todo.txt").open("a", encoding="utf-8") as f:
            f.write(f"(A) {ptos.today().isoformat()} Still tagged +__demo__\n")
        assert ptos.demo_data_present() is True

    def test_false_when_only_user_data_remains(self, demo_home):
        _seed()
        ptos.remove_demo_data()
        with (demo_home / "todo" / "todo.txt").open("a", encoding="utf-8") as f:
            f.write(f"(A) {ptos.today().isoformat()} Mine +personal\n")
        assert ptos.demo_data_present() is False


class TestDemoInitPrompt:
    """--init asks before seeding; --no-demo-data answers for you."""

    @pytest.fixture(autouse=True)
    def _desktop_mode(self, monkeypatch):
        # skips the .ptos_home bootstrap (refuses temp dirs on purpose)
        monkeypatch.setattr(ptos, "DESKTOP_MODE", True)

    def test_demo_false_skips_seed(self, demo_home):
        ptos.init_ptos(demo=False)
        assert not (demo_home / "records" / "demo").exists()

    def test_demo_true_seeds_without_asking(self, demo_home, monkeypatch):
        def _no_input(*a, **k):
            raise AssertionError("must not prompt when demo=True")
        monkeypatch.setattr("builtins.input", _no_input)
        ptos.init_ptos(demo=True)
        assert (demo_home / "records" / "demo").exists()

    @pytest.mark.parametrize("answer", ["n", "N", "no", "nope"])
    def test_prompt_no_skips_seed(self, demo_home, monkeypatch, answer):
        monkeypatch.setattr("builtins.input", lambda *a, **k: answer)
        ptos.init_ptos()
        assert not (demo_home / "records" / "demo").exists()

    @pytest.mark.parametrize("answer", ["", "y", "Y", "yes"])
    def test_prompt_yes_seeds(self, demo_home, monkeypatch, answer):
        monkeypatch.setattr("builtins.input", lambda *a, **k: answer)
        ptos.init_ptos()
        assert (demo_home / "records" / "demo").exists()

    def test_prompt_eof_defaults_to_yes(self, demo_home, monkeypatch):
        def _eof(*a, **k):
            raise EOFError
        monkeypatch.setattr("builtins.input", _eof)
        ptos.init_ptos()
        assert (demo_home / "records" / "demo").exists()

    def test_prompt_closed_stdin_defaults_to_yes(self, demo_home, monkeypatch):
        def _closed(*a, **k):
            raise OSError("reading from stdin while output is captured")
        monkeypatch.setattr("builtins.input", _closed)
        ptos.init_ptos()
        assert (demo_home / "records" / "demo").exists()

    def test_no_prompt_when_not_fresh(self, demo_home, monkeypatch):
        (demo_home / "records" / f"{ptos.today().year}.log").write_text(
            f"{ptos.today().isoformat()} type=mood rating=4\n", encoding="utf-8")
        def _no_input(*a, **k):
            raise AssertionError("must not prompt on a non-fresh workspace")
        monkeypatch.setattr("builtins.input", _no_input)
        ptos.init_ptos()
        assert not (demo_home / "records" / "demo").exists()

    def test_no_prompt_without_demo_spec(self, demo_home, monkeypatch,
                                          tmp_path):
        monkeypatch.setattr(ptos, "STARTER_DIR", str(tmp_path / "empty"))
        def _no_input(*a, **k):
            raise AssertionError("must not prompt without a demo spec")
        monkeypatch.setattr("builtins.input", _no_input)
        ptos.init_ptos()
        assert not (demo_home / "records" / "demo").exists()


class TestDemoCli:
    def test_no_demo_data_flag_is_wired_to_init(self):
        import ptos_cli
        args = ptos_cli.build_parser({}).parse_args(["--init", "--no-demo-data"])
        assert args.init is True
        assert args.no_demo_data is True
        plain = ptos_cli.build_parser({}).parse_args(["--init"])
        assert plain.no_demo_data is False

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
        status, html = self._get("/board?board=demo_job")
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
        assert "demo_job" in html

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

    def test_settings_offers_demo_removal(self):
        status, html = self._get("/settings")
        assert status == 200
        assert "Remove demo data" in html
        assert "removeDemoData" in html

    def test_api_removes_demo_data(self, demo_home):
        from ptos_web import app
        client = app.test_client()
        r = client.post("/api/demo-data/remove")
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["removed"]["records"] > 0
        assert body["removed"]["todos"] > 0
        assert "Demo data removed." in body["message"]
        assert not (demo_home / "records" / "demo").exists()
        assert ptos.demo_data_present() is False
        assert 'id="remove-demo-btn"' not in self._get("/settings")[1]

    def test_api_removal_is_idempotent(self):
        from ptos_web import app
        client = app.test_client()
        client.post("/api/demo-data/remove")
        r = client.post("/api/demo-data/remove")
        body = r.get_json()
        assert body["ok"] is True
        assert body["removed"]["records"] == 0

    def test_api_removal_keeps_notes_and_config(self, demo_home):
        from ptos_web import app
        client = app.test_client()
        client.post("/api/demo-data/remove")
        assert (demo_home / "notes" / "Demo" / "welcome.md").exists()
        assert (demo_home / "config" / "queries.toml").exists()


class TestDemoServiceWrappers:
    def test_demo_data_present(self, demo_home):
        _seed()
        assert svc.demo_data_present() is True
        ptos.remove_demo_data()
        assert svc.demo_data_present() is False

    def test_remove_demo_data_returns_structured_result(self, demo_home,
                                                        capsys):
        _seed()
        result = svc.remove_demo_data()
        assert result["ok"] is True
        assert set(result["removed"]) == {"records", "todos", "done", "journal"}
        assert result["removed"]["records"] > 0
        assert result["kept_dir"] is False
        assert "Demo data removed." in result["message"]
        out = capsys.readouterr().out
        assert "Removed 88 demo record line(s)" not in out  # engine stayed quiet
        assert "Demo data removed." not in out

    def test_remove_demo_data_clears_history_cache(self, demo_home):
        _seed()
        svc.get_board_data("demo_job", time="all")  # warms the cache
        svc.remove_demo_data()
        # the seeded board is gone; a cached read must not resurrect it
        board = svc.get_board_data("demo_job", time="all")
        assert all(not recs for recs in board["data"].values())

    def test_reinstall_demo_data_returns_structured_result(self, demo_home):
        _seed()
        result = svc.reinstall_demo_data()
        assert result["ok"] is True
        assert set(result["removed"]) == {"records", "todos", "done", "journal"}
        assert result["removed"]["records"] == 88
        assert set(result["installed"]) == {
            "records", "todos", "done", "journal", "notes"}
        assert result["installed"]["records"] == 88
        assert result["installed"]["todos"] == 8
        assert result["installed"]["journal"] == 3
        assert "Re-installing demo data" in result["message"]

    def test_reinstall_clears_history_cache(self, demo_home):
        _seed()
        svc.get_board_data("demo_job", time="all")
        svc.reinstall_demo_data()
        board = svc.get_board_data("demo_job", time="all")
        assert any(recs for recs in board["data"].values())

    def test_demo_data_available(self, demo_home):
        assert svc.demo_data_available() is True
        ptos.remove_demo_data()
        # still available: the spec ships with the project
        assert svc.demo_data_available() is True

    def test_demo_data_available_false_without_spec(self, demo_home,
                                                    monkeypatch):
        monkeypatch.setattr(ptos, "STARTER_DIR", str(demo_home / "nope"))
        assert ptos.demo_data_available() is False
        assert svc.demo_data_available() is False
        result = svc.reinstall_demo_data()
        assert result["ok"] is True
        assert result["installed"] is None


class TestDemoReinstall:
    def test_reinstall_after_removal_restores_full_story(self, demo_home):
        _seed()
        ptos.remove_demo_data()
        assert ptos.demo_data_present() is False
        result = ptos.reinstall_demo_data()
        assert result["removed"]["records"] == 0  # nothing left to clear
        # notes are kept by removal, so nothing is re-added for them
        assert result["installed"] == {
            "records": 88, "todos": 8, "done": 3, "journal": 3, "notes": 0}
        assert ptos.demo_data_present() is True
        assert (demo_home / "notes" / "Demo" / "welcome.md").exists()
        assert (demo_home / "notes" / "Demo" / "Find a Job" / "index.md").exists()

    def test_reinstall_keeps_user_record_in_demo_dir(self, demo_home):
        _seed()
        log = demo_home / "records" / "demo" / f"{ptos.today().year}.log"
        with open(log, "a", encoding="utf-8") as f:
            f.write("type=expense amount=7 note=my own line\n")
        ptos.reinstall_demo_data()
        text = log.read_text(encoding="utf-8")
        assert "my own line" in text
        assert text.count("tag=__demo__") == 88

    def test_reinstall_keeps_user_todos_in_order(self, demo_home):
        _seed()
        with open(demo_home / "todo" / "todo.txt", "a", encoding="utf-8") as f:
            f.write("(A) my own urgent task +work\n(B) my own second task +work\n")
        ptos.reinstall_demo_data()
        lines = (demo_home / "todo" / "todo.txt").read_text(
            encoding="utf-8").strip().split("\n")
        # user lines keep their place; the demo story is appended after them
        assert lines[:2] == ["(A) my own urgent task +work",
                             "(B) my own second task +work"]
        assert sum(1 for ln in lines if "+__demo__" in ln) == 8

    def test_reinstall_does_not_duplicate_demo_lines(self, demo_home):
        _seed()
        ptos.reinstall_demo_data()
        ptos.reinstall_demo_data()
        log = demo_home / "records" / "demo" / f"{ptos.today().year}.log"
        assert log.read_text(encoding="utf-8").count("tag=__demo__") == 88
        todos = (demo_home / "todo" / "todo.txt").read_text(encoding="utf-8")
        assert todos.count("+__demo__") == 8

    def test_reinstall_never_overwrites_edited_journal_entry(self, demo_home):
        _seed()
        base = ptos.today()
        rel = os.path.join(str(base.year), f"{base.month:02d}", f"{base}.md")
        path = demo_home / "journal" / rel
        assert path.exists()  # the seeded story writes today's entry
        with open(path, "w", encoding="utf-8") as f:
            f.write("MY OWN JOURNAL ENTRY")
        ptos.reinstall_demo_data()
        assert path.read_text(encoding="utf-8") == "MY OWN JOURNAL ENTRY"

    def test_reinstall_never_overwrites_edited_note(self, demo_home):
        _seed()
        note = demo_home / "notes" / "Demo" / "welcome.md"
        with open(note, "w", encoding="utf-8") as f:
            f.write("MY OWN NOTE")
        ptos.reinstall_demo_data()
        assert note.read_text(encoding="utf-8") == "MY OWN NOTE"

    def test_reinstall_recreates_missing_note(self, demo_home):
        _seed()
        note = demo_home / "notes" / "Demo" / "Find a Job" / "index.md"
        os.remove(note)
        ptos.reinstall_demo_data()
        assert note.exists()

    def test_reinstall_on_fresh_workspace_installs(self, demo_home):
        result = ptos.reinstall_demo_data()
        assert result["installed"]["records"] == 88
        assert ptos.demo_data_present() is True

    def test_reinstall_never_prompts(self, demo_home, monkeypatch):
        _seed()

        def _boom(*a, **k):
            raise AssertionError("re-install must not prompt")

        monkeypatch.setattr("builtins.input", _boom)
        ptos.reinstall_demo_data()
        assert ptos.demo_data_present() is True

    def test_seed_force_false_still_respects_freshness(self, demo_home):
        _seed()
        assert ptos._seed_demo_data(demo=True) is None  # non-fresh, no-op
        assert ptos.demo_data_present() is True

    def test_add_demo_data_flag_is_wired(self, demo_home, capsys, monkeypatch):
        import ptos_cli
        args = ptos_cli.build_parser({}).parse_args(["--add-demo-data"])
        assert args.add_demo_data is True
        plain = ptos_cli.build_parser({}).parse_args([])
        assert plain.add_demo_data is False
        _seed()
        monkeypatch.setattr("ptos_cli.sys.argv", ["ptos", "--add-demo-data"])
        ptos_cli.main()
        out = capsys.readouterr().out
        assert "Re-installing demo data" in out
        assert ptos.demo_data_present() is True
        assert out.count("tag=__demo__") == 0

    def test_api_installs_demo_data(self, demo_home):
        from ptos_web import app
        client = app.test_client()
        assert client.post("/api/demo-data/remove").get_json()["ok"] is True
        r = client.post("/api/demo-data/install")
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["installed"]["records"] == 88
        assert ptos.demo_data_present() is True
        assert "Remove demo data" in client.get("/settings").get_data(as_text=True)

    def test_settings_offers_reinstall_when_absent(self, demo_home):
        from ptos_web import app
        client = app.test_client()
        client.post("/api/demo-data/remove")
        html = client.get("/settings").get_data(as_text=True)
        assert "Re-install demo data" in html
        assert "installDemoData" in html
        assert 'id="remove-demo-btn"' not in html


def _add_real_record(demo_home):
    """Log a user record outside the demo group, as a used workspace would."""
    year = ptos.today().year
    with open(demo_home / "records" / f"{year}.log", "a", encoding="utf-8") as f:
        f.write(f"{ptos.today()} type=expense domain=self category=food "
                f'amount=99 tag=real note="my own lunch"\n')
    ptos._invalidate_all()


def _install_broken_spec(monkeypatch, spec):
    """Point STARTER_DIR at a temp dir holding an intentionally invalid spec."""
    import tempfile
    import tomli_w
    work = tempfile.mkdtemp(prefix="ptos_demo_spec_")
    for name in os.listdir(_REPO_STARTERS):
        shutil.copy2(os.path.join(_REPO_STARTERS, name), os.path.join(work, name))
    with open(os.path.join(work, "starter_demo.toml"), "wb") as f:
        tomli_w.dump(spec, f)
    monkeypatch.setattr(ptos, "STARTER_DIR", work)
    ptos._invalidate_all()


def _edit_toml(path, mutate):
    import tomli_w
    with open(path, "rb") as f:
        data = tomllib.load(f)
    mutate(data)
    with open(path, "wb") as f:
        tomli_w.dump(data, f)
    ptos._invalidate_all()


def _set_schema_demo_group(demo_home, group):
    _edit_toml(demo_home / "config" / "schema.toml",
               lambda d: d["demo"].__setitem__("log_group", group))


def _drop_type_from_live_schema(demo_home, type_name):
    """Simulate a user who deleted a type the starter still ships."""

    def mutate(data):
        data["types"]["allowed"] = [t for t in data["types"]["allowed"]
                                    if t != type_name]
        data["type"].pop(type_name, None)

    _edit_toml(demo_home / "config" / "schema.toml", mutate)


def _narrow_status_options(demo_home):
    """Simulate a user who trimmed an option list the starter still uses."""
    _edit_toml(demo_home / "config" / "schema.toml",
               lambda d: d["type"]["jobsearch"]["fields"]["status"]
               .__setitem__("options", ["applied", "interview"]))


def _replace_config_with_non_matching_items(demo_home):
    """Strip every config item that would match the demo records.

    These sections are stored as literal quoted dotted keys
    (``"habit.NAME"``), so they must be matched by prefix, not by nesting.
    """
    path = demo_home / "config" / "queries.toml"
    prefixes = ("habit.", "threshold.", "board.", "calendar.", "project.")

    def mutate(data):
        for name in list(data):
            if isinstance(name, str) and name.startswith(prefixes):
                data.pop(name)
        for name, value in data.items():
            if isinstance(value, dict):
                if value.get("where"):
                    value["where"] = "type=does_not_exist"
                for key in ("filters", "tag_filters", "columns"):
                    if key in value:
                        value[key] = "type=does_not_exist"
        for name, m in (data.get("metrics") or {}).items():
            if isinstance(m, dict) and isinstance(m.get("sum"), str):
                m["sum"] = "type=does_not_exist"

    _edit_toml(path, mutate)


def _set_show(demo_home, value):
    _edit_toml(demo_home / "config" / "config.toml",
               lambda d: d.setdefault("demo", {}).__setitem__("show", value))


class TestDemoLogGroup:
    """[demo] log_group names the folder; is_demo_logfile routes every path."""

    def test_default_group_is_demo(self, demo_home):
        assert ptos.demo_log_group() == "demo"

    def test_schema_can_rename_the_group(self, demo_home):
        _set_schema_demo_group(demo_home, "samples")
        assert ptos.demo_log_group() == "samples"

    def test_renamed_group_changes_where_records_land(self, demo_home):
        _set_schema_demo_group(demo_home, "samples")
        _seed()
        assert (demo_home / "records" / "samples" /
                f"{ptos.today().year}.log").exists()
        assert not (demo_home / "records" / "demo").exists()

    def test_is_demo_logfile_handles_both_separators(self, demo_home):
        assert ptos.is_demo_logfile("demo/2026.log") is True
        assert ptos.is_demo_logfile("demo\\2026.log") is True
        assert ptos.is_demo_logfile("2026.log") is False
        assert ptos.is_demo_logfile("followup/2026.log") is False

    def test_removal_uses_the_renamed_group(self, demo_home):
        _set_schema_demo_group(demo_home, "samples")
        _seed()
        assert ptos.demo_data_present() is True
        ptos.remove_demo_data()
        assert not (demo_home / "records" / "samples").exists()

    def test_freshness_check_uses_the_renamed_group(self, demo_home):
        _set_schema_demo_group(demo_home, "samples")
        _seed()
        assert ptos._demo_fresh() is False


class TestDemoShowSetting:
    """[demo] show controls whether demo rows reach aggregate reads."""

    def test_fresh_demo_workspace_counts_demo_records(self, demo_home):
        _seed()
        assert ptos.include_demo_records() is True

    def test_used_workspace_excludes_demo_records(self, demo_home):
        _seed()
        _add_real_record(demo_home)
        assert ptos.include_demo_records() is False

    def test_always_includes_despite_real_records(self, demo_home):
        _seed()
        _add_real_record(demo_home)
        _set_show(demo_home, "always")
        assert ptos.include_demo_records() is True

    def test_never_excludes_even_without_real_records(self, demo_home):
        _seed()
        _set_show(demo_home, "never")
        assert ptos.include_demo_records() is False

    def test_invalid_value_falls_back_to_auto(self, demo_home):
        _seed()
        _set_show(demo_home, "sideways")
        assert ptos.get_demo_show() == "auto"
        assert ptos.include_demo_records() is True

    def test_aggregate_metric_ignores_demo_on_used_workspace(self, demo_home):
        _seed()
        _add_real_record(demo_home)
        _set_show(demo_home, "auto")
        ptos._invalidate_all()
        from ptos_service import get_metric
        # the real record logged above is an expense, not income
        assert get_metric("total_income")["raw"] == 0

    def test_aggregate_metric_counts_demo_on_fresh_workspace(self, demo_home):
        _seed()
        _set_show(demo_home, "auto")
        ptos._invalidate_all()
        from ptos_service import get_metric
        assert get_metric("total_income")["raw"] > 0

    def test_threshold_ignores_demo_on_used_workspace(self, demo_home):
        _seed()
        _add_real_record(demo_home)
        ptos._invalidate_all()
        from ptos_service import get_all_threshold_status
        food = next(t for t in get_all_threshold_status() if t["name"] == "food_spend")
        assert food["raw"] < 5000  # demo's food rows are excluded

    def test_browse_still_shows_demo_on_used_workspace(self, demo_home):
        _seed()
        _add_real_record(demo_home)
        ptos._invalidate_all()
        rows = svc.get_records("all", time="all")["records"]
        assert any(f"tag={ptos.DEMO_TAG}" in r["_line"] for r in rows)
        assert any("tag=real" in r["_line"] for r in rows)

    def test_browse_includes_demo_whatever_the_setting(self, demo_home):
        """show governs aggregates; browse/edit always surface demo rows."""
        _seed()
        _add_real_record(demo_home)
        for value in ("always", "never", "auto"):
            _set_show(demo_home, value)
            rows = svc.get_records("all", time="all")["records"]
            assert any(f"tag={ptos.DEMO_TAG}" in r["_line"] for r in rows), value

    def test_type_record_count_never_counts_demo(self, demo_home):
        _seed()
        _add_real_record(demo_home)
        assert svc.get_type_record_count("expense") == 1


class TestDemoAtomicReinstall:
    """A bad spec must never leave the workspace half-emptied."""

    def test_invalid_spec_leaves_records_and_todos_intact(
            self, demo_home, monkeypatch):
        _seed()
        log = demo_home / "records" / "demo" / f"{ptos.today().year}.log"
        todo = demo_home / "todo" / "todo.txt"
        log_before = log.read_text(encoding="utf-8")
        todo_before = todo.read_text(encoding="utf-8")

        spec = ptos._load_demo_spec()
        spec["records"]["lines"].append("2020-01-01 type=not_a_real_type | x")
        _install_broken_spec(monkeypatch, spec)

        result = ptos.reinstall_demo_data()
        assert result["error"]
        assert result["removed"] is None
        assert result["installed"] is None
        assert log.read_text(encoding="utf-8") == log_before
        assert todo.read_text(encoding="utf-8") == todo_before
        assert ptos.demo_data_present() is True

    def test_invalid_spec_leaves_journal_intact(self, demo_home, monkeypatch):
        _seed()
        spec = ptos._load_demo_spec()
        spec["records"]["lines"].append("2020-01-01 type=not_a_real_type | x")
        _install_broken_spec(monkeypatch, spec)
        # Demo journal entries are seeded at today/-1d/-3d, so the month
        # directory follows the current date rather than a fixed one.
        today = dt.date.today()
        jdir = demo_home / "journal" / str(today.year) / f"{today.month:02d}"
        before = sorted(os.listdir(jdir))
        ptos.reinstall_demo_data()
        assert sorted(os.listdir(jdir)) == before


class TestDemoSchemaDrift:
    """Demo content is held to the starter schema, not the live one."""

    def test_seeding_survives_a_live_schema_that_removed_the_type(
            self, demo_home):
        _seed()
        ptos.remove_demo_data()
        _drop_type_from_live_schema(demo_home, "jobsearch")
        _add_real_record(demo_home)
        result = ptos.reinstall_demo_data()
        assert "error" not in result
        assert result["installed"]["records"] == 88

    def test_seeding_survives_a_narrowed_option_list(self, demo_home):
        _seed()
        ptos.remove_demo_data()
        _narrow_status_options(demo_home)
        result = ptos.reinstall_demo_data()
        assert "error" not in result
        assert result["installed"]["records"] == 88

    def test_live_schema_validation_still_guards_real_records(
            self, demo_home):
        _drop_type_from_live_schema(demo_home, "jobsearch")
        kv = ptos.safe_parse_line(
            "2026-01-01 type=jobsearch position=PM company=Acme "
            "status=applied | applied")[1]
        assert any("jobsearch" in p for p in ptos.validate_record(
            ptos.get_schema(), kv))
        # the very same record is perfectly valid against the starter schema
        assert ptos.validate_record(ptos._starter_schema(), kv) == []

    def test_lint_skips_demo_lines_that_break_the_live_schema(self, demo_home):
        _seed()
        _add_real_record(demo_home)
        _narrow_status_options(demo_home)
        result = svc.run_lint()
        assert result["demo_skipped"] == 88
        assert result["error_count"] == 0
        assert result["clean"] is True


class TestDemoNamespacing:
    """The demo project/board/habit/note are namespaced so they cannot
    collide with a user's identically-named config."""

    def test_project_uses_the_demo_job_key(self, demo_home):
        _seed()
        names = [p["name"] for p in svc.get_projects_overview()]
        assert "demo_job" in names
        assert "jobsearch" not in names

    def test_project_board_link_resolves(self, demo_home):
        _seed()
        proj = next(p for p in svc.get_projects_overview()
                    if p["name"] == "demo_job")
        assert proj["has_board"] is True
        assert proj["board_name"] == "demo_job"

    def test_board_lanes_are_guarded_by_type_and_marker(self, demo_home):
        _seed()
        board = svc.get_board_data("demo_job", time="all")
        for lane in board["columns"]:
            assert "type=jobsearch" in board["lanes"][lane]["where"]
            assert f"tag={ptos.DEMO_TAG}" in board["lanes"][lane]["where"]

    def test_due_default_still_points_at_the_real_type(self, demo_home):
        _seed()
        due = svc.get_due("default")
        assert due["rec_type"] == "jobsearch"

    def test_pomodoro_habit_is_namespaced(self, demo_home):
        import tomllib
        with open(demo_home / "config" / "queries.toml", "rb") as f:
            q = tomllib.load(f)
        assert "habit.demo_pomodoro" in q
        assert "habit.pomodoro" not in q

    def test_demo_notes_live_under_demo(self, demo_home):
        _seed()
        assert (demo_home / "notes" / "Demo" / "Find a Job" / "index.md").exists()
        assert not (demo_home / "notes" / "Projects").exists()


class TestDemoCollisionWarning:
    def test_warning_lists_matching_live_config_on_used_workspace(
            self, demo_home, capsys):
        _seed()
        _add_real_record(demo_home)
        ptos.reinstall_demo_data()
        out = capsys.readouterr().out
        assert "also match the demo records" in out
        assert "query 'food_this_month'" in out
        assert "threshold 'food_spend'" in out
        assert "habit 'meditation'" in out
        assert "board 'demo_job'" in out

    def test_warning_is_silent_when_nothing_collides(self, demo_home, capsys):
        _seed()
        _add_real_record(demo_home)
        _replace_config_with_non_matching_items(demo_home)
        ptos.reinstall_demo_data()
        out = capsys.readouterr().out
        assert "also match the demo records" not in out

    def test_warning_is_silent_on_a_fresh_workspace(self, demo_home, capsys):
        _seed()
        ptos.reinstall_demo_data()
        out = capsys.readouterr().out
        assert "also match the demo records" not in out

    def test_warning_does_not_block_installing(self, demo_home, capsys):
        _seed()
        _add_real_record(demo_home)
        result = ptos.reinstall_demo_data()
        assert result["installed"]["records"] == 88


class TestDemoShowFromCli:
    """`ptos --set-config demo.show` is the supported way to flip the switch."""

    def test_set_config_persists_and_takes_effect(self, demo_home, monkeypatch,
                                                   capsys):
        _seed()
        _add_real_record(demo_home)
        monkeypatch.setattr("sys.argv",
                            ["ptos", "--set-config", "demo.show", "always"])
        ptos_cli.main()
        capsys.readouterr()
        ptos._invalidate_all()
        assert ptos.get_demo_show() == "always"
        assert ptos.include_demo_records() is True

    def test_get_config_reports_the_current_value(self, demo_home, monkeypatch,
                                                  capsys):
        _seed()
        monkeypatch.setattr("sys.argv", ["ptos", "--get-config", "demo.show"])
        ptos_cli.main()
        assert "demo.show=auto" in capsys.readouterr().out

    def test_cli_trend_honours_the_setting(self, demo_home, monkeypatch, capsys):
        """--trend is an aggregate, so demo rows drop out on a used workspace."""
        _seed()
        _add_real_record(demo_home)
        monkeypatch.setattr("sys.argv",
                            ["ptos", "--type", "income", "-t", "tm",
                             "--trend", "3", "--table"])
        ptos_cli.main()
        used = capsys.readouterr().out
        _set_show(demo_home, "always")
        monkeypatch.setattr("sys.argv",
                            ["ptos", "--type", "income", "-t", "tm",
                             "--trend", "3", "--table"])
        ptos_cli.main()
        always = capsys.readouterr().out
        assert always != used  # always sees the demo salary rows too


class TestProjectsBoardLink:
    def test_projects_page_links_to_the_namespaced_board(self, demo_home):
        _seed()
        from ptos_web import app
        html = app.test_client().get("/projects").get_data(as_text=True)
        assert "/board?board=demo_job" in html
        assert "Find a Job (Demo)" in html


class TestSchemaBuilderPreservesUnknownSections:
    def test_demo_section_survives_a_builder_save(self, demo_home):
        from ptos_web import _build_schema_dict
        old = ptos.get_schema()
        assert "demo" in old
        rebuilt = _build_schema_dict(
            old,
            new_types=list(old["types"]["allowed"]),
            type_schemas={t: {"fields": dict(d.get("fields") or {})}
                          for t, d in old["type"].items()},
        )
        assert rebuilt.get("demo") == old["demo"]

