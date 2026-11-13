"""Starter area note template: the ptos blocks must be valid widgets."""
import re
import tomllib
from pathlib import Path

STARTER = Path(__file__).resolve().parent.parent / "starters" / "starter_area.md"

BLOCK_RE = re.compile(r"````ptos\n(.*?)\n````", re.S)


def _read_starter():
    return STARTER.read_text(encoding="utf-8")


def _replace_placeholders(text):
    return text.replace("{{AREA_TITLE}}", "Work").replace("{{AREA}}", "work")


def _blocks(text):
    return BLOCK_RE.findall(text)


def test_starter_file_exists():
    assert STARTER.is_file()


def test_has_at_least_ten_ptos_blocks():
    assert len(_blocks(_read_starter())) >= 10


def test_every_block_is_valid_toml_and_widget_spec():
    import ptos_service as svc
    blocks = _blocks(_read_starter())
    assert blocks, "starter_area.md has no ptos blocks"
    for body in blocks:
        filled = _replace_placeholders(body)
        spec = tomllib.loads(filled)
        result = svc.validate_widget_spec(spec)
        assert result["ok"] is True, f"invalid widget spec {spec}: {result['errors']}"
        assert result["errors"] == []


def test_no_placeholders_after_replacement():
    for body in _blocks(_read_starter()):
        filled = _replace_placeholders(body)
        assert "{{AREA}}" not in filled
        assert "{{AREA_TITLE}}" not in filled


def test_placeholder_names_are_not_live_tokens():
    text = _read_starter()
    live = {"greeting", "period", "name", "date", "weekday", "time"}
    used = set(re.findall(r"\{\{\s*([A-Za-z_]+)", text))
    assert used
    assert used.isdisjoint(live), f"placeholder collides with live token: {used & live}"


def test_expected_sections_present():
    text = _read_starter()
    for heading in (
        "## Now",
        "## Plan",
        "### Quarter",
        "### Year",
        "### Someday",
        "## Log",
        "## Reflections",
        "## Reviews",
        "### Weekly Review",
        "### Monthly Review",
        "### Quarterly Review",
        "## Tasks",
        "## Records",
    ):
        assert heading in text, f"missing section: {heading}"


def test_notes_block_removed():
    text = _read_starter()
    assert "Notes in this area" not in text
    assert "type=note" not in text


def test_no_raw_html_colours_or_inline_style():
    text = _read_starter()
    assert re.search(r"#[0-9a-fA-F]{6}", text) is None
    assert re.search(r"<[A-Za-z/][^>]*>", text) is None
    assert "style=" not in text
