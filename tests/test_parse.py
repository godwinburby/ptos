import datetime as dt
import pytest
from ptos import parse_line, safe_parse_line, build_record_line, apply_set


class TestParseLine:
    def test_basic(self):
        d, kv, note = parse_line("2026-01-15 type=expense amount=50")
        assert d == dt.date(2026, 1, 15)
        assert kv["type"] == "expense"
        assert kv["amount"] == "50"
        assert note == ""

    def test_with_note(self):
        d, kv, note = parse_line("2026-01-15 type=expense | bought lunch")
        assert d == dt.date(2026, 1, 15)
        assert kv["type"] == "expense"
        assert note == "bought lunch"

    def test_multi_value_field(self):
        d, kv, note = parse_line("2026-03-01 type=expense tag=food tag=groceries")
        assert kv["tag"] == ["food", "groceries"]

    def test_whitespace_handling(self):
        d, kv, note = parse_line("  2026-06-01  type=expense  amount=30  |  a note  ")
        assert d == dt.date(2026, 6, 1)
        assert kv["amount"] == "30"
        assert note == "a note"

    def test_empty_line_raises(self):
        with pytest.raises(ValueError):
            parse_line("")
        with pytest.raises(ValueError):
            parse_line("   ")

    def test_malformed_date_raises(self):
        with pytest.raises(ValueError):
            parse_line("bad-date type=expense")

    def test_no_date(self):
        with pytest.raises(ValueError):
            parse_line("type=expense amount=50")


class TestSafeParseLine:
    def test_valid_returns_result(self):
        result = safe_parse_line("2026-01-15 type=expense")
        assert result is not None
        d, kv, note = result
        assert d == dt.date(2026, 1, 15)

    def test_invalid_returns_none(self):
        assert safe_parse_line("") is None
        assert safe_parse_line("bad-date x=y") is None
        assert safe_parse_line("onlytext") is None


class TestBuildRecordLine:
    def test_basic(self):
        line = build_record_line("2026-01-15", {"type": "expense", "amount": "50"})
        assert line == "2026-01-15 type=expense amount=50"

    def test_with_note(self):
        line = build_record_line("2026-01-15", {"type": "expense"}, note="test note")
        assert line == "2026-01-15 type=expense | test note"

    def test_multi_value_field(self):
        line = build_record_line(
            "2026-01-15", {"type": "expense", "tag": ["food", "groceries"]}
        )
        assert "tag=food" in line
        assert "tag=groceries" in line

    def test_empty_record(self):
        line = build_record_line("2026-01-15", {})
        assert line == "2026-01-15 "  # trailing space is expected

    def test_note_strip(self):
        line = build_record_line("2026-01-15", {"type": "expense"}, note="  spaced  ")
        assert line == "2026-01-15 type=expense |   spaced  "  # note preserved as-is


class TestApplySet:
    def test_set_simple(self):
        old = "2026-01-15 type=expense amount=50"
        new_line, meta = apply_set(old, ["amount=100"], None)
        d, kv, note = parse_line(new_line)
        assert kv["amount"] == "100"

    def test_set_remove_field(self):
        old = "2026-01-15 type=expense amount=50 vendor=store"
        new_line, meta = apply_set(old, ["vendor="], None)
        d, kv, note = parse_line(new_line)
        assert "vendor" not in kv

    def test_add_tag(self):
        old = "2026-01-15 type=expense tag=food"
        new_line, meta = apply_set(old, ["tag+=coffee"], None)
        d, kv, note = parse_line(new_line)
        assert kv["tag"] == ["food", "coffee"]

    def test_remove_tag(self):
        old = "2026-01-15 type=expense tag=food tag=coffee"
        new_line, meta = apply_set(old, ["tag-=coffee"], None)
        d, kv, note = parse_line(new_line)
        # collapses to scalar when only one remains
        assert kv["tag"] == "food"

    def test_set_new_note(self):
        old = "2026-01-15 type=expense | old note"
        new_line, meta = apply_set(old, [], "new note")
        d, kv, note = parse_line(new_line)
        assert note == "new note"

    def test_remove_note(self):
        old = "2026-01-15 type=expense | old note"
        new_line, meta = apply_set(old, [], "")
        d, kv, note = parse_line(new_line)
        assert note == ""

    def test_date_change(self):
        old = "2026-01-15 type=expense"
        new_line, meta = apply_set(old, ["date=2026-02-01"], None)
        assert new_line.startswith("2026-02-01")
