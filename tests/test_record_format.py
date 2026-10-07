"""The v2 record format: single-token keys/tags, quoted free-text values.

FORMAT.md states it; build_record_line enforces it and every name-minting
path enforces the key half. These tests pin both sides, plus a check that
every seeded line in the starter demo strict-parses as canonical v2.
"""
import os
import re

import pytest

import ptos


class TestNormalizeFieldValue:
    def test_plain_value_unchanged(self):
        assert ptos.normalize_field_value("food") == "food"

    def test_space_becomes_underscore(self):
        assert ptos.normalize_field_value("Big Bazaar") == "Big_Bazaar"

    def test_collapses_runs_of_whitespace(self):
        assert ptos.normalize_field_value("Big   Bazaar") == "Big_Bazaar"
        assert ptos.normalize_field_value("a\t\tb") == "a_b"

    def test_strips_leading_and_trailing(self):
        assert ptos.normalize_field_value("  Big Bazaar  ") == "Big_Bazaar"

    def test_pipe_becomes_slash(self):
        # A | would start the note and discard the rest of the field part.
        assert ptos.normalize_field_value("a|b") == "a/b"

    def test_non_string_scalars_survive(self):
        assert ptos.normalize_field_value(120) == "120"
        assert ptos.normalize_field_value(12.5) == "12.5"

    def test_empty_stays_empty(self):
        assert ptos.normalize_field_value("") == ""

    def test_idempotent(self):
        # The rebuild paths (edit, advance, convert) pass parsed kv back
        # through the writer, so a normalized value must not change again
        # or every unrelated edit would rewrite the file.
        once = ptos.normalize_field_value("Big   Bazaar|x")
        assert ptos.normalize_field_value(once) == once


class TestBuildRecordLine:
    def test_free_text_is_quoted_and_tokens_are_normalized(self):
        # Free-text values keep their spaces (quoted); `tag` keeps the
        # single-token rule (spaces -> underscores) and is never quoted.
        line = ptos.build_record_line(
            "2026-03-13", {"type": "expense", "merchant": "Big Bazaar",
                           "amount": 250})
        assert line == '2026-03-13 type=expense merchant="Big Bazaar" amount=250'

    def test_tag_is_a_single_token_never_quoted(self):
        line = ptos.build_record_line(
            "2026-03-13", {"type": "expense", "tag": "a|b"}, "note here")
        assert line == '2026-03-13 type=expense tag=a/b note="note here"'
        assert '"a/b"' not in line
        assert ptos.parse_line(line) == (
            ptos.parse_date("2026-03-13"), {"type": "expense", "tag": "a/b"},
            "note here")

    def test_note_keeps_inner_text_but_collapses_line_breaks(self):
        # The note keeps inner spacing, '|', '=' and punctuation — only line
        # breaks are collapsed, because a record is one physical line.
        note = "Team lunch | with  snacks   and   a=b"
        line = ptos.build_record_line("2026-03-13", {"type": "expense"}, note)
        assert line.endswith("note=" + ptos._quote_value(note))
        assert ptos.parse_line(line)[2] == note

    def test_newline_in_note_becomes_a_space(self):
        line = ptos.build_record_line(
            "2026-03-13", {"type": "expense"}, "line one\nline two")
        assert "\n" not in line
        assert ptos.parse_line(line)[2] == "line one line two"

    def test_multi_value_fields(self):
        line = ptos.build_record_line(
            "2026-03-12", {"type": "expense", "tag": ["auto deal", "bus"]})
        assert line == "2026-03-12 type=expense tag=auto_deal tag=bus"
        assert ptos.parse_line(line)[1]["tag"] == ["auto_deal", "bus"]

    def test_empty_value_is_refused(self):
        # v2 forbids empty values: omit the field instead of writing `key=`.
        with pytest.raises(ptos.PTOSError, match="empty value"):
            ptos.build_record_line("2026-03-16",
                                   {"type": "expense", "amount": ""})

    def test_round_trip_is_stable(self):
        once = ptos.build_record_line(
            "2026-03-13", {"type": "expense", "merchant": "Big Bazaar"})
        date, kv, note = ptos.parse_line(once)
        twice = ptos.build_record_line(date.isoformat(), kv, note or None)
        assert twice == once


class TestValidateRecordAgreesWithTheWriter:
    """A schema option hand-edited to contain a space must still validate."""

    def _schema(self, options):
        return {
            "types": {"allowed": ["expense"]},
            "type": {"expense": {"fields": {
                "category": {"options": options}}}},
            "fields": {},
        }

    def test_normalized_value_matches_spaced_option(self):
        schema = self._schema(["Big Bazaar"])
        assert ptos.validate_record(
            schema, {"type": "expense", "category": "Big_Bazaar"}) == []

    def test_unnormalized_value_also_accepted(self):
        schema = self._schema(["Big Bazaar"])
        assert ptos.validate_record(
            schema, {"type": "expense", "category": "Big Bazaar"}) == []

    def test_genuinely_wrong_value_still_rejected(self):
        schema = self._schema(["Big Bazaar"])
        problems = ptos.validate_record(
            schema, {"type": "expense", "category": "Small_Bazaar"})
        assert len(problems) == 1 and "Invalid value" in problems[0]

    def test_normalized_option_unchanged(self):
        schema = self._schema(["Big_Bazaar"])
        assert ptos.validate_record(
            schema, {"type": "expense", "category": "Big_Bazaar"}) == []


