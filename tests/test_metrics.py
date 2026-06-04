import datetime as dt
import ptos


def _fake_scan(return_lines, return_total):
    """Return a scan_records mock that returns fixed results."""
    def scan(*a, **kw):
        return return_lines, return_total
    return scan


class TestRunMetric:
    def test_sum(self, monkeypatch, capsys):
        queries = {
            "base": {"where": "type=expense"},
            "metrics": {"my_sum": {"sum": "base"}},
        }
        monkeypatch.setattr(
            ptos, "scan_records",
            _fake_scan(["2026-01-15 type=expense amount=50"], 50)
        )
        start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
        assert ptos.run_metric("my_sum", queries, start, end, {}) is True
        out = capsys.readouterr().out
        assert "50" in out

    def test_sum_custom_field(self, monkeypatch, capsys):
        queries = {
            "base": {"where": "type=sale"},
            "metrics": {"my_sum": {"sum": "base", "field": "advance"}},
        }
        monkeypatch.setattr(
            ptos, "scan_records",
            _fake_scan(["2026-01-15 type=sale amount=100 advance=30"], 30)
        )
        start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
        assert ptos.run_metric("my_sum", queries, start, end, {}) is True
        out = capsys.readouterr().out
        assert "30" in out

    def test_avg(self, monkeypatch, capsys):
        queries = {
            "base": {"where": "type=expense"},
            "metrics": {"my_avg": {"avg": "base"}},
        }
        monkeypatch.setattr(
            ptos, "scan_records",
            _fake_scan(["2026-01-15 amount=50", "2026-01-16 amount=30"], 80)
        )
        start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
        assert ptos.run_metric("my_avg", queries, start, end, {}) is True
        out = capsys.readouterr().out
        assert "40" in out  # 80 / 2

    def test_avg_weighted(self, monkeypatch, capsys):
        queries = {
            "base": {"where": "type=expense"},
            "metrics": {
                "my_wavg": {
                    "avg": "base",
                    "unit_field": "category",
                    "unit_weights": {"food": 2, "transport": 1},
                }
            },
        }
        monkeypatch.setattr(
            ptos, "scan_records",
            _fake_scan([
                "2026-01-15 type=expense category=food amount=100",
                "2026-01-16 type=expense category=transport amount=20",
            ], 120)
        )
        start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
        assert ptos.run_metric("my_wavg", queries, start, end, {}) is True
        out = capsys.readouterr().out
        # weighted: (100 + 20) / (2 + 1) = 40
        assert "40" in out

    def test_avg_no_data(self, monkeypatch, capsys):
        queries = {
            "base": {"where": "type=expense"},
            "metrics": {"my_avg": {"avg": "base"}},
        }
        monkeypatch.setattr(ptos, "scan_records", _fake_scan([], 0))
        start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
        assert ptos.run_metric("my_avg", queries, start, end, {}) is True
        out = capsys.readouterr().out
        assert "no data" in out

    def test_ratio(self, monkeypatch, capsys):
        queries = {
            "a": {"where": "type=expense domain=work"},
            "b": {"where": "type=expense"},
            "metrics": {"my_ratio": {"ratio": ["a", "b"]}},
        }
        monkeypatch.setattr(
            ptos, "scan_records",
            _fake_scan(["2026-01-15 type=expense domain=work amount=50"], 50)
        )
        start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
        assert ptos.run_metric("my_ratio", queries, start, end, {}) is True
        out = capsys.readouterr().out
        # scan_records is called twice with same mock — both return 50
        # ratio: 50/50 = 100%
        assert "100.0%" in out

    def test_ratio_zero_denominator(self, monkeypatch, capsys):
        queries = {
            "a": {"where": "type=expense"},
            "b": {"where": "type=nonexistent"},
            "metrics": {"my_ratio": {"ratio": ["a", "b"]}},
        }
        monkeypatch.setattr(ptos, "scan_records", _fake_scan([], 0))
        start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
        assert ptos.run_metric("my_ratio", queries, start, end, {}) is True
        out = capsys.readouterr().out
        assert "no data" in out

    def test_max(self, monkeypatch, capsys):
        queries = {
            "base": {"where": "type=expense"},
            "metrics": {"my_max": {"max": "base"}},
        }
        monkeypatch.setattr(
            ptos, "scan_records",
            _fake_scan([
                "2026-01-15 type=expense amount=10",
                "2026-01-16 type=expense amount=50",
                "2026-01-17 type=expense amount=30",
            ], 90)
        )
        start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
        assert ptos.run_metric("my_max", queries, start, end, {}) is True
        out = capsys.readouterr().out
        assert "50" in out

    def test_min(self, monkeypatch, capsys):
        queries = {
            "base": {"where": "type=expense"},
            "metrics": {"my_min": {"min": "base"}},
        }
        monkeypatch.setattr(
            ptos, "scan_records",
            _fake_scan([
                "2026-01-15 type=expense amount=10",
                "2026-01-16 type=expense amount=50",
                "2026-01-17 type=expense amount=30",
            ], 90)
        )
        start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
        assert ptos.run_metric("my_min", queries, start, end, {}) is True
        out = capsys.readouterr().out
        assert "10" in out

    def test_max_no_data(self, monkeypatch, capsys):
        queries = {
            "base": {"where": "type=expense"},
            "metrics": {"my_max": {"max": "base"}},
        }
        monkeypatch.setattr(ptos, "scan_records", _fake_scan([], 0))
        start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
        assert ptos.run_metric("my_max", queries, start, end, {}) is True
        out = capsys.readouterr().out
        assert "no data" in out

    def test_derived_simple_addition(self, monkeypatch, capsys):
        queries = {
            "a": {"where": "type=expense"},
            "b": {"where": "type=income"},
            "metrics": {
                "a_sum": {"sum": "a"},
                "b_sum": {"sum": "b"},
                "total": {"derived": "a_sum + b_sum"},
            },
        }
        monkeypatch.setattr(
            ptos, "scan_records",
            _fake_scan(["2026-01-15 type=expense amount=100"], 100)
        )
        start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
        assert ptos.run_metric("total", queries, start, end, {}) is True
        out = capsys.readouterr().out
        assert "200" in out  # 100 + 100

    def test_derived_with_dates(self, monkeypatch, capsys):
        queries = {
            "base": {"where": "type=expense"},
            "metrics": {
                "m_sum": {"sum": "base"},
                "m_daily": {"derived": "m_sum / month_days"},
            },
        }
        import subprocess
        monkeypatch.setattr(
            ptos, "scan_records",
            _fake_scan(["2026-01-15 type=expense amount=310"], 310)
        )
        start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
        assert ptos.run_metric("m_daily", queries, start, end, {}) is True
        out = capsys.readouterr().out
        assert "10" in out  # 310 / 31

    def test_unknown_metric(self):
        assert ptos.run_metric("nope", {}, None, None, {}) is False

    def test_not_found_in_metrics(self, capsys):
        queries = {"metrics": {}}
        assert ptos.run_metric("nonexistent", queries, None, None, {}) is False
