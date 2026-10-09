import os
import random
from collections import Counter

import pytest

import ptos


REC_ORIG = "records/2026.log"
REC_CONF = "records/2026.sync-conflict-20260911-113533-XAJ7GJU.log"
TODO_ORIG = "todo/todo.txt"
TODO_CONF = "todo/todo.sync-conflict-20260827-111614-K4BHCH2.txt"


def _write(rel, lines):
    full = os.path.join(ptos.BASE_DIR, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write("".join(l + "\n" for l in lines))


def _read(rel):
    with open(os.path.join(ptos.BASE_DIR, rel), encoding="utf-8") as f:
        return f.read().splitlines()


class TestMultisetDiff:
    def test_duplicates_survive_the_diff(self):
        _write(REC_ORIG, [])
        dup = "2026-01-01 type=coffee amount=3"
        _write(REC_CONF, [dup, dup])
        d = ptos.diff_records_conflict(REC_ORIG, REC_CONF)
        assert d["lines_only_in_conflict"] == [dup, dup]

    def test_shared_line_cancels_once_not_all(self):
        line = "2026-01-01 type=coffee amount=3"
        _write(REC_ORIG, [line])
        _write(REC_CONF, [line, line])
        d = ptos.diff_records_conflict(REC_ORIG, REC_CONF)
        assert d["lines_only_in_conflict"] == [line]
        assert d["lines_only_in_original"] == []

    def test_file_order_is_kept(self):
        _write(REC_ORIG, [])
        _write(REC_CONF, [
            "2026-01-03 type=expense amount=3",
            "2026-01-01 type=expense amount=1",
            "2026-01-02 type=expense amount=2",
        ])
        d = ptos.diff_records_conflict(REC_ORIG, REC_CONF)
        assert d["lines_only_in_conflict"] == [
            "2026-01-03 type=expense amount=3",
            "2026-01-01 type=expense amount=1",
            "2026-01-02 type=expense amount=2",
        ]


class TestAddSemantics:
    def test_add_all_appends_duplicates(self):
        dup = "2026-01-01 type=coffee amount=3"
        _write(REC_ORIG, [])
        _write(REC_CONF, [dup, dup])
        ptos.import_all_conflict(REC_ORIG, REC_CONF, "records")
        assert Counter(_read(REC_ORIG))[dup] == 2

    def test_add_never_removes_an_original_line(self):
        _write(REC_ORIG, [
            "2026-01-01 type=expense amount=10",
            "2026-01-02 type=expense amount=20",
        ])
        _write(REC_CONF, [
            "2026-01-01 type=expense amount=10",
            "2026-01-03 type=income amount=30",
        ])
        ptos.import_all_conflict(REC_ORIG, REC_CONF, "records")
        after = _read(REC_ORIG)
        assert "2026-01-02 type=expense amount=20" in after
        assert "2026-01-03 type=income amount=30" in after
        assert not os.path.exists(os.path.join(ptos.BASE_DIR, REC_CONF))

    def test_add_selected_appends_even_when_present(self):
        line = "2026-01-01 type=coffee amount=3"
        _write(REC_ORIG, [line])
        _write(REC_CONF, [line])
        ptos.import_conflict_lines(REC_ORIG, REC_CONF, [line], "records")
        assert Counter(_read(REC_ORIG))[line] == 2


class TestReplaceSemantics:
    def test_replace_removes_exactly_one_original_line(self):
        old = "2026-01-01 type=expense amount=10"
        new = "2026-01-01 type=expense amount=99"
        _write(REC_ORIG, [old])
        _write(REC_CONF, [new])
        ptos.replace_conflict_line(REC_ORIG, REC_CONF, new, old, "records")
        assert _read(REC_ORIG) == [new]
        assert not os.path.exists(os.path.join(ptos.BASE_DIR, REC_CONF))

    def test_replace_keeps_duplicates_of_the_target(self):
        old = "2026-01-01 type=expense amount=10"
        new = "2026-01-01 type=expense amount=99"
        _write(REC_ORIG, [old, old])
        _write(REC_CONF, [new])
        ptos.replace_conflict_line(REC_ORIG, REC_CONF, new, old, "records")
        after = _read(REC_ORIG)
        assert Counter(after) == Counter([old, new])


class TestSkipSemantics:
    def test_skip_removes_without_adding(self):
        line = "2026-01-01 type=expense amount=99"
        _write(REC_ORIG, ["2026-01-01 type=expense amount=10"])
        _write(REC_CONF, [line])
        ptos.skip_conflict_line(REC_ORIG, REC_CONF, line, "records")
        assert _read(REC_ORIG) == ["2026-01-01 type=expense amount=10"]
        assert not os.path.exists(os.path.join(ptos.BASE_DIR, REC_CONF))


class TestFileDeletion:
    def test_file_survives_until_every_line_is_handled(self):
        a = "2026-01-08 type=expense amount=7"
        b = "2026-01-09 type=expense amount=8"
        _write(REC_ORIG, ["2026-01-01 type=expense amount=10"])
        _write(REC_CONF, [a, b])
        assert ptos.conflict_actionable_count(REC_ORIG, REC_CONF, "records") == 2
        resolved = ptos.import_conflict_lines(REC_ORIG, REC_CONF, [a], "records")
        assert resolved is False
        assert os.path.exists(os.path.join(ptos.BASE_DIR, REC_CONF))
        resolved = ptos.skip_conflict_line(REC_ORIG, REC_CONF, b, "records")
        assert resolved is True
        assert not os.path.exists(os.path.join(ptos.BASE_DIR, REC_CONF))

    def test_same_id_candidate_has_no_default_action(self):
        old = "2026-01-01 type=expense id=abc amount=10"
        new = "2026-01-01 type=expense id=abc amount=99"
        _write(REC_ORIG, [old])
        _write(REC_CONF, [new])
        d = ptos.diff_records_conflict(REC_ORIG, REC_CONF)
        assert d["edit_conflicts"] == [(old, new)]
        assert d["lines_only_in_conflict"] == [new]
        # nothing changes until an explicit action is taken
        assert _read(REC_ORIG) == [old]


class TestTodoMultiset:
    def test_todo_duplicates_survive_and_add(self):
        line = "Call bob"
        _write(TODO_ORIG, [line])
        _write(TODO_CONF, [line, line])
        d = ptos.diff_todos_conflict(TODO_ORIG, TODO_CONF)
        assert [t.raw_line for t in d["only_in_conflict"]] == [line]
        ptos.import_all_conflict(TODO_ORIG, TODO_CONF, "todo")
        assert _read(TODO_ORIG).count(line) == 2


class TestRandomUnionProperty:
    def test_add_all_yields_the_multiset_union(self):
        rng = random.Random(20261009)
        alphabet = [f"2026-01-0{d} type=expense amount={a}"
                    for d in (1, 2, 3) for a in (10, 20, 30)]
        for _ in range(60):
            orig = [rng.choice(alphabet) for _ in range(rng.randint(0, 6))]
            conf = [rng.choice(alphabet) for _ in range(rng.randint(0, 6))]
            _write(REC_ORIG, orig)
            _write(REC_CONF, conf)
            before = Counter(orig)
            ptos.import_all_conflict(REC_ORIG, REC_CONF, "records")
            after = Counter(_read(REC_ORIG))
            assert after == before + (Counter(conf) - before)
            for line, count in before.items():
                assert after[line] >= count
            assert not os.path.exists(os.path.join(ptos.BASE_DIR, REC_CONF))
