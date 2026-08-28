import os


class TestBacklinks:
    def _patch_paths(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "NOTES_DIR", str(tmp_path / "notes"))
        monkeypatch.setattr(ptos, "JOURNAL_DIR", str(tmp_path / "journal"))
        monkeypatch.setattr(ptos, "TODO_DIR", str(tmp_path / "todo"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo" / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "todo" / "done.txt"))
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        (tmp_path / "notes").mkdir(parents=True, exist_ok=True)
        (tmp_path / "journal").mkdir(parents=True, exist_ok=True)
        (tmp_path / "todo").mkdir(parents=True, exist_ok=True)
        (tmp_path / "records").mkdir(parents=True, exist_ok=True)
        (tmp_path / "todo" / "todo.txt").write_text("")
        (tmp_path / "todo" / "done.txt").write_text("")
        return ptos

    def test_bracket_in_note_case_insensitive(self, tmp_path, monkeypatch):
        ptos = self._patch_paths(tmp_path, monkeypatch)
        notes_dir = tmp_path / "notes" / "project"
        notes_dir.mkdir(parents=True, exist_ok=True)
        (notes_dir / "note.md").write_text("# Note\n\nRead [[Atomic Habits]] today\n")
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/backlinks?q=atomic%20habits")
        data = resp.get_json()
        assert len(data["notes"]) == 1
        hit = data["notes"][0]
        assert hit["rel_path"] == os.path.join("project", "note.md")
        assert hit["title"] == "Note"
        assert "Atomic Habits" in hit["snippet"]

    def test_linkable_field_match_under_records(self, tmp_path, monkeypatch):
        ptos = self._patch_paths(tmp_path, monkeypatch)
        (tmp_path / "records" / "2026.log").write_text(
            "2026-07-10 type=expense domain=self category=food amount=100 "
            "project=Fit context=work\n"
        )
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/backlinks?q=fit")
        data = resp.get_json()
        assert len(data["records"]) == 1
        hit = data["records"][0]
        assert hit["field"] == "project"
        assert hit["type"] == "expense"
        assert hit["date"] == "2026-07-10"
        assert hit["path"] == "2026.log"
        assert hit["lineno"] == 1

    def test_non_linkable_field_not_found(self, tmp_path, monkeypatch):
        ptos = self._patch_paths(tmp_path, monkeypatch)
        (tmp_path / "records" / "2026.log").write_text(
            "2026-07-10 type=expense domain=self category=Fit amount=100\n"
        )
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/backlinks?q=fit")
        data = resp.get_json()
        assert data["records"] == []

    def test_starter_project_context_linkable_by_default(self):
        import ptos
        linkable = ptos.get_linkable_fields()
        assert "project" in linkable
        assert "context" in linkable

    def test_todo_project_prefix_found(self, tmp_path, monkeypatch):
        ptos = self._patch_paths(tmp_path, monkeypatch)
        (tmp_path / "todo" / "todo.txt").write_text("Call supplier +HearSpeechPro\n")
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/backlinks?q=hearspeechpro")
        data = resp.get_json()
        assert len(data["todo"]) == 1
        hit = data["todo"][0]
        assert hit["line"] == "Call supplier +HearSpeechPro"
        assert hit["lineno"] == 1
        assert hit["done"] is False

    def test_todo_bracket_found(self, tmp_path, monkeypatch):
        ptos = self._patch_paths(tmp_path, monkeypatch)
        (tmp_path / "todo" / "todo.txt").write_text("Review [[Fit]] session\n")
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/backlinks?q=fit")
        data = resp.get_json()
        assert len(data["todo"]) == 1
        assert data["todo"][0]["lineno"] == 1

    def test_no_references_returns_all_empty(self, tmp_path, monkeypatch):
        ptos = self._patch_paths(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/backlinks?q=ghost")
        data = resp.get_json()
        assert data == {"notes": [], "journal": [], "todo": [], "records": []}

    def test_empty_subject_returns_all_empty(self, tmp_path, monkeypatch):
        ptos = self._patch_paths(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/backlinks")
        data = resp.get_json()
        assert data == {"notes": [], "journal": [], "todo": [], "records": []}

    def test_snippet_at_file_start_and_end(self, tmp_path, monkeypatch):
        ptos = self._patch_paths(tmp_path, monkeypatch)
        notes_dir = tmp_path / "notes" / "a"
        notes_dir.mkdir(parents=True, exist_ok=True)
        (notes_dir / "start.md").write_text("[[Fit]] begins here\n")
        (notes_dir / "end.md").write_text("some content [[Fit]]\n")
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/backlinks?q=fit")
        data = resp.get_json()
        assert len(data["notes"]) == 2
        assert all("Fit" in n["snippet"] for n in data["notes"])

    def test_journal_bracket_found(self, tmp_path, monkeypatch):
        ptos = self._patch_paths(tmp_path, monkeypatch)
        journal_dir = tmp_path / "journal" / "2026" / "07"
        journal_dir.mkdir(parents=True, exist_ok=True)
        (journal_dir / "2026-07-22.md").write_text("Today I [[buy house]] plans\n")
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/backlinks?q=buy%20house")
        data = resp.get_json()
        assert len(data["journal"]) == 1
        hit = data["journal"][0]
        assert hit["date"] == "2026-07-22"
        assert "buy house" in hit["snippet"]

    def test_todo_context_found_when_linkable(self, tmp_path, monkeypatch):
        ptos = self._patch_paths(tmp_path, monkeypatch)
        (tmp_path / "todo" / "todo.txt").write_text("Task @clinic\n")
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/backlinks?q=clinic")
        data = resp.get_json()
        assert len(data["todo"]) == 1
        assert data["todo"][0]["done"] is False
