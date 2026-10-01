"""Permanent regression guard: tests must not depend on the day of the month.

These probe the same code paths that previously broke at a month boundary,
pinning the clock with a FakeDate so the assertions hold on any run date.
"""
import datetime as dt
import glob
import os

import pytest

import ptos


def _fake_date(clock):
    class FakeDate(dt.date):
        @classmethod
        def today(cls):
            return cls(clock.year, clock.month, clock.day)
    return FakeDate


# 2026-10-01 is the date the suite actually broke on: a fixture dated
# 2026-09-05 fell outside the CLI's default this-month window.
MONTH_BOUNDARY_CLOCKS = [
    dt.date(2026, 9, 20),    # same month as the fixture
    dt.date(2026, 10, 1),    # month boundary (the real-world failure)
    dt.date(2026, 12, 31),   # year end
    dt.date(2027, 1, 2),     # year + month boundary
]


@pytest.mark.parametrize("clock", MONTH_BOUNDARY_CLOCKS)
def test_convert_cli_passes_across_month_boundary(monkeypatch, clock):
    """--convert must not lose a record just because the clock moved past it."""
    import ptos_cli

    ptos._CACHE.clear()
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    with open(os.path.join(ptos.RECORDS_DIR, "2026.log"), "w", encoding="utf-8") as f:
        f.write("2026-09-05 type=capture tag=inbox | walked\n")

    monkeypatch.setattr(dt, "date", _fake_date(clock))
    monkeypatch.setattr(
        "sys.argv",
        ["ptos", "--convert", "type=capture", "exercise",
         "--set", "activity=walk", "duration=30",
         "--keep", "--time", "all"],
    )
    monkeypatch.setattr("builtins.input", lambda _: "y")
    ptos_cli.main()

    content = ""
    for path in sorted(glob.glob(os.path.join(ptos.RECORDS_DIR, "*.log"))):
        with open(path, encoding="utf-8") as f:
            content += f.read()
    assert content.count("\n") == 2, content
    assert "type=exercise" in content
    assert "type=capture" in content


@pytest.mark.parametrize("clock", MONTH_BOUNDARY_CLOCKS)
def test_habit_days_done_stable_across_month_boundary(clock):
    """days_done must be derived from an explicit window, not a rolled month."""
    import ptos_service as svc

    ptos._CACHE.clear()
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    today = clock
    days = [today - dt.timedelta(days=i) for i in range(21)]
    # Records live in the log file for their own year, so a clock near New Year
    # spans two files.
    for year in sorted({d.year for d in days}):
        with open(os.path.join(ptos.RECORDS_DIR, f"{year}.log"),
                  "w", encoding="utf-8") as f:
            f.write("\n".join(
                f"{d.isoformat()} type=habit name=meditation"
                for d in days if d.year == year) + "\n")

    import tomli_w

    queries = ptos.get_queries()
    queries["habit.meditation"] = {
        "filters": ["type=habit", "name=meditation"], "weeks": 60,
    }
    with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
        tomli_w.dump(queries, w.stream)
    ptos._invalidate_all()

    real_date = dt.date
    dt.date = _fake_date(today)
    try:
        ptos._CACHE.clear()
        data = svc.get_habit_data("meditation", time="weeks")
    finally:
        dt.date = real_date

    assert data["streak"] == 21
    assert data["days_done"] == 21


@pytest.mark.parametrize("clock", MONTH_BOUNDARY_CLOCKS)
def test_project_month_signals_stable_across_month_boundary(clock):
    """todo_added / todo_done count from the 1st; derive the expectation the same way."""
    import ptos_todo
    import ptos_service as svc

    tmp = ptos.BASE_DIR
    todo_path = os.path.join(tmp, "todo.txt")
    done_path = os.path.join(tmp, "done.txt")
    queries_path = os.path.join(tmp, "queries.toml")

    ptos._CACHE.clear()
    with open(queries_path, "w", encoding="utf-8") as f:
        f.write('["project.myproj"]\nlabel = "My Project"\ntodo_project = "myproj"\n')
    today_s = clock.isoformat()
    yest_s = (clock - dt.timedelta(days=1)).isoformat()
    old_s = (clock - dt.timedelta(days=90)).isoformat()
    with open(todo_path, "w", encoding="utf-8") as f:
        f.write(f"(A) {today_s} Task 1 +myproj due:{yest_s}\n"
                f"(B) {today_s} Task 2 +myproj due:{today_s}\n"
                f"(C) {yest_s} Old task +myproj due:{yest_s}\n"
                f"(A) {today_s} Unrelated task +other due:{today_s}\n")
    with open(done_path, "w", encoding="utf-8") as f:
        f.write(f"x {today_s} {yest_s} Completed +myproj\n"
                f"x {yest_s} {old_s} Old done +myproj\n")

    for mod in (ptos, ptos_todo, svc):
        mod.QUERIES_PATH = queries_path
        mod.TODO_PATH = todo_path
        mod.DONE_PATH = done_path
    ptos._invalidate_all()

    real_date = dt.date
    dt.date = _fake_date(clock)
    try:
        ptos._CACHE.clear()
        result = svc.get_projects_overview()
    finally:
        dt.date = real_date

    assert len(result) == 1
    p = result[0]
    month_start = clock.replace(day=1)
    yest = clock - dt.timedelta(days=1)
    expected_added = sum(1 for d in (clock, clock, yest) if d >= month_start)
    expected_done = sum(1 for d in (clock, yest) if d >= month_start)
    assert p["todo_added"] == expected_added
    assert p["todo_done"] == expected_done
    assert p["todo_delta"] == expected_added - expected_done