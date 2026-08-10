import os
import datetime as dt
import tomli_w
import ptos
import ptos_service as svc
import pytest


def _write_records(lines):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    with open(os.path.join(ptos.RECORDS_DIR, "2026.log"), "w", encoding="utf-8") as f:
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
        data = svc.get_habit_data("med")
        assert data["days_done"] == 2
        assert data["total_days"] == 15
        assert len(data["grid"]) == 15

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
        assert f"habit:med" in ptos._CACHE
        svc.append_record(f"{today} type=habit name=meditation tag=second")
        assert f"habit:med" not in ptos._CACHE
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
