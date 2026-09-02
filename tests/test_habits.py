import os
import datetime as dt
import tomli_w
import ptos
import ptos_cli
import ptos_service as svc
import pytest


def _write_records(lines):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    with open(os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log"),
              "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _add_habit(name, filters, weeks=12):
    queries = ptos.get_queries()
    queries[f"habit.{name}"] = {"filters": filters, "weeks": weeks}
    with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
        tomli_w.dump(queries, w.stream)
    ptos._invalidate_all()


def _clean_cache():
    ptos._CACHE.clear()


class TestHabitStreak:
    def test_three_consecutive_days(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=4)
        today = dt.date.today()
        lines = [
            f"{(today - dt.timedelta(days=2))} type=habit name=meditation",
            f"{(today - dt.timedelta(days=1))} type=habit name=meditation",
            f"{today} type=habit name=meditation",
        ]
        _write_records(lines)
        data = svc.get_habit_data("med")
        assert data["streak"] == 3

    def test_gap_breaks_streak(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=4)
        today = dt.date.today()
        lines = [
            f"{(today - dt.timedelta(days=2))} type=habit name=meditation",
            f"{today} type=habit name=meditation",
        ]
        _write_records(lines)
        data = svc.get_habit_data("med")
        assert data["streak"] == 1

    def test_today_missing_counts_through_yesterday(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=4)
        today = dt.date.today()
        lines = [
            f"{(today - dt.timedelta(days=2))} type=habit name=meditation",
            f"{(today - dt.timedelta(days=1))} type=habit name=meditation",
        ]
        _write_records(lines)
        data = svc.get_habit_data("med")
        assert data["streak"] == 2

    def test_double_log_still_one_present(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=4)
        today = dt.date.today()
        _write_records([
            f"{today} type=habit name=meditation tag=morning",
            f"{today} type=habit name=meditation tag=evening",
        ])
        data = svc.get_habit_data("med")
        assert data["streak"] == 1
        present_days = [g for g in data["grid"] if g["present"]]
        assert len(present_days) == 1
        assert present_days[0]["date"] == str(today)

    def test_streak_independent_of_display_window(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=60)
        today = dt.date.today()
        lines = [(today - dt.timedelta(days=i)).isoformat() for i in range(21)]
        _write_records([f"{d} type=habit name=meditation" for d in lines])
        data = svc.get_habit_data("med")
        assert data["streak"] == 21
        grid_start = dt.date.fromisoformat(data["grid"][0]["date"])
        assert data["days_done"] == (today - grid_start).days + 1
        assert len(data["months"]) == 1

    def test_unconfigured_habit_raises(self):
        _clean_cache()
        with pytest.raises(svc.PTOSError):
            svc.get_habit_data("does_not_exist")


class TestHabitDataBasics:
    def test_days_done_and_total(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=2)
        today = dt.date.today()
        _write_records([
            f"{today} type=habit name=meditation",
            f"{(today - dt.timedelta(days=3))} type=habit name=meditation",
        ])
        data = svc.get_habit_data("med", time="weeks")
        monday = today - dt.timedelta(days=today.weekday())
        start = monday - dt.timedelta(days=(2 - 1) * 7)
        assert data["grid"][0]["date"] == str(start)
        assert data["total_days"] == (today - start).days + 1
        assert data["days_done"] == 2
        assert len(data["grid"]) == data["total_days"]

    def test_habit_names_lists_configured(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"])
        _add_habit("walk", ["type=habit", "name=walk"])
        names = svc.get_habit_names()
        assert "med" in names
        assert "walk" in names


class TestHabitCaching:
    def test_append_record_invalidates(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=4)
        today = dt.date.today()
        _write_records([f"{today} type=habit name=meditation"])
        data = svc.get_habit_data("med")
        assert data["streak"] == 1
        assert any(k.startswith("habit:med") for k in ptos._CACHE)
        svc.append_record(f"{today} type=habit name=meditation tag=second")
        assert not any(k.startswith("habit:med") for k in ptos._CACHE)
        data2 = svc.get_habit_data("med")
        assert data2["streak"] == 1

    def test_second_call_no_rescan(self, monkeypatch):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=4)
        today = dt.date.today()
        _write_records([f"{today} type=habit name=meditation"])
        calls = []
        original = ptos.find_records_with_location
        def counting(*a, **kw):
            calls.append(a)
            return original(*a, **kw)
        monkeypatch.setattr(ptos, "find_records_with_location", counting)
        first = svc.get_habit_data("med")
        n_after_first = len(calls)
        second = svc.get_habit_data("med")
        assert len(calls) == n_after_first
        assert first == second


class TestHabitWindow:
    def test_grid_monday_aligned(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=4)
        today = dt.date.today()
        _write_records([])
        data = svc.get_habit_data("med")
        first = dt.date.fromisoformat(data["grid"][0]["date"])
        assert first.weekday() == 0
        assert data["total_days"] == len(data["grid"])
        assert (data["total_days"] - 1) % 7 == today.weekday()

    def test_is_today_flag(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=4)
        today = dt.date.today()
        _write_records([f"{today} type=habit name=meditation"])
        data = svc.get_habit_data("med")
        today_cells = [g for g in data["grid"] if g["is_today"]]
        assert len(today_cells) == 1
        assert today_cells[0]["date"] == str(today)
        assert today_cells[0]["present"]

    def test_month_labels_first_matches_grid_start(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=30)
        _write_records([])
        data = svc.get_habit_data("med")
        labels = data["month_labels"]
        assert labels
        first = dt.date.fromisoformat(data["grid"][0]["date"])
        assert labels[0]["column"] == 0
        assert labels[0]["label"] == first.strftime("%b")
        cols = [m["column"] for m in labels]
        assert cols == sorted(cols)

    def test_multi_month_labels_columns_increasing(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=30)
        _write_records([])
        data = svc.get_habit_data("med", time="weeks")
        cols = [m["column"] for m in data["month_labels"]]
        assert len(cols) >= 2
        for a, b in zip(cols, cols[1:]):
            assert b > a

    def test_time_this_month(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=30)
        today = dt.date.today()
        _write_records([f"{today} type=habit name=meditation"])
        data = svc.get_habit_data("med", time="tm")
        start = dt.date(today.year, today.month, 1)
        first = dt.date.fromisoformat(data["grid"][0]["date"])
        assert first <= start
        assert dt.date.fromisoformat(data["grid"][-1]["date"]) == today
        assert first.weekday() == 0
        assert data["total_days"] == (today - first).days + 1
        assert data["range_label"].startswith(dt.date.today().strftime("%b"))

    def test_default_window_is_this_month(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=30)
        today = dt.date.today()
        _write_records([])
        data = svc.get_habit_data("med")
        assert len(data["months"]) == 1
        assert data["months"][0]["name"] == today.strftime("%B %Y")
        assert dt.date.fromisoformat(data["grid"][-1]["date"]) == today

    def test_weeks_code_uses_per_habit_window(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=30)
        today = dt.date.today()
        _write_records([])
        data = svc.get_habit_data("med", time="weeks")
        monday = today - dt.timedelta(days=today.weekday())
        start = monday - dt.timedelta(days=(30 - 1) * 7)
        assert dt.date.fromisoformat(data["grid"][0]["date"]) == start
        assert len(data["months"]) >= 2

    def test_range_window(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=12)
        today = dt.date.today()
        from_d = today - dt.timedelta(days=20)
        _write_records([f"{today} type=habit name=meditation"])
        data = svc.get_habit_data("med", from_date=from_d.isoformat(),
                                 to_date=today.isoformat())
        first = dt.date.fromisoformat(data["grid"][0]["date"])
        assert first.weekday() == 0
        assert (from_d - first).days in range(7)
        assert dt.date.fromisoformat(data["grid"][-1]["date"]) == today
        assert data["days_done"] == 1

    def test_past_window_no_today(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=12)
        today = dt.date.today()
        _write_records([f"{today} type=habit name=meditation"])
        data = svc.get_habit_data("med", time="lm")
        assert not any(g["is_today"] for g in data["grid"])
        assert dt.date.fromisoformat(data["grid"][-1]["date"]) < today
        assert data["days_done"] == 0

    def test_all_time_caps_window(self):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=12)
        _write_records([])
        data = svc.get_habit_data("med", time="all")
        assert data["total_days"] <= 260 * 7
        assert dt.date.fromisoformat(data["grid"][-1]["date"]) == dt.date.today()


