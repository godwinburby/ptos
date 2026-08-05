import os


class TestLinkCandidatesDeriveFromSchema:
    """link-candidates must derive its field set from schema, not a
    hardcoded project|context regex."""

    def _custom_schema(self):
        return """\
[types]
allowed = ["expense", "income"]

[fields.amount]
type = "int"
aggregatable = true

[global_fields.client]
type = "string"
linkable = true

[global_fields.project]
type = "string"
linkable = true

[type.expense]
required = ["domain", "amount"]

[type.expense.fields.domain]
options = ["self", "work"]
"""

    def test_custom_linkable_field_picked_up(self, tmp_path, monkeypatch):
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

        schema_path = ptos.SCHEMA_PATH
        with open(schema_path, "w", encoding="utf-8") as f:
            f.write(self._custom_schema())
        ptos._invalidate("schema")
        assert "client" in ptos.get_linkable_fields()

        (tmp_path / "records" / "2026.log").write_text(
            "2026-07-10 type=expense domain=self amount=50 client=Acme\n"
        )
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/link-candidates?q=acme")
        data = resp.get_json()
        assert "Acme" in data

    def test_non_linkable_field_excluded(self, tmp_path, monkeypatch):
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

        schema_path = ptos.SCHEMA_PATH
        with open(schema_path, "w", encoding="utf-8") as f:
            f.write(self._custom_schema())
        ptos._invalidate("schema")

        (tmp_path / "records" / "2026.log").write_text(
            "2026-07-10 type=expense domain=self amount=50 category=Acme\n"
        )
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/api/link-candidates?q=acme")
        data = resp.get_json()
        assert "Acme" not in data
