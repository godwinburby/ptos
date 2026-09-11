import datetime as dt
import os
import ptos


SCHEMA_WITH_LOG_GROUP = {
    "types": {"allowed": ["expense", "followup"]},
    "type": {
        "expense": {
            "required": ["amount"],
            "fields": {"amount": {}},
        },
        "followup": {
            "required": ["patient"],
            "fields": {"patient": {}, "note": {}},
            "log_group": "followup",
        },
    },
    "fields": {},
}


def _write_schema(monkeypatch, schema=None):
    """Write a schema.toml to the monkeypatched SCHEMA_PATH."""
    import tomli_w
    schema = schema or SCHEMA_WITH_LOG_GROUP
    path = ptos.SCHEMA_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(schema, f)
    ptos._invalidate_all()
    return path


class TestResolveRecordPath:
    def test_no_log_group_goes_to_flat(self, monkeypatch):
        _write_schema(monkeypatch)
        line = "2026-03-15 type=expense amount=50 | lunch"
        result = ptos._resolve_record_path(line)
        assert result == os.path.join(ptos.RECORDS_DIR, "2026.log")

    def test_log_group_routes_to_subdir(self, monkeypatch):
        _write_schema(monkeypatch)
        line = "2026-03-15 type=followup patient=jane note=checkup"
        result = ptos._resolve_record_path(line)
        assert result == os.path.join(ptos.RECORDS_DIR, "followup", "2026.log")

    def test_no_type_uses_flat(self, monkeypatch):
        _write_schema(monkeypatch)
        line = "2026-03-15 tag=test | some note"
        result = ptos._resolve_record_path(line)
        assert result == os.path.join(ptos.RECORDS_DIR, "2026.log")

    def test_unknown_type_uses_flat(self, monkeypatch):
        _write_schema(monkeypatch)
        line = "2026-03-15 type=unknown amount=10"
        result = ptos._resolve_record_path(line)
        assert result == os.path.join(ptos.RECORDS_DIR, "2026.log")


class TestAppendRecordLogGroup:
    def test_followup_goes_to_subdir(self, monkeypatch):
        _write_schema(monkeypatch)
        line = "2026-03-15 type=followup patient=jane note=checkup"
        ptos.append_record(line)
        target = os.path.join(ptos.RECORDS_DIR, "followup", "2026.log")
        assert os.path.exists(target)
        with open(target) as f:
            content = f.read()
        assert "patient=jane" in content

    def test_expense_goes_to_flat(self, monkeypatch):
        _write_schema(monkeypatch)
        line = "2026-03-15 type=expense amount=50 | lunch"
        ptos.append_record(line)
        flat = os.path.join(ptos.RECORDS_DIR, "2026.log")
        subdir = os.path.join(ptos.RECORDS_DIR, "followup", "2026.log")
        assert os.path.exists(flat)
        assert not os.path.exists(subdir)
        with open(flat) as f:
            content = f.read()
        assert "amount=50" in content

    def test_creates_subdir_automatically(self, monkeypatch):
        _write_schema(monkeypatch)
        line = "2026-03-15 type=followup patient=jane note=checkup"
        ptos.append_record(line)
        assert os.path.isdir(os.path.join(ptos.RECORDS_DIR, "followup"))

    def test_multiple_types_share_nothing(self, monkeypatch):
        _write_schema(monkeypatch)
        ptos.append_record("2026-01-15 type=expense amount=10 | coffee")
        ptos.append_record("2026-03-15 type=followup patient=alice note=call")
        ptos.append_record("2026-06-20 type=expense amount=25 | lunch")
        flat = os.path.join(ptos.RECORDS_DIR, "2026.log")
        group = os.path.join(ptos.RECORDS_DIR, "followup", "2026.log")
        assert os.path.exists(flat)
        assert os.path.exists(group)
        with open(flat) as f:
            flat_content = f.read()
        with open(group) as f:
            group_content = f.read()
        assert flat_content.count("type=expense") == 2
        assert "type=followup" not in flat_content
        assert group_content.count("type=followup") == 1


