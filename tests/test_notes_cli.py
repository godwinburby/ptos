import os
import re
import pytest
import ptos
import ptos_cli


def _write_note(rel, content):
    full = os.path.join(ptos.NOTES_DIR, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def _read(rel):
    with open(os.path.join(ptos.NOTES_DIR, rel), encoding="utf-8") as f:
        return f.read()


def _run(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["ptos"] + list(argv))
    ptos_cli.main()


class TestNotesCliList:
    def test_root_empty(self, monkeypatch, capsys):
        _run(monkeypatch, "--notes", "list")
        out = capsys.readouterr().out
        assert "notes (root)" in out
        assert "(empty)" in out

    def test_shows_folders_and_files(self, monkeypatch, capsys):
        _write_note("alpha.md", "hi")
        _write_note("work/log.md", "hi")
        _run(monkeypatch, "--notes", "list")
        out = capsys.readouterr().out
        assert "alpha.md" in out
        assert "work/" in out

    def test_subfolder(self, monkeypatch, capsys):
        _write_note("work/log.md", "hi")
        _run(monkeypatch, "--notes", "list", "work")
        out = capsys.readouterr().out
        assert "log.md" in out

    def test_shows_template_md(self, monkeypatch, capsys):
        _write_note("work/template.md", "# tpl")
        _write_note("work/log.md", "hi")
        _run(monkeypatch, "--notes", "list", "work")
        out = capsys.readouterr().out
        assert "template.md" in out
        assert "log.md" in out


class TestNotesCliNew:
    def test_requires_name(self, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, "--notes", "new", "")
        assert "needs a file name" in str(exc.value.code)

    def test_explicit_content(self, monkeypatch, capsys):
        _run(monkeypatch, "--notes", "new", "", "--name", "hello",
              "--content", "# Hi\nbody")
        assert "# Hi" in _read("hello.md")
        assert "body" in _read("hello.md")
        assert "Note created: hello.md" in capsys.readouterr().out

    def test_without_content_starts_blank(self, monkeypatch):
        _run(monkeypatch, "--notes", "new", "", "--name", "blank")
        assert _read("blank.md") == ""

    def test_applies_local_template_silently(self, monkeypatch):
        _write_note("proj/template.md", "# Project\n")
        _run(monkeypatch, "--notes", "new", "proj", "--name", "meeting")
        assert _read("proj/meeting.md") == "# Project\n"

    def test_parent_template_prompts_non_tty_blank(self, monkeypatch):
        _write_note("proj/template.md", "# Project\n")
        os.makedirs(os.path.join(ptos.NOTES_DIR, "proj", "sub"), exist_ok=True)
        _run(monkeypatch, "--notes", "new", "proj/sub", "--name", "note")
        assert _read("proj/sub/note.md") == ""

    def test_auto_appends_md(self, monkeypatch):
        _run(monkeypatch, "--notes", "new", "", "--name", "bare", "--content", "x")
        assert _read("bare.md") == "x"


class TestNotesCliTemplate:
    def test_local_template(self, monkeypatch, capsys):
        _write_note("proj/template.md", "# Project note\nbody\n")
        _run(monkeypatch, "--notes", "template", "proj")
        out = capsys.readouterr().out
        assert "local template.md" in out
        assert "body" in out

    def test_parent_template_choice(self, monkeypatch, capsys):
        _write_note("proj/template.md", "# Project note\n")
        os.makedirs(os.path.join(ptos.NOTES_DIR, "proj", "sub"), exist_ok=True)
        _run(monkeypatch, "--notes", "template", "proj/sub")
        out = capsys.readouterr().out
        assert "nearest parent 'proj'" in out

    def test_no_template_hint(self, monkeypatch, capsys):
        _run(monkeypatch, "--notes", "template", "nope")
        assert "start blank" in capsys.readouterr().out


class TestNotesCliRead:
    def test_prints_content_and_backlinks(self, monkeypatch, capsys):
        _write_note("target.md", "# T\ncontent here\n")
        _write_note("other.md", "links [[target]] here\n")
        _run(monkeypatch, "--notes", "read", "target.md")
        out = capsys.readouterr().out
        assert "content here" in out
        assert "Backlinks" in out
        assert "other.md" in out

    def test_missing_exits(self, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, "--notes", "read", "nope.md")
        assert "not found" in str(exc.value.code)


class TestNotesCliDelete:
    def test_warns_and_cancels_non_tty(self, monkeypatch, capsys):
        _write_note("target.md", "t\n")
        _write_note("other.md", "[[target]]\n")
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, "--notes", "delete", "target.md")
        out = capsys.readouterr().out
        assert "reference(s)" in out
        assert "Delete cancelled" in str(exc.value.code)
        assert os.path.exists(os.path.join(ptos.NOTES_DIR, "target.md"))

    def test_force_deletes(self, monkeypatch):
        _write_note("target.md", "t\n")
        _write_note("other.md", "[[target]]\n")
        _run(monkeypatch, "--notes", "delete", "target.md", "--force")
        assert not os.path.exists(os.path.join(ptos.NOTES_DIR, "target.md"))

    def test_no_backlinks_deletes(self, monkeypatch):
        _write_note("solo.md", "t\n")
        _run(monkeypatch, "--notes", "delete", "solo.md")
        assert not os.path.exists(os.path.join(ptos.NOTES_DIR, "solo.md"))

    def test_missing_exits(self, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, "--notes", "delete", "nope.md")
        assert "not found" in str(exc.value.code)


class TestNotesCliId:
    def test_generates_and_persists(self, monkeypatch, capsys):
        _write_note("n.md", "# N\n")
        _run(monkeypatch, "--notes", "id", "n.md")
        out = capsys.readouterr().out.strip()
        assert re.fullmatch(r"[abcdefghjkmnpqrstuvwxyz23456789]+", out)
        assert f"ptos-id: {out}" in _read("n.md").splitlines()[0]

    def test_existing_id_returned(self, monkeypatch, capsys):
        _write_note("n.md", "<!-- ptos-id: abc123 -->\n# N\n")
        _run(monkeypatch, "--notes", "id", "n.md")
        assert capsys.readouterr().out.strip() == "abc123"


class TestNotesCliMisc:
    def test_unknown_action_exits(self, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, "--notes", "frob", "x")
        assert "Unknown --notes action" in str(exc.value.code)

    def test_missing_path_exits(self, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, "--notes", "read")
        assert "missing path argument" in str(exc.value.code)

    def test_empty_usage_exits(self, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, "--notes")
        assert "Usage: ptos --notes" in str(exc.value.code)