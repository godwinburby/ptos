import datetime as dt
import ptos


class TestIndianCommas:
    def test_small_number(self):
        assert ptos._indian_commas(100) == "100"

    def test_thousands(self):
        assert ptos._indian_commas(1000) == "1,000"

    def test_lakhs(self):
        assert ptos._indian_commas(100000) == "1,00,000"

    def test_crores(self):
        assert ptos._indian_commas(10000000) == "1,00,00,000"

    def test_negative(self):
        assert ptos._indian_commas(-5000) == "-5,000"

    def test_zero(self):
        assert ptos._indian_commas(0) == "0"


class TestFmt:
    def test_default_currency(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        monkeypatch.setattr(ptos, "currency", lambda: "")
        assert ptos.fmt(100) == "100"

    def test_rupee_currency(self, monkeypatch):
        monkeypatch.setattr(ptos, "currency", lambda: "₹")
        result = ptos.fmt(50000)
        assert "₹" in result
        assert "50,000" in result


class TestFmtAvg:
    def test_rounded_no_currency(self, monkeypatch):
        monkeypatch.setattr(ptos, "currency", lambda: "")
        assert ptos.fmt_avg(99.7) == "100"


class TestFmtDate:
    def test_indian_format(self, monkeypatch):
        monkeypatch.setattr(ptos, "date_format", lambda: "indian")
        d = dt.date(2026, 5, 16)
        assert ptos.fmt_date(d) == "16/05/2026"

    def test_us_format(self, monkeypatch):
        monkeypatch.setattr(ptos, "date_format", lambda: "us")
        d = dt.date(2026, 5, 16)
        assert ptos.fmt_date(d) == "05/16/2026"

    def test_eu_format(self, monkeypatch):
        monkeypatch.setattr(ptos, "date_format", lambda: "eu")
        d = dt.date(2026, 5, 16)
        assert ptos.fmt_date(d) == "16.05.2026"

    def test_readable_format(self, monkeypatch):
        monkeypatch.setattr(ptos, "date_format", lambda: "readable")
        d = dt.date(2026, 5, 16)
        assert ptos.fmt_date(d) == "16 May 2026"

    def test_iso_format(self, monkeypatch):
        monkeypatch.setattr(ptos, "date_format", lambda: "iso")
        d = dt.date(2026, 5, 16)
        assert ptos.fmt_date(d) == "2026-05-16"

    def test_custom_strftime(self, monkeypatch):
        monkeypatch.setattr(ptos, "date_format", lambda: "%Y/%m/%d")
        d = dt.date(2026, 5, 16)
        assert ptos.fmt_date(d) == "2026/05/16"


class TestFmtDatetime:
    def test_datetime_format(self, monkeypatch):
        monkeypatch.setattr(ptos, "date_format", lambda: "iso")
        d = dt.datetime(2026, 5, 16, 14, 30)
        # iso format calls .isoformat() on datetime → includes T and seconds
        assert "2026-05-16" in ptos.fmt_datetime(d)
        assert "14:30" in ptos.fmt_datetime(d)


class TestDisp:
    def test_underscores_replaced(self):
        assert ptos._disp("some_field") == "some field"

    def test_already_spaced(self):
        assert ptos._disp("hello world") == "hello world"

    def test_none_returns_empty(self):
        assert ptos._disp(None) == ""

    def test_empty_string(self):
        assert ptos._disp("") == ""

    def test_multi_underscores(self):
        assert ptos._disp("a_b_c_d") == "a b c d"
