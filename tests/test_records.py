import datetime as dt
import os
import ptos


SAMPLE_LINES = [
    "2026-01-15 type=expense domain=self category=food amount=50 | lunch",
    "2026-01-20 type=income source=salary amount=2000",
    "2026-02-10 type=expense domain=work category=supplies amount=100",
    "2026-03-05 type=expense domain=self category=transport amount=30 tag=fuel",
]


def _write_log(tmpdir, filename="2026.log"):
    """Write sample records to a log file in tmpdir/records/."""
    records_dir = os.path.join(tmpdir, "records")
    os.makedirs(records_dir, exist_ok=True)
    path = os.path.join(records_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        for line in SAMPLE_LINES:
            f.write(line + "\n")
    return path


class TestScanRecords:
    def test_no_filters_returns_all(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        _write_log(tmpdir)
        start = dt.date(2026, 1, 1)
        end = dt.date(2026, 12, 31)
        results, total = ptos.scan_records(start, end, [], None)
        assert len(results) == 4

    def test_date_filter(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        _write_log(tmpdir)
        start = dt.date(2026, 2, 1)
        end = dt.date(2026, 12, 31)
        results, total = ptos.scan_records(start, end, [], None)
        assert len(results) == 2

    def test_single_filter(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        _write_log(tmpdir)
        start = dt.date(2026, 1, 1)
        end = dt.date(2026, 12, 31)
        results, total = ptos.scan_records(start, end, ["domain=work"], None)
        assert len(results) == 1
        assert "domain=work" in results[0]

    def test_search_text(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        _write_log(tmpdir)
        start = dt.date(2026, 1, 1)
        end = dt.date(2026, 12, 31)
        results, total = ptos.scan_records(start, end, [], "lunch")
        assert len(results) == 1

    def test_sum_field(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        _write_log(tmpdir)
        start = dt.date(2026, 1, 1)
        end = dt.date(2026, 12, 31)
        results, total = ptos.scan_records(start, end, [], None, sum_field="amount")
        assert total == 50 + 2000 + 100 + 30

    def test_from_file(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        _write_log(tmpdir)
        _write_log(tmpdir, "2025.log")  # write a second file
        start = dt.date(2026, 1, 1)
        end = dt.date(2026, 12, 31)
        results, total = ptos.scan_records(start, end, [], None, from_file="2026.log")
        assert len(results) == 4

    def test_no_records_in_range(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        _write_log(tmpdir)
        start = dt.date(2025, 1, 1)
        end = dt.date(2025, 12, 31)
        results, total = ptos.scan_records(start, end, [], None)
        assert results == []
        assert total == 0


class TestAppendRecord:
    def test_appends_to_correct_file(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        monkeypatch.setattr(ptos, "atomic_write", ptos.atomic_write)
        line = "2026-06-01 type=expense domain=self amount=25"
        ptos.append_record(line)
        path = os.path.join(tmpdir, "records", "2026.log")
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
        assert line in content

    def test_appends_new_year_file(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        monkeypatch.setattr(ptos, "atomic_write", ptos.atomic_write)
        line = "2027-01-01 type=income source=gift amount=100"
        ptos.append_record(line)
        path = os.path.join(tmpdir, "records", "2027.log")
        assert os.path.exists(path)


class TestFindRecordsWithLocation:
    def test_finds_matching_records(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        fp = _write_log(tmpdir)
        start = dt.date(2026, 1, 1)
        end = dt.date(2026, 12, 31)
        matches = ptos.find_records_with_location(["domain=work"], start=start, end=end)
        assert len(matches) == 1
        filepath, lineno, raw = matches[0]
        assert "domain=work" in raw

    def test_no_matches(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        _write_log(tmpdir)
        matches = ptos.find_records_with_location(["nonexistent=value"])
        assert matches == []


class TestRewriteLineInFile:
    def test_replace_line(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        fp = _write_log(tmpdir)
        ptos.rewrite_line_in_file(fp, SAMPLE_LINES[0], "2026-01-15 type=expense amount=99")
        with open(fp) as f:
            content = f.read()
        assert "amount=99" in content
        assert "amount=50" not in content

    def test_delete_line(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        fp = _write_log(tmpdir)
        ptos.rewrite_line_in_file(fp, SAMPLE_LINES[0], None)
        with open(fp) as f:
            content = f.read()
        assert SAMPLE_LINES[0] not in content
        assert len(content.strip().split("\n")) == 3

    def test_replace_by_lineno(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        fp = _write_log(tmpdir)
        ptos.rewrite_line_in_file(fp, SAMPLE_LINES[1], "2026-01-20 type=income amount=9999", lineno=1)
        with open(fp) as f:
            content = f.read()
        assert "amount=9999" in content

    def test_line_not_found_raises(self, tmpdir, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", os.path.join(tmpdir, "records"))
        fp = _write_log(tmpdir)
        import pytest
        with pytest.raises(ValueError, match="Line not found"):
            ptos.rewrite_line_in_file(fp, "nonexistent line", None)