class TestGetLogFiles:
    def test_flat_only(self, monkeypatch):
        records = os.path.join(ptos.RECORDS_DIR)
        os.makedirs(records, exist_ok=True)
        with open(os.path.join(records, "2026.log"), "w") as f:
            f.write("line1\n")
        with open(os.path.join(records, "2025.log"), "w") as f:
            f.write("line2\n")
        result = ptos.get_log_files()
        assert sorted(result) == ["2025.log", "2026.log"]

    def test_with_subdirs(self, monkeypatch):
        records = ptos.RECORDS_DIR
        os.makedirs(records, exist_ok=True)
        with open(os.path.join(records, "2026.log"), "w") as f:
            f.write("line1\n")
        followup = os.path.join(records, "followup")
        os.makedirs(followup, exist_ok=True)
        with open(os.path.join(followup, "2026.log"), "w") as f:
            f.write("line2\n")
        result = ptos.get_log_files()
        assert "2026.log" in result
        assert os.path.join("followup", "2026.log") in result

    def test_excludes_conflict_files(self, monkeypatch):
        records = ptos.RECORDS_DIR
        os.makedirs(records, exist_ok=True)
        with open(os.path.join(records, "2026.log"), "w") as f:
            f.write("line1\n")
        with open(os.path.join(records, "2026.log.conflict"), "w") as f:
            f.write("bad\n")
        result = ptos.get_log_files()
        assert result == ["2026.log"]

    def test_excludes_non_log_files(self, monkeypatch):
        records = ptos.RECORDS_DIR
        os.makedirs(records, exist_ok=True)
        with open(os.path.join(records, "2026.log"), "w") as f:
            f.write("line1\n")
        with open(os.path.join(records, "readme.txt"), "w") as f:
            f.write("ignore me\n")
        result = ptos.get_log_files()
        assert result == ["2026.log"]

    def test_empty_records_dir(self, monkeypatch):
        os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
        result = ptos.get_log_files()
        assert result == []


class TestScanRecordsLogGroup:
    def test_finds_records_in_subdir(self, monkeypatch):
        _write_schema(monkeypatch)
        records = ptos.RECORDS_DIR
        os.makedirs(records, exist_ok=True)
        with open(os.path.join(records, "2026.log"), "w") as f:
            f.write("2026-01-15 type=expense amount=50 | lunch\n")
        followup = os.path.join(records, "followup")
        os.makedirs(followup, exist_ok=True)
        with open(os.path.join(followup, "2026.log"), "w") as f:
            f.write("2026-03-15 type=followup patient=jane note=checkup\n")
        start = dt.date(2026, 1, 1)
        end = dt.date(2026, 12, 31)
        results, total = ptos.scan_records(start, end, [], None)
        assert len(results) == 2

    def test_year_skip_works_with_subdirs(self, monkeypatch):
        _write_schema(monkeypatch)
        records = ptos.RECORDS_DIR
        os.makedirs(records, exist_ok=True)
        with open(os.path.join(records, "2025.log"), "w") as f:
            f.write("2025-06-15 type=expense amount=10\n")
        followup = os.path.join(records, "followup")
        os.makedirs(followup, exist_ok=True)
        with open(os.path.join(followup, "2025.log"), "w") as f:
            f.write("2025-06-15 type=followup patient=jane note=old\n")
        start = dt.date(2026, 1, 1)
        end = dt.date(2026, 12, 31)
        results, total = ptos.scan_records(start, end, [], None)
        assert len(results) == 0

    def test_filter_on_log_group_type(self, monkeypatch):
        _write_schema(monkeypatch)
        records = ptos.RECORDS_DIR
        os.makedirs(records, exist_ok=True)
        with open(os.path.join(records, "2026.log"), "w") as f:
            f.write("2026-01-15 type=expense amount=50 | lunch\n")
        followup = os.path.join(records, "followup")
        os.makedirs(followup, exist_ok=True)
        with open(os.path.join(followup, "2026.log"), "w") as f:
            f.write("2026-03-15 type=followup patient=jane note=checkup\n")
            f.write("2026-03-20 type=followup patient=bob note=followup\n")
        start = dt.date(2026, 1, 1)
        end = dt.date(2026, 12, 31)
        results, total = ptos.scan_records(start, end, ["type=followup"], None)
        assert len(results) == 2

    def test_cli_file_with_subdir(self, monkeypatch):
        _write_schema(monkeypatch)
        records = ptos.RECORDS_DIR
        os.makedirs(records, exist_ok=True)
        followup = os.path.join(records, "followup")
        os.makedirs(followup, exist_ok=True)
        with open(os.path.join(followup, "2026.log"), "w") as f:
            f.write("2026-03-15 type=followup patient=jane note=checkup\n")
        start = dt.date(2026, 1, 1)
        end = dt.date(2026, 12, 31)
        results, total = ptos.scan_records(start, end, [], None,
                                           from_file="followup/2026.log")
        assert len(results) == 1

    def test_find_records_with_location_in_subdir(self, monkeypatch):
        _write_schema(monkeypatch)
        records = ptos.RECORDS_DIR
        os.makedirs(records, exist_ok=True)
        followup = os.path.join(records, "followup")
        os.makedirs(followup, exist_ok=True)
        with open(os.path.join(followup, "2026.log"), "w") as f:
            f.write("2026-03-15 type=followup patient=jane note=checkup\n")
        matches = ptos.find_records_with_location(
            ["type=followup"], start=dt.date(2026, 1, 1), end=dt.date(2026, 12, 31))
        assert len(matches) == 1
        filepath, lineno, raw = matches[0]
        assert "followup" in filepath.replace("\\", "/")
        assert "patient=jane" in raw


