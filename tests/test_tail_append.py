"""Tests for the append-only fast writer (append_line_fast) and the
stale-signature/cache protections it forces (H1).

Fast appends open with O_APPEND and write the whole line in one os.write, so
concurrent writers queue at the true end of file instead of racing a
read-modify-write. The file is never truncated and trailing bytes are never
deleted; a torn tail (no trailing newline) is isolated by a leading "\\n"
written before the new line. Tests cover the two-process race, a reader
scanning during appends, rollback of failed/partial writes, CRLF/mixed
endings, parity with the old read-rewrite writer, physical lineno semantics,
and the file-level lint warning for leftover fragments.
"""

import os
import subprocess
import sys
import threading
import time
from collections import Counter

import pytest

import ptos
import ptos_todo

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rec_path(*parts):
    return os.path.join(ptos.RECORDS_DIR, *parts)


def _write_records_file(name, content_bytes):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    path = _rec_path(name)
    with open(path, "wb") as f:
        f.write(content_bytes)
    return path


def _read(path):
    if not os.path.isabs(path):
        path = os.path.join(ptos.RECORDS_DIR, path)
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(autouse=True)
def _clear_caches():
    yield
    ptos._CACHE.clear()
    ptos_todo._TODO_LOAD_CACHE.clear()


class TestAppendLineFast:
    def test_missing_file_created(self):
        path = os.path.join(ptos.RECORDS_DIR, "2026.log")
        ptos.append_line_fast(path, "2026-10-12 type=a x=1")
        assert _read(path) == "2026-10-12 type=a x=1\n"

    def test_empty_file_gets_single_line(self):
        path = _write_records_file("2026.log", b"")
        ptos.append_line_fast(path, "2026-10-12 type=a x=1")
        assert _read(path) == "2026-10-12 type=a x=1\n"

    def test_normal_appends(self):
        path = _write_records_file("2026.log", b"2026-10-01 type=a x=1\n")
        ptos.append_line_fast(path, "2026-10-02 type=a x=2")
        ptos.append_line_fast(path, "2026-10-03 type=a x=3")
        assert _read(path).splitlines() == [
            "2026-10-01 type=a x=1",
            "2026-10-02 type=a x=2",
            "2026-10-03 type=a x=3",
        ]
        assert _read(path).endswith("\n")

    def test_torn_tail_isolated_never_deleted(self):
        path = _write_records_file("2026.log", b"2026-10-01 type=a x=1\nTORN-FRAGMENT")
        ptos.append_line_fast(path, "2026-10-02 type=a x=2")
        raw = open(path, "rb").read()
        assert raw == (
            b"2026-10-01 type=a x=1\n"
            b"TORN-FRAGMENT\n"
            b"2026-10-02 type=a x=2\n"
        )

    def test_torn_tail_then_more_appends_stay_clean(self):
        path = _write_records_file("2026.log", b"frag")
        for i in range(3):
            ptos.append_line_fast(path, f"2026-10-0{i} type=a x={i}")
        lines = open(path, encoding="utf-8").read().splitlines()
        assert lines == [
            "frag",
            "2026-10-00 type=a x=0",
            "2026-10-01 type=a x=1",
            "2026-10-02 type=a x=2",
        ]

    def test_trailing_blank_lines_left_in_place(self):
        path = _write_records_file("2026.log", b"A\n\n\n \n")
        ptos.append_line_fast(path, "B")
        assert open(path, "rb").read() == b"A\n\n\n \nB\n"

    def test_no_bak_or_tmp_left_behind(self, tmp_path):
        p = tmp_path / "scratch"
        p.mkdir()
        path = str(p / "2026.log")
        for i in range(5):
            ptos.append_line_fast(path, f"2026-10-0{i} type=a x={i}")
        leftovers = [x for x in os.listdir(p) if x.endswith((".bak", ".tmp"))]
        assert leftovers == []

    def test_unicode_content_round_trips(self):
        path = os.path.join(ptos.RECORDS_DIR, "2026.log")
        ptos.append_line_fast(path, '2026-10-12 type=meal note="dosa ½ plate"')
        d, kv, note = ptos.parse_line("2026-10-12 type=meal note=\"dosa ½ plate\"")
        assert note == "dosa ½ plate"

    def test_inserts_newline_only_when_tail_unterminated(self):
        path = _write_records_file("2026.log", b"first\nsecond")
        ptos.append_line_fast(path, "third")
        assert open(path, "rb").read() == b"first\nsecond\nthird\n"


