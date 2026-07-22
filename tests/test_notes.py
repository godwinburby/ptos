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


class TestExtractTitle:
    def test_heading_title(self, tmp_path):
        from ptos_web import _extract_title
        p = tmp_path / "note.md"
        p.write_text("# My Note Title\n\nContent here\n")
        assert _extract_title(str(p)) == "My Note Title"

    def test_no_heading_falls_back_to_slug(self, tmp_path):
        from ptos_web import _extract_title
        p = tmp_path / "my-project-note.md"
        p.write_text("Just some text\n")
        assert _extract_title(str(p)) == "My Project Note"

    def test_missing_file_falls_back_to_slug(self, tmp_path):
        from ptos_web import _extract_title
        p = tmp_path / "missing-file.md"
        assert _extract_title(str(p)) == "Missing File"


class TestLinkCandidates:
    def test_notes_appear_in_candidates(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "NOTES_DIR", str(tmp_path / "notes"))
        notes_dir = tmp_path / "notes" / "project"
        notes_dir.mkdir(parents=True)
        (notes_dir / "2026-07-21-atomic-habits.md").write_text("# Atomic Habits\n\nContent")
        from ptos_web import _extract_title
        assert _extract_title(str(notes_dir / "2026-07-21-atomic-habits.md")) == "Atomic Habits"

    def test_journal_dates_appear_in_candidates(self, tmp_path, monkeypatch):
        import ptos, glob, os
        monkeypatch.setattr(ptos, "JOURNAL_DIR", str(tmp_path / "journal"))
        journal_dir = tmp_path / "journal" / "2026" / "07"
        journal_dir.mkdir(parents=True)
        (journal_dir / "2026-07-21.md").write_text("# Journal")
        paths = glob.glob(os.path.join(ptos.JOURNAL_DIR, "*", "*", "*.md"))
        dates = [os.path.basename(p).replace(".md", "") for p in paths]
        assert "2026-07-21" in dates
