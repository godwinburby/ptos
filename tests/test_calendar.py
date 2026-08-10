import os
import calendar as _cal
import datetime as dt
import tomli_w
import ptos
import ptos_service as svc
import pytest


def _write_records(year, lines):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    with open(os.path.join(ptos.RECORDS_DIR, f"{year}.log"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _add_calendar(name, filters, time_window="this-month"):
    queries = ptos.get_queries()
    queries[f"calendar.{name}"] = {"filters": filters, "time_window": time_window}
    with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
        tomli_w.dump(queries, w.stream)
    ptos._invalidate_all()


def _clean_cache():
    ptos._CACHE.clear()


class TestCalendarGrid:
    def test_records_land_in_correct_day_cell(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        _write_records(2026, [
            "2026-03-05 type=expense amount=100",
            "2026-03-21 type=expense amount=200",
        ])
        data = svc.get_calendar_data("exp", 2026, 3)
        cells = [c for w in data["weeks"] for c in w if c]
        by_day = {c["day"]: c for c in cells}
        assert by_day[5]["count"] == 1
        assert by_day[21]["count"] == 1
        assert by_day[5]["records"][0]["title"] == "(expense)"
        assert by_day[21]["records"][0]["note"] == ""

    def test_outside_month_record_excluded(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        _write_records(2026, [
            "2026-03-05 type=expense amount=100",
            "2026-04-05 type=expense amount=999",
        ])
        data = svc.get_calendar_data("exp", 2026, 3)
        cells = [c for w in data["weeks"] for c in w if c]
        by_day = {c["day"]: c for c in cells}
        assert by_day[5]["count"] == 1
        assert data["total_records"] == 1

    def test_leading_and_trailing_blanks(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        _write_records(2026, ["2026-03-05 type=expense"])
        data = svc.get_calendar_data("exp", 2026, 3)
        first_weekday, days_in_month = _cal.monthrange(2026, 3)
        flattened = [c for w in data["weeks"] for c in w]
        assert len(flattened) % 7 == 0
        day_cells = [c for c in flattened if c]
        assert day_cells[0]["day"] == 1
        assert len(day_cells) == days_in_month
        none_count = sum(1 for c in flattened if c is None)
        assert none_count == first_weekday + (7 - (first_weekday + days_in_month) % 7) % 7

    def test_day_one_in_correct_weekday_column(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        _write_records(2026, ["2026-03-01 type=expense"])
        data = svc.get_calendar_data("exp", 2026, 3)
        first_weekday = _cal.monthrange(2026, 3)[0]
        assert data["weeks"][0][:first_weekday] == [None] * first_weekday
        assert data["weeks"][0][first_weekday]["day"] == 1

    def test_empty_month_still_multiple_of_seven(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        _write_records(2026, [])
        data = svc.get_calendar_data("exp", 2026, 2)
        flattened = [c for w in data["weeks"] for c in w]
        assert len(flattened) % 7 == 0
        assert data["total_records"] == 0


class TestAllRecordsCalendar:
    def test_all_records_includes_every_type_without_config(self):
        _clean_cache()
        _write_records(2026, [
            "2026-03-05 type=expense amount=100",
            "2026-03-05 type=prescription fit=binaural",
            "2026-03-21 type=habit name=exercise",
        ])
        data = svc.get_calendar_data("__all__", 2026, 3)
        assert data["total_records"] == 3
        cells = [c for w in data["weeks"] for c in w if c]
        by_day = {c["day"]: c for c in cells}
        assert by_day[5]["count"] == 2
        assert by_day[21]["count"] == 1
        assert data["filters"] == []

    def test_all_records_does_not_need_config_entry(self):
        _clean_cache()
        _write_records(2026, ["2026-03-05 type=expense"])
        data = svc.get_calendar_data("__all__", 2026, 3)
        assert data["total_records"] == 1
        assert data["calendar_name"] == "__all__"

    def test_all_records_not_listed_in_names(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        names = svc.get_calendar_names()
        assert "exp" in names
        assert "__all__" not in names

    def test_all_records_defaults_to_current_month(self):
        _clean_cache()
        today = dt.date.today()
        data = svc.get_calendar_data("__all__")
        assert (data["year"], data["month"]) == (today.year, today.month)


class TestCalendarNavigation:
    def test_prev_rolls_december_to_january(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        _write_records(2026, [])
        data = svc.get_calendar_data("exp", 2026, 1)
        assert data["prev"] == {"year": 2025, "month": 12}

    def test_next_rolls_january_to_december(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        _write_records(2026, [])
        data = svc.get_calendar_data("exp", 2025, 12)
        assert data["next"] == {"year": 2026, "month": 1}

    def test_prev_next_regular_month(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        _write_records(2026, [])
        data = svc.get_calendar_data("exp", 2026, 3)
        assert data["prev"] == {"year": 2026, "month": 2}
        assert data["next"] == {"year": 2026, "month": 4}

    def test_time_window_sets_initial_month(self):
        _clean_cache()
        today = dt.date.today()
        last_month = dt.date(today.year, today.month, 1) - dt.timedelta(days=1)
        _add_calendar("exp", ["type=expense"], time_window="lm")
        _write_records(today.year, [f"{today} type=expense"])
        data = svc.get_calendar_data("exp")
        assert (data["year"], data["month"]) == (last_month.year, last_month.month)


class TestCalendarConfig:
    def test_unconfigured_calendar_raises(self):
        _clean_cache()
        with pytest.raises(svc.PTOSError):
            svc.get_calendar_data("does_not_exist")

    def test_calendar_names_lists_configured(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        _add_calendar("work", ["type=task"])
        names = svc.get_calendar_names()
        assert "exp" in names
        assert "work" in names

    def test_save_queries_full_round_trips(self):
        _clean_cache()
        svc.save_queries_full({}, {}, {},
            raw_calendars={"exp": {"filters": ["type=expense"], "time_window": "last-month"}})
        queries = ptos.get_queries()
        assert queries["calendar.exp"] == {"filters": ["type=expense"], "time_window": "last-month"}

    def test_save_queries_full_rejects_empty_filters(self):
        _clean_cache()
        with pytest.raises(svc.PTOSError):
            svc.save_queries_full({}, {}, {}, raw_calendars={"exp": {"filters": []}})

    def test_save_ignores_leaked_config_keys_in_queries(self):
        _clean_cache()
        svc.save_queries_full(
            {"habit.exercise": {"where": "", "time": "tm"},
             "board.client_sale_journey": {"where": "", "time": "tm"}},
            {},
            {},
            raw_habits={"exercise": {"filters": ["type=habit", "name=exercise"], "weeks": 12}},
            raw_calendars={"prescriptions": {"filters": ["type=prescription"]}},
        )
        queries = ptos.get_queries()
        assert queries["habit.exercise"] == {
            "filters": ["type=habit", "name=exercise"], "weeks": 12}
        assert queries["calendar.prescriptions"] == {"filters": ["type=prescription"]}

    def test_save_leaked_habit_key_no_longer_raises_invalid_name(self):
        _clean_cache()
        svc.save_queries_full(
            {"habit.exercise": {"where": "", "time": "tm"}},
            {},
            {},
            raw_habits={"exercise": {"filters": ["type=habit", "name=exercise"]}},
        )
        queries = ptos.get_queries()
        assert queries["habit.exercise"]["filters"] == ["type=habit", "name=exercise"]


class TestCalendarCaching:
    def test_append_record_invalidates(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        today = dt.date.today()
        _write_records(today.year, [f"{today} type=expense amount=1"])
        data = svc.get_calendar_data("exp", today.year, today.month)
        assert data["total_records"] == 1
        assert f"calendar:exp:{today.year}:{today.month}" in ptos._CACHE
        svc.append_record(f"{today} type=expense amount=2")
        assert f"calendar:exp:{today.year}:{today.month}" not in ptos._CACHE
        data2 = svc.get_calendar_data("exp", today.year, today.month)
        assert data2["total_records"] == 2

    def test_second_call_no_rescan(self, monkeypatch):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        today = dt.date.today()
        _write_records(today.year, [f"{today} type=expense amount=1"])
        calls = []
        original = ptos.find_records_with_location
        def counting(*a, **kw):
            calls.append(a)
            return original(*a, **kw)
        monkeypatch.setattr(ptos, "find_records_with_location", counting)
        first = svc.get_calendar_data("exp", today.year, today.month)
        n_after_first = len(calls)
        second = svc.get_calendar_data("exp", today.year, today.month)
        assert len(calls) == n_after_first
        assert first == second


class TestCalendarWeb:
    def test_calendar_page_renders_empty_state(self):
        _clean_cache()
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/calendar")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "All records" in html
        assert "showing" in html.lower()

    def test_calendar_page_renders_grid(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        today = dt.date.today()
        _write_records(today.year, [f"{today} type=expense amount=100"])
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/calendar")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "exp" in html
        assert "record(s) this month" in html

    def test_calendar_named_route(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        today = dt.date.today()
        _write_records(today.year, [f"{today} type=expense amount=100"])
        from ptos_web import app
        client = app.test_client()
        resp = client.get(f"/calendar/exp?year={today.year}&month={today.month}")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Open day in Browse" in html

    def test_global_view_shows_all_types_and_named_filters(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"])
        today = dt.date.today()
        _write_records(today.year, [
            f"{today} type=expense amount=100",
            f"{today} type=prescription fit=binaural",
        ])
        from ptos_web import app
        client = app.test_client()
        html_all = client.get("/calendar").get_data(as_text=True)
        assert "(prescription)" in html_all
        html_exp = client.get(
            f"/calendar/exp?year={today.year}&month={today.month}").get_data(as_text=True)
        assert "(prescription)" not in html_exp

    def test_query_builder_includes_calendars(self):
        _clean_cache()
        _add_calendar("exp", ["type=expense"], time_window="last-month")
        import re
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/query-builder")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        m = re.search(r"var _bkCalendars = (.*?);", html, re.S)
        assert m, "calendars JSON not found in rendered page"
        import json
        cals = json.loads(m.group(1))
        assert "exp" in cals
        assert cals["exp"]["filters"] == ["type=expense"]
        assert cals["exp"]["time_window"] == "last-month"