class TestRunSetYearCross:
    def test_year_cross_moves_to_correct_group_file(self, monkeypatch):
        _write_schema(monkeypatch)
        records = ptos.RECORDS_DIR
        os.makedirs(records, exist_ok=True)
        followup = os.path.join(records, "followup")
        os.makedirs(followup, exist_ok=True)
        orig = "2026-03-15 type=followup patient=jane note=checkup"
        with open(os.path.join(followup, "2026.log"), "w") as f:
            f.write(orig + "\n")
        matches = ptos.find_records_with_location(
            ["type=followup"], start=dt.date(2026, 1, 1), end=dt.date(2026, 12, 31))
        assert len(matches) == 1
        filepath, lineno, raw = matches[0]
        new_line, changed_date = ptos.apply_set(
            raw, ["date=2027-01-10"], None)
        assert changed_date == "2027-01-10"
        new_path = ptos._resolve_record_path(new_line)
        assert "followup" in new_path.replace("\\", "/")
        assert "2027.log" in new_path


class TestLintRecordsLogGroup:
    def test_lint_error_files_resolve_to_group(self, monkeypatch):
        _write_schema(monkeypatch)
        records = ptos.RECORDS_DIR
        os.makedirs(records, exist_ok=True)
        followup = os.path.join(records, "followup")
        os.makedirs(followup, exist_ok=True)
        line = "2026-03-15 type=followup patient=jane"
        with open(os.path.join(followup, "2026.log"), "w") as f:
            f.write(line + "\n")
        results, _ = ptos.scan_records(
            dt.date(2026, 1, 1), dt.date(2026, 12, 31), [], None)
        error_files = ptos.lint_records(results, SCHEMA_WITH_LOG_GROUP)
        resolved = error_files.pop() if error_files else None
        if resolved:
            assert "followup" in resolved.replace("\\", "/")


class TestEditRecordYearCross:
    def test_year_cross_in_service(self, monkeypatch):
        _write_schema(monkeypatch)
        records = ptos.RECORDS_DIR
        os.makedirs(records, exist_ok=True)
        followup = os.path.join(records, "followup")
        os.makedirs(followup, exist_ok=True)
        orig = "2026-03-15 type=followup patient=jane note=checkup"
        target = os.path.join(followup, "2026.log")
        with open(target, "w") as f:
            f.write(orig + "\n")
        filepath = target
        import ptos_service as svc
        result = svc.edit_record(filepath, orig, set_args=["date=2027-01-10"],
                                 lineno=0)
        new_path = ptos._resolve_record_path(result["new_line"])
        assert "followup" in new_path.replace("\\", "/")
        assert "2027.log" in new_path
        assert os.path.exists(new_path)


class TestMigrateLogGroup:
    def test_migrate_moves_records(self, monkeypatch):
        _write_schema(monkeypatch)
        records = ptos.RECORDS_DIR
        os.makedirs(records, exist_ok=True)
        flat = os.path.join(records, "2026.log")
        with open(flat, "w") as f:
            f.write("2026-01-15 type=expense amount=50 | lunch\n")
            f.write("2026-03-15 type=followup patient=jane note=checkup\n")
            f.write("2026-06-20 type=followup patient=bob note=followup\n")
        from ptos_cli import _handle_migrate_log_group
        _handle_migrate_log_group("followup")
        target_dir = os.path.join(records, "followup")
        assert os.path.isdir(target_dir)
        target = os.path.join(target_dir, "2026.log")
        assert os.path.exists(target)
        with open(target) as f:
            moved = f.read()
        assert moved.count("type=followup") == 2
        with open(flat) as f:
            remaining = f.read()
        assert "type=followup" not in remaining
        assert "type=expense" in remaining

    def test_migrate_no_records(self, monkeypatch):
        _write_schema(monkeypatch)
        records = ptos.RECORDS_DIR
        os.makedirs(records, exist_ok=True)
        flat = os.path.join(records, "2026.log")
        with open(flat, "w") as f:
            f.write("2026-01-15 type=expense amount=50 | lunch\n")
        from ptos_cli import _handle_migrate_log_group
        _handle_migrate_log_group("followup")
        assert not os.path.isdir(os.path.join(records, "followup"))

    def test_migrate_no_log_group_exits(self, monkeypatch):
        _write_schema(monkeypatch, schema={
            "types": {"allowed": ["expense"]},
            "type": {"expense": {"required": ["amount"], "fields": {"amount": {}}}},
        })
        import ptos_cli
        try:
            ptos_cli._handle_migrate_log_group("expense")
            assert False, "Should have exited"
        except SystemExit:
            pass