class TestCrlfMix:
    def test_crlf_untouched_new_line_lf(self):
        path = _write_records_file("2026.log", b"A\r\nB\r\n")
        ptos.append_line_fast(path, "2026-10-12 type=c x=1")
        assert open(path, "rb").read() == b"A\r\nB\r\n2026-10-12 type=c x=1\n"

    def test_mixed_endings_reparse_in_text_mode(self):
        path = _write_records_file("2026.log", b"A\r\nB\nC\r\n")
        ptos.append_line_fast(path, "2026-10-12 type=c x=1")
        lines = open(path, encoding="utf-8").read().split("\n")
        assert lines[-2] == "2026-10-12 type=c x=1"
        parsed = ptos._parsed_file("2026.log")
        assert [r[4] for r in parsed] == ["2026-10-12 type=c x=1"]


class TestRollback:
    def _hook(self, writer):
        old = ptos._os_write

        def wrapped(fd, payload):
            ptos._os_write = old
            return writer(fd, payload)

        ptos._os_write = wrapped
        return old

    def test_short_write_rolls_back(self):
        path = _write_records_file("2026.log", b"A line\n")
        before = open(path, "rb").read()
        old = ptos._os_write

        def short(fd, payload):
            return old(fd, payload[:3])

        self._hook(short)
        with pytest.raises(OSError, match="wrote 3 of"):
            ptos.append_line_fast(path, "B line that is longer")
        assert open(path, "rb").read() == before
        ptos.append_line_fast(path, "recovered")
        assert open(path, "rb").read() == b"A line\nrecovered\n"

    def test_exception_after_partial_write_rolls_back_own_fragment(self):
        path = _write_records_file("2026.log", b"A line\n")
        before = open(path, "rb").read()
        old = ptos._os_write

        def boom(fd, payload):
            old(fd, payload[:4])
            raise OSError("disk full")

        self._hook(boom)
        with pytest.raises(OSError):
            ptos.append_line_fast(path, "ZZZ another line")
        assert open(path, "rb").read() == before

    def test_exception_skips_rollback_when_foreign_bytes_landed(self):
        path = _write_records_file("2026.log", b"base\n")
        old = ptos._os_write

        def boom(fd, payload):
            old(fd, payload[:4])
            old(fd, b"foreign\n")
            raise OSError("disk full")

        self._hook(boom)
        with pytest.raises(OSError):
            ptos.append_line_fast(path, "WWW fail line")
        raw = open(path, "rb").read()
        assert raw.startswith(b"base\nWWW foreign\n")
        ptos.append_line_fast(path, "final")
        lines = open(path, "rb").read().splitlines()
        assert lines[-1] == b"final"

    def test_read_only_failures_leave_file_untouched(self):
        path = _write_records_file("2026.log", b"A line\n")
        before = open(path, "rb").read()

        def fail(fd, payload):
            raise OSError("denied")

        self._hook(fail)
        with pytest.raises(OSError):
            ptos.append_line_fast(path, "nope")
        assert open(path, "rb").read() == before


class TestAppendRecordFastPath:
    def test_appends_to_correct_file(self):
        line = "2026-10-12 type=expense amount=5"
        ptos.append_record(line)
        assert _read("2026.log") == line + "\n"

    def test_still_refuses_line_breaks(self):
        with pytest.raises(ptos.PTOSError):
            ptos.append_record("2026-10-12 type=a\nb")

    def test_still_refuses_unparseable(self):
        with pytest.raises(ptos.PTOSError):
            ptos.append_record("just some words with no date")

    def test_return_position_fresh_file_is_zero(self):
        path, lineno = ptos.append_record(
            "2026-10-12 type=expense amount=1", return_position=True)
        assert path == _rec_path("2026.log")
        assert lineno == 0

    def test_return_position_multi_line(self):
        for i in range(3):
            path, lineno = ptos.append_record(
                f"2026-10-1{i} type=expense amount={i}", return_position=True)
        assert lineno == 2

    def test_return_position_physical_index_with_trailing_blanks(self):
        _write_records_file("2026.log", b"2026-10-01 type=a amt=1\n\n\n")
        path, lineno = ptos.append_record(
            "2026-10-12 type=a amt=2", return_position=True)
        assert lineno == 3
        assert _read(path).splitlines()[3] == "2026-10-12 type=a amt=2"

    def test_return_position_physical_index_with_torn_tail(self):
        _write_records_file("2026.log", b"2026-10-01 type=a amt=1\nfrag")
        path, lineno = ptos.append_record(
            "2026-10-12 type=a amt=2", return_position=True)
        assert lineno == 2
        assert _read(path).splitlines()[2] == "2026-10-12 type=a amt=2"

    def test_no_bak_tmp_in_records_dir(self):
        ptos.append_record("2026-10-12 type=expense amount=1")
        ptos.append_record("2026-10-13 type=expense amount=2")
        leftovers = [
            x for x in os.listdir(ptos.RECORDS_DIR)
            if x.endswith((".bak", ".tmp")) or ".bak" in x
        ]
        assert leftovers == []

    def test_new_year_file_still_refreshes_log_files_cache(self):
        ptos.append_record("2025-12-31 type=expense amount=1")
        ptos.append_record("2026-01-01 type=expense amount=2")
        assert "2025.log" in ptos.get_log_files()
        assert "2026.log" in ptos.get_log_files()


