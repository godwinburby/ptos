"""Regression tests for the -e editor helpers and --retro-id note: each of
these paths raised NameError (tempfile / format_line / parse_todo_line /
NOTES_DIR / ensure_note_id were never imported at the point of use) and only
a call could surface it (pre-modularization spec A2)."""
import os
import sys

import pytest

import ptos
import ptos_cli
import ptos_todo


@pytest.fixture
def noop_editor(monkeypatch):
    monkeypatch.setattr(
        ptos, "resolve_editor", lambda: [sys.executable, "-c", "pass"])


@pytest.fixture
def appending_editor(tmp_path, monkeypatch):
    ed = tmp_path / "append_ed.py"
    ed.write_text(
        "import sys\n"
        "p = sys.argv[1]\n"
        "s = open(p, encoding='utf-8').read()\n"
        "open(p, 'w', encoding='utf-8').write(s + ' MARK')\n",
        encoding="utf-8")
    monkeypatch.setattr(ptos, "resolve_editor", lambda: [sys.executable, str(ed)])


class TestEditLine:
    def test_noop_editor_returns_line(self, noop_editor):
        line = '2026-01-01 type=call note="hi"'
        assert ptos_cli._edit_line(line) == line

    def test_editor_change_comes_back(self, appending_editor):
        assert ptos_cli._edit_line("original") == "original MARK"


class TestEditText:
    def test_noop_editor_returns_text(self, noop_editor):
        assert ptos_cli._edit_text("hello") == "hello"

    def test_editor_change_comes_back(self, appending_editor):
        assert ptos_cli._edit_text("hello") == "hello MARK"


class TestEditTodoLine:
    def test_round_trip_through_editor(self, noop_editor):
        t = ptos_todo.parse_todo_line("(A) buy milk +home @store")
        out = ptos_cli._edit_todo_line(t)
        assert out is not None
        assert out.priority == "A"
        assert out.description == "buy milk"
        assert "+home" in out.raw_line
        assert "@store" in out.raw_line


class TestRetroIdNote:
    def test_retro_id_note_via_cli(self, monkeypatch):
        os.makedirs(ptos.NOTES_DIR, exist_ok=True)
        note = os.path.join(ptos.NOTES_DIR, "clinic-visit.md")
        with open(note, "w", encoding="utf-8") as f:
            f.write("dentist appointment\n")
        monkeypatch.setattr(
            "sys.argv",
            ["ptos", "--retro-id", "note", "--search", "clinic-visit"])
        ptos_cli.main()
        assert ptos.note_id_of(note)

    def test_retro_id_note_missing_note_exits(self, monkeypatch, capsys):
        os.makedirs(ptos.NOTES_DIR, exist_ok=True)
        monkeypatch.setattr(
            "sys.argv", ["ptos", "--retro-id", "note", "--search", "zzz-none"])
        with pytest.raises(SystemExit) as ei:
            ptos_cli.main()
        assert "No note matching" in str(ei.value)
