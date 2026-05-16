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


class TestLintAllRecords:
    def test_clean_records(self, tmp_path, monkeypatch):
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        (records_dir / "2026.log").write_text(
            "2026-01-15 type=expense amount=50 tag=food | lunch\n", encoding="utf-8")
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(records_dir))
        monkeypatch.setattr(ptos, "get_schema", lambda: {
            "types": {"allowed": ["expense"]},
            "fields": {"amount": {"type": "int"}},
            "type": {"expense": {"required": ["amount"], "fields": {}}}
        })
        result = ptos.lint_all_records()
        assert result["clean"] == True
        assert result["checked"] == 1
        assert result["error_count"] == 0
        assert result["warning_count"] == 0

    def test_missing_type_error(self, tmp_path, monkeypatch):
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        (records_dir / "2026.log").write_text(
            "2026-01-15 amount=50 tag=food | lunch\n", encoding="utf-8")
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(records_dir))
        monkeypatch.setattr(ptos, "get_schema", lambda: {
            "types": {"allowed": ["expense"]},
            "fields": {"amount": {"type": "int"}},
            "type": {"expense": {"required": ["amount"], "fields": {}}}
        })
        result = ptos.lint_all_records()
        assert result["clean"] == False
        assert result["error_count"] >= 1
        assert "missing type field" in result["errors"][0]["problems"][0]

    def test_quality_warnings(self, tmp_path, monkeypatch):
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        (records_dir / "2026.log").write_text(
            "2026-01-15 type=expense amount=50\n", encoding="utf-8")
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(records_dir))
        monkeypatch.setattr(ptos, "get_schema", lambda: {
            "types": {"allowed": ["expense"]},
            "fields": {"amount": {"type": "int"}},
            "type": {"expense": {"required": ["amount"], "fields": {}}}
        })
        result = ptos.lint_all_records()
        assert result["quality_warning_count"] >= 1
        warnings_text = " ".join(w["problems"][0] for w in result["quality_warnings"])
        assert "no tag" in warnings_text or "no note" in warnings_text

    def test_type_counts(self, tmp_path, monkeypatch):
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        (records_dir / "2026.log").write_text(
            "2026-01-15 type=expense amount=50 tag=food\n"
            "2026-01-16 type=income amount=100\n", encoding="utf-8")
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(records_dir))
        monkeypatch.setattr(ptos, "get_schema", lambda: {
            "types": {"allowed": ["expense", "income"]},
            "fields": {"amount": {"type": "int"}},
            "type": {
                "expense": {"required": ["amount"], "fields": {}},
                "income": {"required": ["amount"], "fields": {}}
            }
        })
        result = ptos.lint_all_records()
        assert result["type_counts"]["expense"] == 1
        assert result["type_counts"]["income"] == 1

    def test_skips_comments_and_blanks(self, tmp_path, monkeypatch):
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        (records_dir / "2026.log").write_text(
            "# comment line\n\n2026-01-15 type=expense amount=50 tag=food\n", encoding="utf-8")
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(records_dir))
        monkeypatch.setattr(ptos, "get_schema", lambda: {
            "types": {"allowed": ["expense"]},
            "fields": {"amount": {"type": "int"}},
            "type": {"expense": {"required": ["amount"], "fields": {}}}
        })
        result = ptos.lint_all_records()
        assert result["clean"] == True
        assert result["checked"] == 1

    def test_unparseable_line(self, tmp_path, monkeypatch):
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        (records_dir / "2026.log").write_text(
            "garbage data\n", encoding="utf-8")
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(records_dir))
        monkeypatch.setattr(ptos, "get_schema", lambda: {
            "types": {"allowed": []},
            "fields": {},
            "type": {}
        })
        result = ptos.lint_all_records()
        assert len(result["errors"]) >= 1
        assert "cannot parse line" in result["errors"][0]["problems"][0]
        assert result["checked"] == 1

    def test_missing_file_skipped(self, tmp_path, monkeypatch):
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(records_dir))
        monkeypatch.setattr(ptos, "get_schema", lambda: {
            "types": {"allowed": []},
            "fields": {},
            "type": {}
        })
        result = ptos.lint_all_records()
        assert result["clean"] == True
        assert result["checked"] == 0