class TestTwoProcessRace:
    CHILD = (
        "import sys, ptos\n"
        "path, tag, n = sys.argv[1], sys.argv[2], int(sys.argv[3])\n"
        "for i in range(n):\n"
        "    ptos.append_line_fast(path, f'2026-10-12 type=race id={tag}-{i:04d}')\n"
    )

    def test_zero_lines_lost_under_two_writers(self):
        path = os.path.join(ptos.RECORDS_DIR, "2026.log")
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", self.CHILD, path, tag, "200"],
                cwd=REPO_ROOT,
            )
            for tag in ("px", "py")
        ]
        for p in procs:
            assert p.wait() == 0
        lines = open(path, encoding="utf-8").read().splitlines()
        assert len(lines) == 400
        expected = [
            f"2026-10-12 type=race id={tag}-{i:04d}"
            for tag in ("px", "py") for i in range(200)
        ]
        assert Counter(lines) == Counter(expected)

    def test_zero_lines_lost_many_small_batches(self):
        path = os.path.join(ptos.RECORDS_DIR, "2026.log")
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", self.CHILD, path, tag, "50"],
                cwd=REPO_ROOT,
            )
            for tag in ("pa", "pb", "pc", "pd")
        ]
        for p in procs:
            assert p.wait() == 0
        lines = open(path, encoding="utf-8").read().splitlines()
        assert len(lines) == 200


class TestReaderDuringAppends:
    """H1: scans during in-place appends never serve a parseable-but-wrong
    row, and never cache a torn read under the finished file's signature."""

    def test_reader_never_serves_torn_rows(self):
        path = _write_records_file("2026.log", b"seed\n")
        stop = threading.Event()
        served = []
        errors = []

        def writer():
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_BINARY)
            try:
                for i in range(400):
                    part1 = f"2026-10-12 type=scan n={i:04d} ".encode()
                    part2 = b"done\n"
                    # Deliberately split the line across two writes with a
                    # pause so readers observe a fully-parseable fragment
                    # (n="...", no 'done') mid-write.
                    os.write(fd, part1)
                    time.sleep(0.0005)
                    os.write(fd, part2)
            finally:
                os.close(fd)
                stop.set()

        def reader():
            while not stop.is_set():
                try:
                    for _idx, _d, _kv, _note, line in ptos._parsed_file("2026.log"):
                        served.append(line)
                except Exception as exc:  # pragma: no cover
                    errors.append(exc)

        wt = threading.Thread(target=writer)
        rt = threading.Thread(target=reader)
        wt.start()
        rt.start()
        wt.join()
        rt.join()
        assert errors == []
        assert served, "reader never observed an append window"
        final = {
            line.strip() for line in open(path, encoding="utf-8").read().split("\n")
            if line.strip()
        }
        for line in served:
            assert line in final, f"served a torn/foreign row: {line!r}"
            assert line.endswith("done")
        final_rows = ptos._parsed_file("2026.log")
        assert len(final_rows) == 400

    def test_empty_during_flap_self_heals(self):
        path = _write_records_file(
            "2026.log", b"2026-10-01 type=expense amount=1\n"
                        b"2026-10-02 type=expense amount=2\n"
        )
        assert [r[4] for r in ptos._parsed_file("2026.log")] == [
            "2026-10-01 type=expense amount=1",
            "2026-10-02 type=expense amount=2",
        ]
        ptos.append_line_fast(path, "2026-10-03 type=expense amount=3")
        assert [r[4] for r in ptos._parsed_file("2026.log")] == [
            "2026-10-01 type=expense amount=1",
            "2026-10-02 type=expense amount=2",
            "2026-10-03 type=expense amount=3",
        ]


