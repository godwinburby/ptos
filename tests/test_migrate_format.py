import os

import ptos


def _seed(rel_path, text):
    path = os.path.join(ptos.RECORDS_DIR, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestMigrateRecordFormat:
    def test_pipe_note_becomes_note_field(self):
        path = _seed("2026.log", "2026-01-15 type=expense amount=5 | bought lunch\n")
        summary = ptos.migrate_record_format()
        assert summary["changed"] == 1
        assert _read(path) == '2026-01-15 type=expense amount=5 note="bought lunch"\n'

    def test_type_moved_second(self):
        path = _seed("2026.log", "2026-01-15 amount=5 type=expense\n")
        ptos.migrate_record_format()
        assert _read(path) == "2026-01-15 type=expense amount=5\n"

    def test_canonical_line_left_untouched(self):
        line = "2026-01-15 type=expense amount=5 tag=food note=\"bought lunch\"\n"
        path = _seed("2026.log", line)
        summary = ptos.migrate_record_format()
        assert summary["changed"] == 0
        assert _read(path) == line

    def test_blank_and_comment_preserved(self):
        path = _seed("2026.log", "# a note\n\n2026-01-15 type=expense | x\n")
        ptos.migrate_record_format()
        lines = _read(path).splitlines()
        assert lines[0] == "# a note"
        assert lines[1] == ""
        assert lines[2] == "2026-01-15 type=expense note=x"

    def test_dry_run_writes_nothing(self):
        path = _seed("2026.log", "2026-01-15 type=expense | x\n")
        summary = ptos.migrate_record_format(dry_run=True)
        assert summary["changed"] == 1
        assert _read(path) == "2026-01-15 type=expense | x\n"

    def test_subdirectory_is_migrated(self):
        path = _seed(os.path.join("followup", "2026.log"),
                     "2026-01-15 type=followup patient=jane | called\n")
        summary = ptos.migrate_record_format()
        assert summary["changed"] == 1
        assert _read(path) == "2026-01-15 type=followup patient=jane note=called\n"

    def test_empty_value_reported_and_left(self):
        line = "2026-01-15 type=expense amount=\n"
        path = _seed("2026.log", line)
        summary = ptos.migrate_record_format()
        assert summary["changed"] == 0
        assert len(summary["errors"]) == 1
        assert _read(path) == line

    def test_non_log_files_untouched(self):
        path = _seed("notes.txt", "not a record\n")
        summary = ptos.migrate_record_format()
        assert summary["files"] == 0
        assert _read(path) == "not a record\n"


class TestFreeTextUnderscoreDecode:
    def test_free_text_underscore_becomes_space(self):
        path = _seed(
            "2026.log",
            "2026-01-15 type=expense domain=self category=food amount=5 project=big_proj\n")
        summary = ptos.migrate_record_format()
        assert summary["changed"] == 1
        assert _read(path) == (
            '2026-01-15 type=expense domain=self category=food amount=5 '
            'project="big proj"\n')

    def test_token_values_untouched(self):
        line = ("2026-01-15 type=investment instrument=mutual_fund provider=bank "
                "amount=5 tag=water_metro\n")
        path = _seed("2026.log", line)
        summary = ptos.migrate_record_format()
        assert summary["changed"] == 0
        assert _read(path) == line

    def test_already_spaced_free_text_untouched(self):
        line = ('2026-01-15 type=expense domain=self category=food amount=5 '
                'project="big proj"\n')
        path = _seed("2026.log", line)
        summary = ptos.migrate_record_format()
        assert summary["changed"] == 0
        assert _read(path) == line

    def test_unknown_field_untouched(self):
        line = ("2026-01-15 type=expense domain=self category=food amount=5 "
                "bogus_field=foo_bar\n")
        path = _seed("2026.log", line)
        summary = ptos.migrate_record_format()
        assert summary["changed"] == 0
        assert _read(path) == line

    def test_id_and_links_untouched(self):
        line = ("2026-01-15 type=expense domain=self category=food amount=5 "
                "id=abc_def links=income:xyz_123\n")
        path = _seed("2026.log", line)
        summary = ptos.migrate_record_format()
        assert summary["changed"] == 0
        assert _read(path) == line


class TestMigrateCli:
    def test_cli_dry_run_reports(self, monkeypatch, capsys):
        import ptos_cli
        _seed("2026.log", "2026-01-15 type=expense | x\n")
        monkeypatch.setattr("sys.argv", ["ptos", "--migrate-format", "--dry-run"])
        ptos_cli.main()
        out = capsys.readouterr().out
        assert "would change 1 line" in out.lower()

    def test_cli_writes(self, monkeypatch):
        import ptos_cli
        path = _seed("2026.log", "2026-01-15 type=expense | x\n")
        monkeypatch.setattr("sys.argv", ["ptos", "--migrate-format"])
        ptos_cli.main()
        assert _read(path) == "2026-01-15 type=expense note=x\n"