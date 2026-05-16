import ptos


class TestLintRecords:
    def test_clean_records(self, capsys):
        schema = {
            "types": {"allowed": ["expense"]},
            "fields": {"amount": {"type": "int"}},
            "type": {
                "expense": {
                    "required": ["amount"],
                    "fields": {}
                }
            }
        }
        records = [
            "2026-01-15 type=expense amount=50 tag=food | bought lunch",
        ]
        errors = ptos.lint_records(records, schema)
        out = capsys.readouterr().out
        assert errors == set()
        assert "All records clean" in out

    def test_missing_type(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", "/tmp/fake")
        schema = {"types": {"allowed": []}, "fields": {}, "type": {}}
        records = ["2026-01-15 amount=50 tag=food | note"]
        ptos.lint_records(records, schema)
        out = capsys.readouterr().out
        # The date is valid but type is missing — "missing type field" error
        assert "missing type field" in out

    def test_missing_type(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", "/tmp/fake")
        schema = {"types": {"allowed": []}, "fields": {}, "type": {}}
        records = ["2026-01-15 amount=50"]
        errors = ptos.lint_records(records, schema)
        assert "missing type field" in capsys.readouterr().out

    def test_no_tag_warning(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", "/tmp/fake")
        schema = {
            "types": {"allowed": ["expense"]},
            "fields": {"amount": {"type": "int"}},
            "type": {"expense": {"required": ["amount"], "fields": {}}}
        }
        records = ["2026-01-15 type=expense amount=50 | lunch"]
        ptos.lint_records(records, schema)
        out = capsys.readouterr().out
        assert "no tag" in out

    def test_no_note_warning(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", "/tmp/fake")
        schema = {
            "types": {"allowed": ["expense"]},
            "fields": {"amount": {"type": "int"}},
            "type": {"expense": {"required": ["amount"], "fields": {}}}
        }
        records = ["2026-01-15 type=expense amount=50 tag=food"]
        ptos.lint_records(records, schema)
        out = capsys.readouterr().out
        assert "no note" in out

    def test_schema_validation_errors(self, capsys):
        schema = {
            "types": {"allowed": ["expense"]},
            "fields": {"amount": {"type": "int"}},
            "type": {
                "expense": {
                    "required": ["amount", "domain"],
                    "fields": {
                        "domain": {"options": ["work", "home"]}
                    }
                }
            }
        }
        records = ["2026-01-15 type=expense amount=50 | note"]
        ptos.lint_records(records, schema)
        out = capsys.readouterr().out
        assert "domain" in out

    def test_empty_line_skipped(self, capsys):
        schema = {
            "types": {"allowed": ["expense"]},
            "fields": {"amount": {"type": "int"}},
            "type": {"expense": {"required": [], "fields": {}}}
        }
        records = ["", "   ", "2026-01-15 type=expense amount=50 tag=food | note"]
        ptos.lint_records(records, schema)
        out = capsys.readouterr().out
        assert "All records clean" in out

    def test_multiple_records_multiple_errors(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", "/tmp/fake_logs")
        schema = {
            "types": {"allowed": ["expense"]},
            "fields": {"amount": {"type": "int"}},
            "type": {"expense": {"required": ["amount", "domain"], "fields": {}}}
        }
        records = [
            "2026-01-14 type=expense amount=50 | note one",
            "2026-01-15 type=expense | missing amount",
        ]
        errors = ptos.lint_records(records, schema)
        out = capsys.readouterr().out
        assert "missing amount" in out or "domain" in out
        assert "/tmp/fake_logs" in list(errors)[0]

    def test_type_counts_in_output(self, capsys):
        schema = {
            "types": {"allowed": ["expense", "income"]},
            "fields": {"amount": {"type": "int"}},
            "type": {
                "expense": {"required": ["amount"], "fields": {}},
                "income": {"required": ["amount"], "fields": {}},
            }
        }
        records = [
            "2026-01-15 type=expense amount=50",
            "2026-01-16 type=income amount=100",
        ]
        ptos.lint_records(records, schema)
        out = capsys.readouterr().out
        assert "expense:1" in out
        assert "income:1" in out
