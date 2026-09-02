import os
import datetime as dt
import tomli_w
import pytest
import ptos
import ptos_cli


def _write_records(lines):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    with open(os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log"),
              "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _add_queries_table(key, cfg):
    queries = ptos.get_queries()
    queries[key] = cfg
    with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
        tomli_w.dump(queries, w.stream)
    ptos._invalidate_all()


def _run(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["ptos"] + list(argv))
    ptos_cli.main()


class TestCliHabitsTime:
    def test_habits_honors_time(self, monkeypatch, capsys):
        _add_queries_table("habit.med", {"filters": ["type=habit", "name=meditation"], "weeks": 4})
        today = dt.date.today()
        _write_records([f"{today} type=habit name=meditation"])
        _run(monkeypatch, "--habits", "med", "--time", "td")
        out = capsys.readouterr().out
        assert "1-day streak" in out
        assert today.strftime("%B %Y") in out
        assert f"- {today.strftime('%b')} {today.day}, {today.year}" in out

    def test_default_still_this_month(self, monkeypatch, capsys):
        _add_queries_table("habit.med", {"filters": ["type=habit", "name=meditation"], "weeks": 4})
        today = dt.date.today()
        _write_records([f"{today} type=habit name=meditation"])
        _run(monkeypatch, "--habits", "med")
        out = capsys.readouterr().out
        assert today.strftime("%B %Y") in out

    def test_missing_name_exits(self, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, "--habits", "nope")
        assert "not found" in str(exc.value.code)


class TestCliCalendars:
    def test_named_calendar_grid(self, monkeypatch, capsys):
        _add_queries_table("calendar.test", {"filters": ["type=expense"]})
        today = dt.date.today()
        _write_records([f"{today} type=expense domain=self category=food amount=1"])
        _run(monkeypatch, "--calendars", "test")
        out = capsys.readouterr().out
        assert "test -" in out
        assert "record(s)" in out
        assert "Mo Tu We Th Fr Sa Su" in out

    def test_no_named_calendars_hint(self, monkeypatch, capsys):
        _run(monkeypatch, "--calendars")
        out = capsys.readouterr().out
        assert "All records" in out
        assert '["calendar.work"]' in out

    def test_missing_name_exits(self, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, "--calendars", "nope")
        assert "not found" in str(exc.value.code)


class TestCliBoard:
    def test_board_columns(self, monkeypatch, capsys):
        _add_queries_table("board.work", {"columns": ["expense"]})
        today = dt.date.today()
        _write_records([f"{today} type=expense domain=self category=food amount=10"])
        _run(monkeypatch, "--board", "work")
        out = capsys.readouterr().out
        assert "Board: work" in out
        assert "expense: 1 record(s)" in out
        assert today.strftime("%d/%m/%Y") in out

    def test_no_boards_hint(self, monkeypatch, capsys):
        _run(monkeypatch, "--board")
        out = capsys.readouterr().out
        assert '["board.work"]' in out

    def test_missing_name_exits(self, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, "--board", "nope")
        assert "not found" in str(exc.value.code)