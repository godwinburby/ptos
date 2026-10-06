"""The record format's one hard rule: both halves of key=value are single tokens.

FORMAT.md states it; build_record_line enforces the value half and every
name-minting path enforces the key half. These tests pin both sides, plus a
check over the starter demo that would have caught the 17 seeded lines that
violated the rule before it was enforced.
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
    def test_values_are_normalized(self):
        line = ptos.build_record_line(
            "2026-03-13", {"type": "expense", "merchant": "Big Bazaar",
                           "amount": 250})
        assert line == "2026-03-13 type=expense merchant=Big_Bazaar amount=250"

    def test_pipe_in_value_is_defused(self):
        line = ptos.build_record_line("2026-03-13", {"tag": "a|b"}, "note here")
        assert line == "2026-03-13 tag=a/b | note here"
        # Critically: only one | remains, so the note boundary is unambiguous.
        assert line.count("|") == 1
        assert ptos.parse_line(line) == (
            ptos.parse_date("2026-03-13"), {"tag": "a/b"}, "note here")

    def test_note_is_never_touched(self):
        # Notes live after the | and may contain anything at all.
        note = "Team lunch | with  snacks   and   a=b"
        line = ptos.build_record_line("2026-03-13", {"type": "expense"}, note)
        assert line.endswith("| " + note)
        assert ptos.parse_line(line)[2] == note

    def test_multi_value_fields(self):
        line = ptos.build_record_line(
            "2026-03-12", {"type": "expense", "tag": ["auto deal", "bus"]})
        assert line == "2026-03-12 type=expense tag=auto_deal tag=bus"
        assert ptos.parse_line(line)[1]["tag"] == ["auto_deal", "bus"]

    def test_empty_value_stays_a_field(self):
        line = ptos.build_record_line("2026-03-16",
                                     {"type": "expense", "amount": ""})
        assert line == "2026-03-16 type=expense amount="
        assert ptos.parse_line(line)[1]["amount"] == ""

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
    """Every seeded record line, with its {{date}} token left in place."""
    path = os.path.join(STARTERS, "starter_demo.toml")
    text = open(path, encoding="utf-8").read()
    body = re.search(r"^lines\s*=\s*\[(.*?)^\]", text, re.M | re.S)
    assert body, "could not find the [records] lines array in starter_demo.toml"
    out = []
    for raw in body.group(1).splitlines():
        s = raw.strip()
        if s.startswith('"'):
            out.append(s.strip('",'))
    return out


class TestStarterDemoObeysTheFormat:
    """Seeded demo data must not model the mistake the spec warns about.

    Every value in a record line is a single token, so the field part may
    not contain a piece without '=' -- that is a silently dropped word.
    Seventeen seeded lines did exactly this before build_record_line
    enforced the rule: `position=Product Manager` was stored as
    position="Product", and schema validation did not catch it because
    `position` is a free-text field.
    """

    LINES = _demo_record_lines()

    def test_demo_has_records_to_check(self):
        assert len(self.LINES) > 20

    def test_no_silently_dropped_words(self):
        offenders = []
        for line in self.LINES:
            field_part = line.partition("|")[0].partition(" ")[2]
            stray = [p for p in field_part.split() if "=" not in p]
            if stray:
                offenders.append((line, stray))
        assert not offenders, "\n".join(
            "dropped %s from: %s" % (s, l) for l, s in offenders)

    def test_no_space_inside_any_value(self):
        offenders = [l for l in self.LINES
                     if any(" " in p for p in l.partition("|")[0].split())]
        assert not offenders, "\n".join(offenders)

    def test_no_pipe_inside_the_field_part(self):
        # A | is the note separator, so the field part can only hold the
        # one trailing separator (checked separately) and never an interior one.
        offenders = []
        for line in self.LINES:
            field_part = line.partition("|")[0]
            for p in field_part.split():
                if "|" in p:
                    offenders.append(line)
        assert not offenders, "\n".join(offenders)

    def test_every_line_starts_with_a_date_token(self):
        bad = [l for l in self.LINES
               if not re.match(r"^\{\{[^}]+\}\}\s", l)]
        assert not bad, "\n".join(bad)


class TestTeachingNoteObeysTheFormat:
    """The seeded note that explains the format must not break it."""

    def test_example_records_in_demo_note_are_conforming(self):
        path = os.path.join(STARTERS, "starter_demo.toml")
        text = open(path, encoding="utf-8").read()
        examples = re.findall(r"^\d{4}-\d{2}-\d{2} type=.*$", text, re.M)
        assert examples, "the how_i_log note should show example records"
        for line in examples:
            field_part = line.partition("|")[0]
            stray = [p for p in field_part.split()[1:] if "=" not in p]
            assert not stray, (line, stray)