class TestLoadTodosBracket:
    def test_add_todo_reflected_immediately(self, tmp_path):
        path = str(tmp_path / "todo.txt")
        t = ptos_todo.add_todo(path, "Call supplier +HearingCare due:2026-10-12")
        todos, errors = ptos_todo.load_todos(path)
        assert errors == []
        assert [x.description for x in todos] == ["Call supplier"]

    def test_reader_never_serves_torn_todo(self, tmp_path):
        path = str(tmp_path / "todo.txt")
        ptos_todo.add_todo(path, "(A) seed task +p")
        stop = threading.Event()
        served = []

        def writer():
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_BINARY)
            try:
                for i in range(300):
                    os.write(fd, f"(B) task number {i:04d} +p ".encode())
                    time.sleep(0.0005)
                    os.write(fd, b"END\n")
            finally:
                os.close(fd)
                stop.set()

        def reader():
            while not stop.is_set():
                todos, _ = ptos_todo.load_todos(path)
                for t in todos:
                    served.append(t.description)

        wt = threading.Thread(target=writer)
        rt = threading.Thread(target=reader)
        wt.start()
        rt.start()
        wt.join()
        rt.join()
        assert served
        for desc in served:
            if desc.startswith("task number"):
                assert desc.endswith("END"), f"served torn todo: {desc!r}"


class TestParityWithOldWriter:
    def _old_append(self, path, line):
        # Model of the pre-append-only writer's *logical* behaviour: read
        # everything, strip trailing whitespace once, append the line. Written
        # in binary so the comparison is about content, not the historical
        # text-mode CRLF translation on Windows.
        with open(path, "rb") as f:
            existing = f.read()
        stripped = existing.rstrip(b"\n\r ")
        new = stripped + b"\n" + line.encode() + b"\n" if stripped != existing \
            else existing + line.encode() + b"\n"
        with open(path, "wb") as f:
            f.write(new)

    def test_well_formed_file_same_logical_rows(self):
        new_path = _write_records_file("2026.log", b"")
        old_path = _write_records_file("old.log", b"")
        lines = [
            "2026-10-01 type=expense amount=1",
            "2026-10-02 type=expense amount=2",
            "2026-10-03 type=expense amount=3",
            "2026-10-04 type=expense amount=4",
            "2026-10-05 type=expense amount=5",
        ]
        for line in lines:
            ptos.append_line_fast(new_path, line)
            self._old_append(old_path, line)
        assert _read(new_path).splitlines() == _read(old_path).splitlines()
        if os.linesep == "\n":
            assert open(new_path, "rb").read() == open(old_path, "rb").read()

    def test_parsed_record_sets_match_for_trailing_blank_files(self):
        new_path = _write_records_file(
            "2026.log", b"2026-09-01 type=expense amount=1\n\n\n"
        )
        old_src = _write_records_file(
            "old.log", b"2026-09-01 type=expense amount=1\n\n\n"
        )
        for line in ("2026-10-11 type=expense amount=2",
                     "2026-10-12 type=expense amount=3"):
            ptos.append_line_fast(new_path, line)
            self._old_append(old_src, line)
        new_rows = [r[4] for r in ptos._parsed_file("2026.log")]
        old_rows = []
        with open(old_src, encoding="utf-8") as f:
            for raw in f:
                l = raw.strip()
                if not l or l.startswith("#"):
                    continue
                old_rows.append(l)
        assert new_rows == [
            "2026-09-01 type=expense amount=1",
            "2026-10-11 type=expense amount=2",
            "2026-10-12 type=expense amount=3",
        ]
        assert old_rows == new_rows
        assert open(new_path, "rb").read() != open(old_src, "rb").read()


class TestLintFragmentWarning:
    def test_unterminated_tail_warns(self, tmp_path):
        _write_records_file("2026.log", b"2026-05-05 type=expense amount=5")
        assert ptos.find_unterminated_tail_files() == [("2026.log", 1)]
        result = ptos.lint_all_records()
        assert result["warning_count"] >= 1
        frag = [w for w in result["warnings"]
                if "does not end with a newline" in w["problems"][0]]
        assert len(frag) == 1
        assert frag[0]["filepath"] == "2026.log"
        assert frag[0]["lineno"] == 1
        assert result["clean"] is False

    def test_terminated_file_no_warning(self):
        _write_records_file("2026.log", b"2026-05-05 type=expense amount=5\n")
        assert ptos.find_unterminated_tail_files() == []
        result = ptos.lint_all_records()
        assert not any("does not end with a newline" in w["problems"][0]
                       for w in result["warnings"])

    def test_find_skips_missing_and_empty_files(self):
        assert ptos.find_unterminated_tail_files() == []
        _write_records_file("2026.log", b"")
        assert ptos.find_unterminated_tail_files() == []