import os
import ptos
import pytest


class TestGetNoteTemplate:
    def test_daily_template(self):
        content = ptos.get_note_template("daily", {"date": "2026-07-21"})
        assert "2026-07-21" in content

    def test_unknown_category(self):
        content = ptos.get_note_template("unknown", {"title": "Hello"})
        assert "Hello" in content

    def test_starter_note_template(self):
        content = ptos.get_note_template("meeting", {"title": "Standup", "date": "2026-07-21"})
        assert "Standup" in content
        assert "2026-07-21" in content

    def test_category_specific_takes_priority(self):
        cat_dir = os.path.join(ptos.TEMPLATE_DIR)
        os.makedirs(cat_dir, exist_ok=True)
        with open(os.path.join(cat_dir, "meeting.md"), "w", encoding="utf-8") as f:
            f.write("# MEETING: {{title}}\n")
        content = ptos.get_note_template("meeting", {"title": "Standup"})
        assert content == "# MEETING: Standup\n"

    def test_falls_back_to_note_template(self):
        os.makedirs(os.path.join(ptos.TEMPLATE_DIR), exist_ok=True)
        with open(os.path.join(ptos.TEMPLATE_DIR, "note.md"), "w", encoding="utf-8") as f:
            f.write("# Generic: {{title}}\n")
        content = ptos.get_note_template("nonexistent", {"title": "Test"})
        assert content == "# Generic: Test\n"

    def test_falls_back_to_starter_category(self):
        os.makedirs(os.path.join(ptos.TEMPLATE_DIR), exist_ok=True)
        note_path = os.path.join(ptos.TEMPLATE_DIR, "note.md")
        if os.path.exists(note_path):
            os.remove(note_path)
        content = ptos.get_note_template("book", {"title": "My Book"})
        assert "My Book" in content

    def test_falls_back_to_starter_note(self):
        os.makedirs(os.path.join(ptos.TEMPLATE_DIR), exist_ok=True)
        for f in ["note.md", "book.md"]:
            p = os.path.join(ptos.TEMPLATE_DIR, f)
            if os.path.exists(p):
                os.remove(p)
        content = ptos.get_note_template("unknown", {"title": "X"})
        assert "X" in content


class TestGetJournalTemplateContent:
    def test_returns_template_without_writing(self):
        content = ptos.get_journal_template_content("2026-07-21")
        assert "2026-07-21" in content
        year_dir = os.path.join(ptos.JOURNAL_DIR, "2026")
        path = os.path.join(year_dir, "2026-07-21.md")
        assert not os.path.exists(path)


class TestSlugify:
    def test_basic(self):
        assert ptos.slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert ptos.slugify("Notes & Stuff!") == "notes-stuff"

    def test_multiple_dashes(self):
        result = ptos.slugify("a  --  b")
        assert "--" not in result
        assert result == "a-b"

    def test_strip_edges(self):
        assert ptos.slugify(" hello ") == "hello"


