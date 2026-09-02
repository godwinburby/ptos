import os
import datetime as dt
import pytest
import ptos
import ptos_cli


def _write_records(line):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    with open(os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log"),
              "w", encoding="utf-8") as f:
        f.write(line + "\n")


def _write_notes(rel, content):
    full = os.path.join(ptos.NOTES_DIR, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def _write_journal(date_str, content):
    full = os.path.join(ptos.JOURNAL_DIR, date_str[:4], date_str[5:7],
                        date_str + ".md")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def _write_todo(path_name, content):
    os.makedirs(ptos.TODO_DIR, exist_ok=True)
    with open(os.path.join(ptos.TODO_DIR, path_name), "w", encoding="utf-8") as f:
        f.write(content)


def _run(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["ptos"] + list(argv))
    ptos_cli.main()


class TestCliFind:
    def test_across_all_sources(self, monkeypatch, capsys):
        _write_records("type=exercise notes=running today")
        _write_journal("2026-08-17", "went running in the park")
        _write_todo("todo.txt", "(A) jogging done today\n")
        _write_notes("log.md", "my running log\n")
        _run(monkeypatch, "--find", "running")
        out = capsys.readouterr().out
        assert "Records:" in out
        assert "Journal:" in out
        assert "Todos:" in out
        assert "Notes:" in out
        assert "3 result(s)" in out

    def test_glob_wildcard(self, monkeypatch, capsys):
        _write_notes("a.md", "stargazing notes\n")
        _run(monkeypatch, "--find", "star*")
        out = capsys.readouterr().out
        assert "a.md" in out
        assert "1 result(s)" in out

    def test_no_hits(self, monkeypatch, capsys):
        _run(monkeypatch, "--find", "zzz_nothing")
        assert "0 result(s)" in capsys.readouterr().out


class TestCliBacklinks:
    def test_finds_note_reference(self, monkeypatch, capsys):
        _write_notes("note-a.md", "see [[target]] here\n")
        _run(monkeypatch, "--backlinks", "target")
        out = capsys.readouterr().out
        assert "Backlinks (1)" in out
        assert "notes:" in out
        assert "note-a.md" in out

    def test_empty(self, monkeypatch, capsys):
        _write_notes("solo.md", "nope\n")
        _run(monkeypatch, "--backlinks", "ghost")
        assert "No backlinks." in capsys.readouterr().out


class TestCliLinkIds:
    def test_lists_record_todo_note_targets(self, monkeypatch, capsys):
        _write_records("2026-08-17 type=expense domain=self category=food amount=1 id=abc123")
        _write_todo("todo.txt", "(A) research the topic id:xyz789\n")
        _write_notes("linked-note.md", "<!-- ptos-id: noteid1 -->\n# Note\n")
        _run(monkeypatch, "--link-ids")
        out = capsys.readouterr().out
        assert "expense:abc123" in out
        assert "todo:xyz789" in out
        assert "note:noteid1" in out

    def test_empty(self, monkeypatch, capsys):
        _run(monkeypatch, "--link-ids")
        assert "No type:id targets" in capsys.readouterr().out