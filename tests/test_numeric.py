import ptos


class TestNumericValue:
    def test_finds_first_numeric_field(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount", "duration"])
        assert ptos.numeric_value({"amount": "50"}) == 50

    def test_returns_none_when_no_match(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        assert ptos.numeric_value({"type": "expense"}) is None

    def test_picks_first_of_multiple(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["duration", "amount"])
        assert ptos.numeric_value({"duration": "30", "amount": "100"}) == 30

    def test_multi_value_field(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        assert ptos.numeric_value({"amount": ["50", "30"]}) == 50

    def test_non_digit_returns_none(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        assert ptos.numeric_value({"amount": "abc"}) is None

    def test_empty_kv(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        assert ptos.numeric_value({}) is None


class TestNumericValueFor:
    def test_basic(self):
        assert ptos.numeric_value_for({"amount": "50"}, "amount") == 50

    def test_field_not_present(self):
        assert ptos.numeric_value_for({"amount": "50"}, "nonexistent") is None

    def test_non_numeric_value(self):
        assert ptos.numeric_value_for({"amount": "abc"}, "amount") is None

    def test_multi_value(self):
        assert ptos.numeric_value_for({"amount": ["50", "30"]}, "amount") == 50

    def test_int_value(self):
        assert ptos.numeric_value_for({"amount": 50}, "amount") == 50


class TestDetectValueField:
    def test_finds_numeric_in_first_line(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        results = ["2026-01-15 type=expense amount=50"]
        assert ptos.detect_value_field(results) == "amount"

    def test_skips_line_without_numeric(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        results = [
            "2026-01-15 type=expense",
            "2026-01-16 type=expense amount=30",
        ]
        assert ptos.detect_value_field(results) == "amount"

    def test_returns_none_when_no_numeric(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        results = ["2026-01-15 type=expense"]
        assert ptos.detect_value_field(results) is None

    def test_empty_results(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        assert ptos.detect_value_field([]) is None

    def test_malformed_line_skipped(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        results = ["invalid line", "2026-01-15 type=expense amount=50"]
        # detect_value_field calls parse_line which raises on invalid
        # we expect it to propagate the error since there's no try/except
        import pytest
        with pytest.raises(ValueError):
            ptos.detect_value_field(results)
