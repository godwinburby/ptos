import datetime as dt
import ptos


class TestChooseFromList:
    def test_valid_choice(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda _: "2")
        result = ptos.choose_from_list("Pick:", ["a", "b", "c"])
        assert result == "b"

    def test_invalid_then_valid(self, monkeypatch, capsys):
        inputs = iter(["0", "4", "1"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        result = ptos.choose_from_list("Pick:", ["x", "y"])
        assert result == "x"

    def test_prints_prompt_and_options(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda _: "1")
        ptos.choose_from_list("Select:", ["foo"])
        out = capsys.readouterr().out
        assert "Select:" in out
        assert "foo" in out


class TestChooseFromListOptional:
    def test_enter_skips(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda _: "")
        result = ptos.choose_from_list_optional("Pick:", ["a", "b"])
        assert result == ""

    def test_valid_number(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda _: "2")
        result = ptos.choose_from_list_optional("Pick:", ["a", "b", "c"])
        assert result == "b"

    def test_text_match(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda _: "coffee")
        result = ptos.choose_from_list_optional("Pick:", ["tea", "coffee", "water"])
        assert result == "coffee"

    def test_invalid_then_valid(self, monkeypatch, capsys):
        inputs = iter(["99", "1"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        result = ptos.choose_from_list_optional("Pick:", ["a", "b"])
        assert result == "a"


class TestInputText:
    def test_returns_text(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "hello")
        assert ptos.input_text("Name:") == "hello"

    def test_replaces_spaces_with_underscores(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "hello world")
        assert ptos.input_text("Name:") == "hello_world"

    def test_empty_loops(self, monkeypatch):
        inputs = iter(["", "", "ok"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        assert ptos.input_text("Name:") == "ok"


class TestInputInt:
    def test_valid_digit(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "42")
        assert ptos.input_int("Age:") == "42"

    def test_invalid_then_valid(self, monkeypatch):
        inputs = iter(["abc", "", "25"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        assert ptos.input_int("Age:") == "25"


class TestInputDate:
    def test_enter_uses_today(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "")
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        assert ptos.input_date() == "2026-05-16"

    def test_valid_date(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "2026-03-15")
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        assert ptos.input_date() == "2026-03-15"

    def test_invalid_then_valid(self, monkeypatch):
        inputs = iter(["bad", "2026-06-01"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 5, 16))
        assert ptos.input_date() == "2026-06-01"


class TestInputTags:
    def test_no_allowed_tags_freeform(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "custom_tag")
        tags, new_tags = ptos.input_tags([])
        assert tags == ["custom_tag"]
        assert new_tags == ["custom_tag"]

    def test_no_allowed_tags_skip(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "")
        tags, new_tags = ptos.input_tags([])
        assert tags == []
        assert new_tags == []

    def test_number_selection(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda _: "2")
        tags, new_tags = ptos.input_tags(["food", "transport", "work"])
        assert tags == ["transport"]
        assert new_tags == []

    def test_multiple_numbers(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda _: "1 3")
        tags, new_tags = ptos.input_tags(["food", "transport", "work"])
        assert tags == ["food", "work"]
        assert new_tags == []

    def test_comma_separated(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda _: "1, 3")
        tags, new_tags = ptos.input_tags(["food", "transport", "work"])
        assert tags == ["food", "work"]
        assert new_tags == []

    def test_custom_tag_with_numbers(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda _: "1 quick delivery")
        tags, new_tags = ptos.input_tags(["food", "transport", "work"])
        assert "food" in tags
        assert "quick_delivery" in tags
        assert "quick_delivery" in new_tags

    def test_skip_returns_empty(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda _: "")
        tags, new_tags = ptos.input_tags(["food", "transport"])
        assert tags == []
        assert new_tags == []

    def test_custom_tag_only(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda _: "groceries")
        tags, new_tags = ptos.input_tags(["food", "transport"])
        assert tags == ["groceries"]
        assert new_tags == ["groceries"]

    def test_custom_tag_matches_allowed(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda _: "FOOD")
        tags, new_tags = ptos.input_tags(["food", "transport"])
        assert tags == ["food"]
        assert new_tags == []
