import datetime as dt
from ptos import (
    parse_date,
    month_range,
    quarter_range,
    resolve_cycle,
    resolve_date,
    today,
)


class TestParseDate:
    def test_iso_format(self):
        assert parse_date("2026-01-15") == dt.date(2026, 1, 15)

    def test_invalid_raises(self):
        import pytest
        with pytest.raises(ValueError):
            parse_date("not-a-date")
        with pytest.raises(ValueError):
            parse_date("2026/01/15")
        with pytest.raises(ValueError):
            parse_date("15-01-2026")


class TestMonthRange:
    def test_january(self):
        assert month_range(2026, 1) == (dt.date(2026, 1, 1), dt.date(2026, 1, 31))

    def test_december(self):
        assert month_range(2026, 12) == (dt.date(2026, 12, 1), dt.date(2026, 12, 31))

    def test_february_non_leap(self):
        assert month_range(2025, 2) == (dt.date(2025, 2, 1), dt.date(2025, 2, 28))

    def test_february_leap(self):
        assert month_range(2024, 2) == (dt.date(2024, 2, 1), dt.date(2024, 2, 29))


class TestQuarterRange:
    def test_q1(self):
        assert quarter_range(2026, 0) == (dt.date(2026, 1, 1), dt.date(2026, 3, 31))

    def test_q2(self):
        assert quarter_range(2026, 1) == (dt.date(2026, 4, 1), dt.date(2026, 6, 30))

    def test_q3(self):
        assert quarter_range(2026, 2) == (dt.date(2026, 7, 1), dt.date(2026, 9, 30))

    def test_q4(self):
        assert quarter_range(2026, 3) == (dt.date(2026, 10, 1), dt.date(2026, 12, 31))


class TestResolveDate:
    def test_none_returns_today(self):
        assert resolve_date(None) == today().isoformat()

    def test_today_keyword(self):
        assert resolve_date("today") == today().isoformat()

    def test_yesterday_keyword(self):
        expected = (today() - dt.timedelta(days=1)).isoformat()
        assert resolve_date("yesterday") == expected

    def test_valid_iso(self):
        assert resolve_date("2026-05-01") == "2026-05-01"

    def test_invalid_exits(self):
        import pytest
        with pytest.raises(SystemExit):
            resolve_date("bad-date")


class TestResolveCycle:
    def test_basic_cycle_structure(self):
        start, end = resolve_cycle(15)
        assert isinstance(start, dt.date)
        assert isinstance(end, dt.date)
        assert start <= end

    def test_offset_returns_past(self):
        start0, end0 = resolve_cycle(1, offset=0)
        start1, end1 = resolve_cycle(1, offset=1)
        assert end1 < start0  # previous cycle ends before current starts
