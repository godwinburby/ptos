import os
import ptos
import pytest


class TestListNoteCategories:
    def test_empty(self):
        result = ptos.list_note_categories()
        assert result == []

    def test_with_categories(self):
        os.makedirs(os.path.join(ptos.NOTES_DIR, "daily"))
        os.makedirs(os.path.join(ptos.NOTES_DIR, "project"))
        os.makedirs(os.path.join(ptos.NOTES_DIR, "meeting"))
        result = ptos.list_note_categories()
        assert result == ["daily", "meeting", "project"]

    def test_ignores_files(self):
        cat_dir = os.path.join(ptos.NOTES_DIR, "daily")
        os.makedirs(cat_dir)
        with open(os.path.join(cat_dir, "test.md"), "w") as f:
            f.write("test")
        with open(os.path.join(ptos.NOTES_DIR, "stray.txt"), "w") as f:
            f.write("stray")
        result = ptos.list_note_categories()
        assert result == ["daily"]


class TestListNotes:
    def test_empty_category(self):
        os.makedirs(os.path.join(ptos.NOTES_DIR, "daily"))
        result = ptos.list_notes("daily")
        assert result == []

    def test_nonexistent_category(self):
        result = ptos.list_notes("nonexistent")
        assert result == []

    def test_with_notes(self):
        cat_dir = os.path.join(ptos.NOTES_DIR, "daily")
        os.makedirs(cat_dir)
        with open(os.path.join(cat_dir, "2026-07-21-my-note.md"), "w") as f:
            f.write("# My Note\n\nContent here.")
        with open(os.path.join(cat_dir, "2026-07-20-older.md"), "w") as f:
            f.write("# Older Note")
        result = ptos.list_notes("daily")
        assert len(result) == 2
        assert result[0]["slug"] == "2026-07-21-my-note"
        assert result[0]["title"] == "My Note"
        assert result[0]["date"] == "2026-07-21"
        assert result[1]["slug"] == "2026-07-20-older"
        assert result[1]["title"] == "Older Note"

    def test_title_fallback_from_filename(self):
        cat_dir = os.path.join(ptos.NOTES_DIR, "ideas")
        os.makedirs(cat_dir)
        with open(os.path.join(cat_dir, "2026-07-21-bright-idea.md"), "w") as f:
            f.write("No heading here.")
        result = ptos.list_notes("ideas")
        assert result[0]["title"] == "Bright Idea"

    def test_ignores_non_md(self):
        cat_dir = os.path.join(ptos.NOTES_DIR, "daily")
        os.makedirs(cat_dir)
        with open(os.path.join(cat_dir, "test.txt"), "w") as f:
            f.write("not md")
        with open(os.path.join(cat_dir, "2026-07-21-ok.md"), "w") as f:
            f.write("# OK")
        result = ptos.list_notes("daily")
        assert len(result) == 1
        assert result[0]["slug"] == "2026-07-21-ok"


class TestCreateNote:
    def test_creates_category_and_file(self):
        result = ptos.create_note("project", "My Project")
        assert result["category"] == "project"
        import datetime as _dt
        assert result["slug"].startswith(f"{_dt.date.today().isoformat()}-")
        assert os.path.isdir(os.path.join(ptos.NOTES_DIR, "project"))
        assert os.path.isfile(result["path"])
        with open(result["path"], encoding="utf-8") as f:
            content = f.read()
        assert "My Project" in content

    def test_slug_collision(self):
        r1 = ptos.create_note("daily", "Test Note")
        r2 = ptos.create_note("daily", "Test Note")
        assert r1["slug"] != r2["slug"]
        assert r2["slug"].endswith("-2")

    def test_custom_content(self):
        result = ptos.create_note("ideas", "Custom", content="# Custom\nHello")
        with open(result["path"], encoding="utf-8") as f:
            assert f.read() == "# Custom\nHello"


class TestReadNote:
    def test_read_existing(self):
        cat_dir = os.path.join(ptos.NOTES_DIR, "daily")
        os.makedirs(cat_dir)
        with open(os.path.join(cat_dir, "2026-07-21-test.md"), "w", encoding="utf-8") as f:
            f.write("# Test\n\nContent")
        content = ptos.read_note("daily", "2026-07-21-test")
        assert content == "# Test\n\nContent"

    def test_read_nonexistent(self):
        assert ptos.read_note("daily", "nonexistent") is None


class TestSaveNote:
    def test_save_existing(self):
        cat_dir = os.path.join(ptos.NOTES_DIR, "daily")
        os.makedirs(cat_dir)
        with open(os.path.join(cat_dir, "2026-07-21-test.md"), "w", encoding="utf-8") as f:
            f.write("old content")
        ptos.save_note("daily", "2026-07-21-test", "new content")
        with open(os.path.join(cat_dir, "2026-07-21-test.md"), encoding="utf-8") as f:
            assert f.read() == "new content"

    def test_save_creates_dirs(self):
        ptos.save_note("meetings", "2026-07-21-standup", "# Standup")
        assert os.path.isfile(os.path.join(ptos.NOTES_DIR, "meetings", "2026-07-21-standup.md"))


class TestDeleteNote:
    def test_delete_existing(self):
        cat_dir = os.path.join(ptos.NOTES_DIR, "daily")
        os.makedirs(cat_dir)
        with open(os.path.join(cat_dir, "2026-07-21-test.md"), "w") as f:
            f.write("delete me")
        ptos.delete_note("daily", "2026-07-21-test")
        assert not os.path.exists(os.path.join(cat_dir, "2026-07-21-test.md"))

    def test_delete_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            ptos.delete_note("daily", "nonexistent")


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