class TestNameIsASingleToken:
    """The key half of key=value obeys the same rule as the value half.

    A name with a space can never be matched: the field part is split on
    whitespace, so `amount spent=50` parses as `amount=spent` plus a dropped
    word. Every write path that mints a name must reject or coerce one.
    """

    def test_legal_names(self):
        for name in ("type", "amount", "my_field", "f2", "x1"):
            assert ptos.is_valid_name(name), name

    def test_names_with_spaces_rejected(self):
        for name in ("my field", "big bazaar", " leading", "trailing "):
            assert not ptos.is_valid_name(name), name

    def test_trailing_newline_rejected(self):
        # A $ anchor would match just before a trailing newline and let a
        # name in from a pasted value; fullmatch does not.
        assert not ptos.is_valid_name("amount\n")

    def test_uppercase_rejected(self):
        # Values keep their case (Big_Bazaar is legal); keys do not, because
        # filters and schema lookups are case-sensitive lowercase tokens.
        assert not ptos.is_valid_name("BigBazaar")

    def test_non_string_rejected(self):
        assert not ptos.is_valid_name(None)
        assert not ptos.is_valid_name("")

    def test_normalize_name_coerces(self):
        assert ptos.normalize_name("  My Field  ") == "my_field"
        assert ptos.normalize_name("Big  Bazaar") == "big_bazaar"
        assert ptos.normalize_name("already_fine") == "already_fine"
        # Idempotent, so a round trip through the UI is stable.
        assert ptos.normalize_name(ptos.normalize_name("My Field")) == "my_field"

    def test_error_message_names_the_offender(self):
        msg = ptos.invalid_name_error("field", "my field")
        assert "my field" in msg and "underscores" in msg


class TestValidateSchemaStructureChecksNames:
    """`ptos --lint` must flag a field name no record could ever match."""

    def _schema(self):
        return {"types": {"allowed": ["expense"]},
                "type": {"expense": {"fields": {"amount": {"type": "int"}}}}}

    def test_clean_schema_passes(self):
        assert ptos.validate_schema_structure(self._schema()) == []

    def test_spaced_type_name_flagged(self):
        s = self._schema()
        s["types"]["allowed"] = ["expense report"]
        assert any("expense report" in i for i in ptos.validate_schema_structure(s))

    def test_spaced_field_name_flagged(self):
        s = self._schema()
        s["type"]["expense"]["fields"]["unit price"] = {"type": "string"}
        assert any("unit price" in i for i in ptos.validate_schema_structure(s))

    def test_spaced_global_field_name_flagged(self):
        s = self._schema()
        s["global_fields"] = {"cost centre": {"type": "string"}}
        assert any("cost centre" in i for i in ptos.validate_schema_structure(s))

    def test_spaced_shared_name_flagged(self):
        s = self._schema()
        s["shared"] = {"money value": {"type": "int"}}
        assert any("money value" in i for i in ptos.validate_schema_structure(s))


class TestInvalidSchemaNames:
    """The helper the Schema Builder uses to reject bad field names."""

    def test_clean_payload_reports_nothing(self):
        assert ptos.invalid_schema_names(
            {"expense": {"fields": {"amount": {}}, "required": ["amount"]}},
            {"currency": {}}, {"origin": {}}, {"money": {}}) == []

    def test_flags_field_name(self):
        bad = ptos.invalid_schema_names(
            {"expense": {"fields": {"unit price": {}}}})
        assert bad == ["unit price"]

    def test_flags_required_entry(self):
        # A required list entry is a field name too, and would otherwise be
        # reported as "required field has no definition" instead.
        bad = ptos.invalid_schema_names(
            {"expense": {"fields": {}, "required": ["cost centre"]}})
        assert bad == ["cost centre"]

    def test_flags_global_field_and_shared_names(self):
        bad = ptos.invalid_schema_names({}, {"cost centre": {}}, None,
                                        {"money value": {}})
        assert bad == ["cost centre", "money value"]

    def test_deduplicates_and_sorts(self):
        bad = ptos.invalid_schema_names(
            {"a": {"fields": {"x y": {}}}, "b": {"fields": {"x y": {}}}},
            {"x y": {}})
        assert bad == ["x y"]

    def test_ignores_non_dict_type_schema(self):
        assert ptos.invalid_schema_names({"a": None, "b": "x"}) == []