class TestHabitMonths:
    def _data(self, days=30):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=12)
        today = dt.date.today()
        lines = [(today - dt.timedelta(days=i)).isoformat()
                 for i in range(0, days, 2)]
        _write_records([f"{d} type=habit name=meditation" for d in lines])
        return svc.get_habit_data("med")

    def test_months_blocks_present(self):
        data = self._data()
        assert data["months"]
        for m in data["months"]:
            assert m["name"]
            assert any(c["date"] for c in m["days"])

    def test_month_leading_blanks_align_first_day(self):
        data = self._data()
        for m in data["months"]:
            leading = 0
            for c in m["days"]:
                if c["date"] is None:
                    leading += 1
                else:
                    break
            first = dt.date.fromisoformat(
                next(c["date"] for c in m["days"] if c["date"]))
            # every block aligns its first real day under its weekday (Monday=0)
            assert leading == first.weekday()

    def test_months_weeks_padded_to_multiple_of_7(self):
        data = self._data()
        for m in data["months"]:
            assert len(m["days"]) % 7 == 0

    def test_months_last_is_current_month_with_today(self):
        data = self._data()
        today = dt.date.today()
        assert data["months"][-1]["name"] == today.strftime("%B %Y")
        today_cells = [c for c in data["months"][-1]["days"] if c["date"] == str(today)]
        assert len(today_cells) == 1
        assert today_cells[0]["is_today"]


class TestHabitCli:
    def test_run_habits_prints_calendar(self, capsys):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=2)
        today = dt.date.today()
        _write_records([f"{today} type=habit name=meditation"])
        ptos_cli.run_habits("__ALL__")
        out = capsys.readouterr().out
        assert "med" in out
        assert "day streak" in out
        assert today.strftime("%B %Y") in out
        assert "M T W T F S S" in out
        assert "#" in out
        assert "^" in out

    def test_run_habits_named_filters(self, capsys):
        _clean_cache()
        _add_habit("med", ["type=habit", "name=meditation"], weeks=2)
        _add_habit("walk", ["type=habit", "name=walk"], weeks=2)
        today = dt.date.today()
        _write_records([f"{today} type=habit name=meditation"])
        ptos_cli.run_habits("med")
        out = capsys.readouterr().out
        assert "med" in out
        assert "walk" not in out

    def test_run_habits_missing_name_exits(self):
        _clean_cache()
        with pytest.raises(SystemExit):
            ptos_cli.run_habits("nope")

    def test_run_habits_no_habits_hint(self, capsys):
        _clean_cache()
        with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
            tomli_w.dump({}, w.stream)
        ptos._invalidate_all()
        ptos_cli.run_habits("__ALL__")
        out = capsys.readouterr().out
        assert '["habit.meditation"]' in out
