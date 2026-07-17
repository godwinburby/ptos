import datetime as dt
import pytest
import ptos


class TestResolveTime:
    def test_today(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("today", {})
        assert start == dt.date(2026, 5, 16)
        assert end == dt.date(2026, 5, 16)

    def test_today_shortcode(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("td", {})
        assert start == dt.date(2026, 5, 16)
        assert end == dt.date(2026, 5, 16)

    def test_yesterday(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("yesterday", {})
        assert start == dt.date(2026, 5, 15)
        assert end == dt.date(2026, 5, 15)

    def test_yesterday_shortcode(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("yd", {})
        assert start == dt.date(2026, 5, 15)
        assert end == dt.date(2026, 5, 15)

    def test_this_week(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("this-week", {})
        assert start == dt.date(2026, 5, 11)
        assert end == dt.date(2026, 5, 17)

    def test_last_week(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("last-week", {})
        assert start == dt.date(2026, 5, 4)
        assert end == dt.date(2026, 5, 10)

    def test_this_month(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("this-month", {})
        assert start == dt.date(2026, 5, 1)
        assert end == dt.date(2026, 5, 31)

    def test_this_month_shortcode(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("tm", {})
        assert start == dt.date(2026, 5, 1)
        assert end == dt.date(2026, 5, 31)

    def test_last_month(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("last-month", {})
        assert start == dt.date(2026, 4, 1)
        assert end == dt.date(2026, 4, 30)

    def test_last_month_december(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 1, 15))
        start, end = ptos.resolve_time("last-month", {})
        assert start == dt.date(2025, 12, 1)
        assert end == dt.date(2025, 12, 31)

    def test_this_quarter(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("this-quarter", {})
        assert start == dt.date(2026, 4, 1)
        assert end == dt.date(2026, 6, 30)

    def test_last_quarter(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("last-quarter", {})
        assert start == dt.date(2026, 1, 1)
        assert end == dt.date(2026, 3, 31)

    def test_last_quarter_prev_year(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 1, 15))
        start, end = ptos.resolve_time("last-quarter", {})
        assert start == dt.date(2025, 10, 1)
        assert end == dt.date(2025, 12, 31)

    def test_this_year(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("this-year", {})
        assert start == dt.date(2026, 1, 1)
        assert end == dt.date(2026, 12, 31)

    def test_last_year(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("last-year", {})
        assert start == dt.date(2025, 1, 1)
        assert end == dt.date(2025, 12, 31)

    def test_all(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("all", {})
        assert start == dt.date.min
        assert end == dt.date.max

    def test_literal_month(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("2026-03", {})
        assert start == dt.date(2026, 3, 1)
        assert end == dt.date(2026, 3, 31)

    def test_custom_cycle(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("clinic", {"clinic": 26})
        assert start == dt.date(2026, 4, 26)
        assert end == dt.date(2026, 5, 25)

    def test_custom_cycle_with_offset(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("clinic-1", {"clinic": 26})
        assert start == dt.date(2026, 3, 26)
        assert end == dt.date(2026, 4, 25)

    def test_unknown_keyword_falls_back_to_this_month(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        start, end = ptos.resolve_time("bogus", {})
        assert start == dt.date(2026, 5, 1)
        assert end == dt.date(2026, 5, 31)

    def test_week_with_monday(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 11))
        start, end = ptos.resolve_time("this-week", {})
        assert start == dt.date(2026, 5, 11)
        assert end == dt.date(2026, 5, 17)

    def test_week_with_sunday(self, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 17))
        start, end = ptos.resolve_time("this-week", {})
        assert start == dt.date(2026, 5, 11)
        assert end == dt.date(2026, 5, 17)