class TestLinkCandidates:
    def test_bracket_links_in_notes(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "NOTES_DIR", str(tmp_path / "notes"))
        notes_dir = tmp_path / "notes" / "project"
        notes_dir.mkdir(parents=True)
        (notes_dir / "note.md").write_text("# Note\n\nRead [[Atomic Habits]] today\n")
        from ptos_web import app
        client = app.test_client()
        monkeypatch.setattr(ptos, "JOURNAL_DIR", str(tmp_path / "journal"))
        monkeypatch.setattr(ptos, "TODO_DIR", str(tmp_path / "todo"))
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        tmp_path / "todo" / "todo.txt"
        tmp_path / "todo" / "done.txt"
        tmp_path / "records"
        resp = client.get("/api/link-candidates?q=atomic")
        data = resp.get_json()
        assert "Atomic Habits" in data

    def test_bracket_links_in_journal(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "NOTES_DIR", str(tmp_path / "notes"))
        monkeypatch.setattr(ptos, "JOURNAL_DIR", str(tmp_path / "journal"))
        monkeypatch.setattr(ptos, "TODO_DIR", str(tmp_path / "todo"))
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        (tmp_path / "notes").mkdir()
        journal_dir = tmp_path / "journal" / "2026" / "07"
        journal_dir.mkdir(parents=True)
        (journal_dir / "2026-07-22.md").write_text("Today I [[buy house]] plans\n")
        (tmp_path / "todo").mkdir()
        (tmp_path / "records").mkdir()
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/link-candidates?q=buy")
        data = resp.get_json()
        assert "buy house" in data

    def test_multi_word_phrases(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "NOTES_DIR", str(tmp_path / "notes"))
        monkeypatch.setattr(ptos, "JOURNAL_DIR", str(tmp_path / "journal"))
        monkeypatch.setattr(ptos, "TODO_DIR", str(tmp_path / "todo"))
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        (tmp_path / "notes").mkdir()
        journal_dir = tmp_path / "journal" / "2026" / "07"
        journal_dir.mkdir(parents=True)
        (journal_dir / "2026-07-22.md").write_text("[[fitting]] session done\n")
        (tmp_path / "todo").mkdir()
        (tmp_path / "records").mkdir()
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/link-candidates?q=fitting")
        data = resp.get_json()
        assert "fitting" in data

    def test_todo_projects_in_candidates(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "NOTES_DIR", str(tmp_path / "notes"))
        monkeypatch.setattr(ptos, "JOURNAL_DIR", str(tmp_path / "journal"))
        todo_dir = tmp_path / "todo"
        monkeypatch.setattr(ptos, "TODO_DIR", str(todo_dir))
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_dir / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(todo_dir / "done.txt"))
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        (tmp_path / "notes").mkdir()
        (tmp_path / "journal").mkdir()
        (tmp_path / "records").mkdir()
        todo_dir.mkdir()
        (todo_dir / "todo.txt").write_text("Task +HearSpeechPro\n")
        (todo_dir / "done.txt").write_text("")
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/link-candidates?q=hearspeechpro")
        data = resp.get_json()
        assert "HearSpeechPro" in data

    def test_record_project_context(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "NOTES_DIR", str(tmp_path / "notes"))
        monkeypatch.setattr(ptos, "JOURNAL_DIR", str(tmp_path / "journal"))
        monkeypatch.setattr(ptos, "TODO_DIR", str(tmp_path / "todo"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo" / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "todo" / "done.txt"))
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        (tmp_path / "notes").mkdir()
        (tmp_path / "journal").mkdir()
        (tmp_path / "todo").mkdir()
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        (records_dir / "2026.log").write_text(
            "type=expense domain=self category=food amount=100 project=Fit context=work\n"
            "type=expense domain=self category=food amount=200 project=Fit context=home\n"
        )
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/link-candidates?q=fit")
        data = resp.get_json()
        assert "Fit" in data
        resp2 = client.get("/api/link-candidates?q=work")
        data2 = resp2.get_json()
        assert "work" in data2

    def test_no_noise_from_pure_numbers(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "NOTES_DIR", str(tmp_path / "notes"))
        monkeypatch.setattr(ptos, "JOURNAL_DIR", str(tmp_path / "journal"))
        monkeypatch.setattr(ptos, "TODO_DIR", str(tmp_path / "todo"))
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        (tmp_path / "notes").mkdir()
        journal_dir = tmp_path / "journal" / "2026" / "07"
        journal_dir.mkdir(parents=True)
        (journal_dir / "2026-07-22.md").write_text("Spent 11500 on [[buy house]]\n")
        (tmp_path / "todo").mkdir()
        (tmp_path / "records").mkdir()
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/link-candidates?q=115")
        data = resp.get_json()
        assert "11500" not in data


class TestSafePath:
    def test_empty_returns_notes_dir(self):
        assert ptos._safe_path("") == ptos.NOTES_DIR

    def test_normal_path(self):
        result = ptos._safe_path("folder/file.md")
        assert result.startswith(os.path.abspath(ptos.NOTES_DIR))
        assert "folder/file.md" in result.replace("\\", "/")

    def test_rejects_dotdot(self):
        with pytest.raises(ptos.PTOSError, match="Invalid path"):
            ptos._safe_path("../etc/passwd")

    def test_rejects_absolute(self):
        with pytest.raises(ptos.PTOSError, match="Invalid path"):
            ptos._safe_path("/etc/passwd")

    def test_rejects_windows_absolute(self):
        with pytest.raises(ptos.PTOSError, match="Invalid path"):
            ptos._safe_path("C:\\Windows\\System32")


class TestValidateName:
    def test_rejects_empty(self):
        with pytest.raises(ptos.PTOSError, match="Invalid name"):
            ptos._validate_name("")

    def test_rejects_slash(self):
        with pytest.raises(ptos.PTOSError, match="Invalid name"):
            ptos._validate_name("foo/bar")

    def test_rejects_backslash(self):
        with pytest.raises(ptos.PTOSError, match="Invalid name"):
            ptos._validate_name("foo\\bar")

    def test_rejects_dot(self):
        with pytest.raises(ptos.PTOSError, match="Invalid name"):
            ptos._validate_name(".")

    def test_rejects_dotdot(self):
        with pytest.raises(ptos.PTOSError, match="Invalid name"):
            ptos._validate_name("..")

    def test_valid_name(self):
        ptos._validate_name("my-note.md")


class TestListDir:
    def test_empty_dir(self):
        result = ptos.list_dir("")
        assert result == {"folders": [], "files": []}

    def test_folders_and_files(self):
        os.makedirs(os.path.join(ptos.NOTES_DIR, "sub"))
        with open(os.path.join(ptos.NOTES_DIR, "readme.md"), "w") as f:
            f.write("# Notes")
        result = ptos.list_dir("")
        assert len(result["folders"]) == 1
        assert result["folders"][0]["name"] == "sub"
        assert len(result["files"]) == 1
        assert result["files"][0]["name"] == "readme.md"

    def test_template_md_is_shown(self):
        with open(os.path.join(ptos.NOTES_DIR, "template.md"), "w") as f:
            f.write("tpl")
        result = ptos.list_dir("")
        assert len(result["files"]) == 1
        assert result["files"][0]["name"] == "template.md"

    def test_nested_rel_path(self):
        os.makedirs(os.path.join(ptos.NOTES_DIR, "a", "b"))
        result = ptos.list_dir("a")
        assert len(result["folders"]) == 1
        assert result["folders"][0]["rel_path"] == "a/b"

    def test_nonexistent_folder(self):
        with pytest.raises(ptos.PTOSError, match="Folder not found"):
            ptos.list_dir("nope")

    def test_ignores_non_md_files(self):
        with open(os.path.join(ptos.NOTES_DIR, "data.txt"), "w") as f:
            f.write("txt")
        result = ptos.list_dir("")
        assert len(result["files"]) == 0


class TestCreateFolder:
    def test_creates_folder(self):
        ptos.create_folder("", "projects")
        assert os.path.isdir(os.path.join(ptos.NOTES_DIR, "projects"))

    def test_rejects_duplicate(self):
        ptos.create_folder("", "dup")
        with pytest.raises(ptos.PTOSError, match="already exists"):
            ptos.create_folder("", "dup")

    def test_rejects_bad_name(self):
        with pytest.raises(ptos.PTOSError, match="Invalid name"):
            ptos.create_folder("", "../escape")


class TestCreateFile:
    def test_creates_file(self):
        ptos.create_file("", "notes.md", "# Hello")
        assert os.path.isfile(os.path.join(ptos.NOTES_DIR, "notes.md"))
        with open(os.path.join(ptos.NOTES_DIR, "notes.md")) as f:
            assert f.read() == "# Hello"

    def test_auto_appends_md(self):
        ptos.create_file("", "readme", "content")
        assert os.path.isfile(os.path.join(ptos.NOTES_DIR, "readme.md"))

    def test_rejects_existing(self):
        ptos.create_file("", "dup.md", "first")
        with pytest.raises(ptos.PTOSError, match="already exists"):
            ptos.create_file("", "dup.md", "second")

    def test_creates_parent_dirs(self):
        ptos.create_file("sub/dir", "file.md", "content")
        assert os.path.isfile(os.path.join(ptos.NOTES_DIR, "sub", "dir", "file.md"))

    def test_rejects_bad_name(self):
        with pytest.raises(ptos.PTOSError, match="Invalid name"):
            ptos.create_file("", "bad/name.md", "x")


class TestRename:
    def test_rename_file(self):
        with open(os.path.join(ptos.NOTES_DIR, "old.md"), "w") as f:
            f.write("content")
        ptos.rename_note("old.md", "new.md")
        assert os.path.isfile(os.path.join(ptos.NOTES_DIR, "new.md"))
        assert not os.path.exists(os.path.join(ptos.NOTES_DIR, "old.md"))

    def test_rename_folder(self):
        os.makedirs(os.path.join(ptos.NOTES_DIR, "old_folder"))
        ptos.rename_note("old_folder", "new_folder")
        assert os.path.isdir(os.path.join(ptos.NOTES_DIR, "new_folder"))
        assert not os.path.exists(os.path.join(ptos.NOTES_DIR, "old_folder"))

    def test_rejects_existing_target(self):
        with open(os.path.join(ptos.NOTES_DIR, "a.md"), "w") as f:
            f.write("a")
        with open(os.path.join(ptos.NOTES_DIR, "b.md"), "w") as f:
            f.write("b")
        with pytest.raises(ptos.PTOSError, match="already exists"):
            ptos.rename_note("a.md", "b.md")


class TestDeleteEntry:
    def test_delete_file(self):
        with open(os.path.join(ptos.NOTES_DIR, "del.md"), "w") as f:
            f.write("bye")
        ptos.delete_note_entry("del.md")
        assert not os.path.exists(os.path.join(ptos.NOTES_DIR, "del.md"))

    def test_delete_folder_recursive(self):
        d = os.path.join(ptos.NOTES_DIR, "folder")
        os.makedirs(os.path.join(d, "sub"))
        with open(os.path.join(d, "file.md"), "w") as f:
            f.write("x")
        with open(os.path.join(d, "sub", "inner.md"), "w") as f:
            f.write("y")
        ptos.delete_note_entry("folder")
        assert not os.path.exists(d)

    def test_delete_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            ptos.delete_note_entry("nope.md")


class TestFindParentTemplate:
    def test_local_template_exists(self):
        os.makedirs(os.path.join(ptos.NOTES_DIR, "clinic"))
        with open(os.path.join(ptos.NOTES_DIR, "clinic", "template.md"), "w") as f:
            f.write("# Clinic note")
        result = ptos.find_parent_template("clinic/sub")
        assert result is not None
        assert result["rel_path"] == "clinic"
        assert "# Clinic note" in result["content"]

    def test_no_template_anywhere(self):
        result = ptos.find_parent_template("empty")
        assert result is None

    def test_root_template(self):
        with open(os.path.join(ptos.NOTES_DIR, "template.md"), "w") as f:
            f.write("# Root template")
        result = ptos.find_parent_template("deep/nested/folder")
        assert result is not None
        assert result["rel_path"] == "."


class TestResolveNewFileTemplate:
    def test_local_template(self):
        os.makedirs(os.path.join(ptos.NOTES_DIR, "myfolder"))
        with open(os.path.join(ptos.NOTES_DIR, "myfolder", "template.md"), "w") as f:
            f.write("# Local tpl")
        result = ptos.resolve_new_file_template("myfolder")
        assert result["source"] == "local"
        assert "# Local tpl" in result["content"]

    def test_parent_template(self):
        os.makedirs(os.path.join(ptos.NOTES_DIR, "parent"))
        with open(os.path.join(ptos.NOTES_DIR, "parent", "template.md"), "w") as f:
            f.write("# Parent tpl")
        os.makedirs(os.path.join(ptos.NOTES_DIR, "parent", "child"))
        result = ptos.resolve_new_file_template("parent/child")
        assert result["source"] == "choice"
        assert result["parent"] is not None
        assert "# Parent tpl" in result["parent"]["content"]

    def test_no_template(self):
        result = ptos.resolve_new_file_template("bare")
        assert result["source"] == "choice"
        assert result["parent"] is None
