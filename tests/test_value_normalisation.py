"""The write path never silently loses data (SPEC R9.5).

A record is one physical line and both halves of key=value are single tokens
(FORMAT.md). build_record_line cleans and validates both; append_record refuses
anything the parser could not read back. These tests pin the general path, the
entry-point normalisation, and the two modules that used to assemble a record
line by hand.
"""
import os
import re

import pytest

import ptos


class TestCleanNote:
    def test_newline_becomes_a_space(self):
        assert ptos.clean_note("one\ntwo") == "one two"

    def test_crlf_and_cr_collapse(self):
        assert ptos.clean_note("one\r\ntwo\rthree") == "one two three"

    def test_inner_spacing_and_pipe_preserved(self):
        note = "a | b   c=d"
        assert ptos.clean_note(note) == note

    def test_empty_is_none(self):
        assert ptos.clean_note("") is None
        assert ptos.clean_note("   \n  ") is None
        assert ptos.clean_note(None) is None


class TestBuildRecordLineValidates:
    def test_bad_date_raises(self):
        with pytest.raises(ptos.PTOSError):
            ptos.build_record_line("2026-13-40", {"type": "expense"})
        with pytest.raises(ptos.PTOSError):
            ptos.build_record_line("not-a-date", {"type": "expense"})

    def test_non_iso_date_raises(self):
        # fromisoformat in 3.11 accepts 20260313; the format is stricter.
        with pytest.raises(ptos.PTOSError):
            ptos.build_record_line("20260313", {"type": "expense"})

    @pytest.mark.parametrize("key", ["", "a b", "a=b", "a|b"])
    def test_bad_key_raises(self, key):
        with pytest.raises(ptos.PTOSError):
            ptos.build_record_line("2026-03-13", {key: "x"})

    def test_newline_note_is_flattened(self):
        line = ptos.build_record_line(
            "2026-03-13", {"type": "expense"}, "one\ntwo")
        assert "\n" not in line
        assert ptos.parse_line(line)[2] == "one two"


class TestAppendRecordRefusesBadLines:
    YEAR = 2026

    def _read_all(self):
        out = []
        for dirpath, _dirs, files in os.walk(ptos.RECORDS_DIR):
            for name in files:
                with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                    out.append(f.read())
        return "\n".join(out)

    def test_newline_line_rejected(self):
        before = self._read_all()
        with pytest.raises(ptos.PTOSError):
            ptos.append_record("2026-03-13 type=expense\n2026-03-14 type=expense")
        assert self._read_all() == before

    def test_carriage_return_line_rejected(self):
        before = self._read_all()
        with pytest.raises(ptos.PTOSError):
            ptos.append_record("2026-03-13 type=expense\r")
        assert self._read_all() == before

    def test_unparseable_line_rejected(self):
        before = self._read_all()
        with pytest.raises(ptos.PTOSError):
            ptos.append_record("just some words with no date")
        assert self._read_all() == before

    def test_valid_line_is_written(self):
        line = ptos.build_record_line("2026-03-13", {"type": "expense"})
        ptos.append_record(line)
        assert line in self._read_all()


class TestApplySetNormalizesBeforeComparing:
    def test_plus_equals_does_not_duplicate_a_spaced_value(self):
        old = "2026-03-13 type=expense tag=big_shop"
        new, _ = ptos.apply_set(old, ["tag+=big shop"], None)
        assert new == "2026-03-13 type=expense tag=big_shop"

    def test_minus_equals_matches_a_spaced_value(self):
        old = "2026-03-13 type=expense tag=big_shop tag=bus"
        new, _ = ptos.apply_set(old, ["tag-=big shop"], None)
        assert new == "2026-03-13 type=expense tag=bus"

    def test_assignment_preserves_free_text(self):
        old = "2026-03-13 type=expense"
        new, _ = ptos.apply_set(old, ["merchant=Big Bazaar"], None)
        assert new == '2026-03-13 type=expense merchant="Big Bazaar"'


class TestOnlyTheEngineBuildsRecordLines:
    """No module outside ptos.py may assemble a record line by hand."""

    MODULES = ["ptos_service.py", "ptos_cli.py", "ptos_web.py", "desktop_app.py"]
    ALLOWED_ARGS = {
        "line", "new_line", "new_record_line", "stripped", "record", "rec_line",
    }

    def test_every_append_record_uses_build_record_line(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for name in self.MODULES:
            path = os.path.join(root, name)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                src = f.read()
            for m in re.finditer(r"append_record\(", src):
                tail = src[m.end():m.end() + 200].lstrip()
                arg = re.split(r"[,)]", tail, maxsplit=1)[0].strip()
                if "build_record_line" in arg or arg in self.ALLOWED_ARGS:
                    continue
                if re.fullmatch(r"draft\[['\"][^'\"]+['\"]\]", arg):
                    continue
                offenders.append(f"{name}: append_record({arg} ...")
        assert not offenders, "record line assembled by hand:\n" + "\n".join(offenders)