class TestSaveRejectsSpacedNames:
    """Every name that reaches a config file is a key in a dotted TOML key.

    A spaced name can be written to queries.toml (quoted keys allow it) but is
    then unreachable through the URL param or CLI flag that selects it.
    """

    def _save(self, **kw):
        import ptos_service
        base = {"raw_queries": {}, "raw_metrics": {}, "raw_dashboards": {}}
        base.update(kw)
        ptos_service.save_queries_full(**base)

    @pytest.mark.parametrize("section,kwarg,entry", [
        ("query", "raw_queries", {"where": "type=habit"}),
        ("metric", "raw_metrics", {"kind": "sum", "base": "q"}),
        ("board", "raw_boards", {"columns": ["habit"]}),
        ("calendar", "raw_calendars", {"filters": ["type=habit"]}),
        ("threshold", "raw_thresholds", {"metric": "q"}),
        ("habit", "raw_habits", {"filters": ["type=habit"]}),
        ("due", "raw_due", {"type": "habit", "key": "name"}),
        ("project", "raw_projects", {"label": "P"}),
    ])
    def test_spaced_name_rejected(self, section, kwarg, entry):
        import ptos_service
        with pytest.raises(ptos_service.PTOSError, match="Invalid name"):
            self._save(**{kwarg: {"my name": entry}})

    @pytest.mark.parametrize("section,kwargs", [
        ("habit", {"raw_habits": {"my_habit": {"filters": ["type=habit"]}}}),
        ("due", {"raw_due": {"my_due": {"type": "habit", "key": "name"}}}),
        ("project", {"raw_projects": {"my_project": {"label": "P"}}}),
    ])
    def test_underscore_name_accepted(self, section, kwargs):
        self._save(**kwargs)

    def test_valid_name_for_every_section_round_trips(self):
        self._save(
            raw_queries={"q": {"where": "type=habit"}},
            raw_metrics={"m": {"kind": "sum", "base": "q"}},
            raw_boards={"b": {"columns": ["habit"]}},
            raw_calendars={"c": {"filters": ["type=habit"]}},
            raw_thresholds={"t": {"metric": "q"}},
            raw_habits={"h": {"filters": ["type=habit"]}},
            raw_due={"d": {"type": "habit", "key": "name"}},
            raw_projects={"p": {"label": "P"}})


STARTERS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "starters")


def _demo_record_lines():
    """Every seeded record line, with its {{date}} token left in place.

    starter_demo.toml is TOML, so the embedded record lines escape their
    inner quotes (``\\"``); unescape to the raw record line v2 parses.
    """
    path = os.path.join(STARTERS, "starter_demo.toml")
    text = open(path, encoding="utf-8").read()
    body = re.search(r"^lines\s*=\s*\[(.*?)^\]", text, re.M | re.S)
    assert body, "could not find the [records] lines array in starter_demo.toml"
    out = []
    for raw in body.group(1).splitlines():
        s = raw.strip()
        if not (s.startswith('"') and s.endswith('",')):
            continue
        out.append(s[1:-2].replace('\\"', '"'))
    return out


def _canonical(line):
    """Real-date the {{date}} token, then strict-parse and re-emit."""
    real = re.sub(r"\{\{[^}]+\}\}", "2026-09-12", line)
    date, kv, note = ptos._parse_v2(real)
    return real, ptos.build_record_line(date, kv, note or None)


class TestStarterDemoObeysTheFormat:
    """Seeded demo data must be canonical v2.

    Every line must strict-parse (leading date, ``type=`` next, quoted
    free-text, ``note=``) and re-emit byte-identical -- the same property
    the migrator relies on to leave canonical lines untouched. Seventeen
    seeded lines once carried `position=Product Manager`, which v1 silently
    read as `position=Product`; the v2 writer now refuses a space in a token
    field, and the demo must use an underscore instead.
    """

    LINES = _demo_record_lines()

    def test_demo_has_records_to_check(self):
        assert len(self.LINES) > 20

    def test_every_line_strict_parses_as_v2(self):
        bad = []
        for line in self.LINES:
            real = re.sub(r"\{\{[^}]+\}\}", "2026-09-12", line)
            try:
                ptos._parse_v2(real)
            except ValueError as exc:
                bad.append("%s (%s)" % (line, exc))
        assert not bad, "\n".join(bad)

    def test_every_line_is_canonical(self):
        bad = []
        for line in self.LINES:
            real, rebuilt = _canonical(line)
            if rebuilt != real:
                bad.append("in:  %s\nout: %s" % (real, rebuilt))
        assert not bad, "\n".join(bad)

    def test_every_line_starts_with_a_date_token(self):
        bad = [l for l in self.LINES
               if not re.match(r"^\{\{[^}]+\}\}\s", l)]
        assert not bad, "\n".join(bad)

    def test_type_is_the_second_token(self):
        bad = [l for l in self.LINES
               if not re.match(r"^\{\{[^}]+\}\}\s+type=\S+", l)]
        assert not bad, "\n".join(bad)


class TestTeachingNoteObeysTheFormat:
    """The seeded note that explains the format must not break it."""

    def test_example_records_in_demo_note_are_conforming(self):
        path = os.path.join(STARTERS, "starter_demo.toml")
        text = open(path, encoding="utf-8").read()
        examples = re.findall(r"^\d{4}-\d{2}-\d{2} type=.*$", text, re.M)
        assert examples, "the how_i_log note should show example records"
        for line in examples:
            date, kv, note = ptos._parse_v2(line)
            assert ptos.build_record_line(date, kv, note or None) == line, line