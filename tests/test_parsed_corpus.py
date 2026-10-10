import datetime as dt

import ptos
import ptos_service as svc


def _write_record(line, fname="2026.log"):
    path = ptos.os.path.join(ptos.RECORDS_DIR, fname)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


class TestParsedFileCache:
    def test_same_object_until_file_changes(self):
        _write_record("2026-01-01 type=expense amount=10")
        first = ptos._parsed_file("2026.log")
        second = ptos._parsed_file("2026.log")
        assert second is first  # cached, no re-read

    def test_picks_up_same_process_write_without_invalidation(self):
        _write_record("2026-01-01 type=expense amount=10")
        ptos._parsed_file("2026.log")
        with open(ptos.os.path.join(ptos.RECORDS_DIR, "2026.log"), "w",
                  encoding="utf-8") as f:
            f.write("2026-01-01 type=expense amount=10\n"
                    "2026-01-02 type=expense amount=7\n")
        rows = ptos._parsed_file("2026.log")
        assert len(rows) == 2
        assert rows[1][1].isoformat() == "2026-01-02"

    def test_missing_file_returns_empty(self):
        assert ptos._parsed_file("does-not-exist.log") == []

    def test_scan_records_shares_the_parsed_rows(self):
        _write_record("2026-01-01 type=expense amount=10")
        rows = ptos._parsed_file("2026.log")
        _, _, parsed = ptos.scan_records(
            dt.date(2026, 1, 1), dt.date(2026, 12, 31), ["type=expense"],
            None, return_parsed=True)
        assert parsed[0][1] is rows[0][2]  # same kv dict, one parse

    def test_blank_and_comment_lines_skipped(self):
        _write_record("2026-01-01 type=expense amount=10\n# comment\n\n")
        rows = ptos._parsed_file("2026.log")
        assert len(rows) == 1

    def test_prefix_cleared_by_service_invalidate(self):
        _write_record("2026-01-01 type=expense amount=10")
        svc.get_records([], "all")
        assert any(k.startswith("pf:") for k in ptos._CACHE)
        svc.append_record("2026-01-02 type=expense amount=5")
        assert not any(k.startswith("pf:") for k in ptos._CACHE)

    def test_prefix_watched_for_external_changes(self):
        assert "pf:" in ptos._EXT_RECORD_PREFIXES


class TestGetRecordsRowMemo:
    def test_rows_computed_once_across_same_corpus(self, monkeypatch):
        for i in range(5):
            _write_record(f"2026-01-{i+1:02d} type=expense amount={i+1}")
        calls = []
        import ptos
        orig = ptos.compute_derived
        monkeypatch.setattr(ptos, "compute_derived", lambda kv, record_date=None: (
            calls.append(1) or orig(kv, record_date)))
        first = svc.get_records([], "all")
        assert first["count"] == 5
        n_after_first = len(calls)
        assert n_after_first == 5
        # Second browse sorts the SAME corpus — every row body is memoized, so
        # not a single derived-field pass runs again.
        second = svc.get_records([], "all", sort="amount")
        assert second["count"] == 5
        assert len(calls) == n_after_first
        assert [r["amount"] for r in second["records"]] == ["1", "2", "3", "4", "5"]

    def test_returned_rows_are_isolated(self):
        _write_record("2026-01-01 type=expense amount=10")
        first = svc.get_records([], "all")
        first["kind"] = "records"
        first["records"][0]["date"] = "MUTATED"
        second = svc.get_records([], "all")
        assert "kind" not in second
        assert second["records"][0]["date"] != "MUTATED"

    def test_schema_change_clears_rows(self):
        _write_record("2026-01-01 type=expense amount=10")
        svc.get_records([], "all")
        assert any(k.startswith("row:") for k in ptos._CACHE)
        ptos._invalidate_from_changes(["config/schema.toml"])
        assert not any(k.startswith("row:") for k in ptos._CACHE)

    def test_config_change_clears_rows(self):
        _write_record("2026-01-01 type=expense amount=10")
        svc.get_records([], "all")
        ptos._invalidate_from_changes(["config/config.toml"])
        assert not any(k.startswith("row:") for k in ptos._CACHE)

    def test_prefix_watched_for_external_changes(self):
        assert "row:" in ptos._EXT_RECORD_PREFIXES


class TestDateFormatCache:
    def test_resolved_once_per_toml(self, monkeypatch):
        fmt = ptos.date_format()
        assert isinstance(fmt, str)
        def boom():
            raise AssertionError("date_format must not re-read config every call")
        monkeypatch.setattr(ptos, "get_config", boom)
        assert ptos.date_format() == fmt

    def test_cleared_by_config_invalidation(self):
        fmt = ptos.date_format()
        ptos._invalidate("config")
        assert "date_fmt" not in ptos._CACHE
        assert ptos.date_format() == fmt

    def test_follows_set_date_format(self):
        ptos.set_date_format("iso")
        assert ptos.date_format() == "iso"
        ptos.set_date_format("indian")
        assert ptos.date_format() == "indian"


class TestScanShare:
    def test_distinct_queries_parse_corpus_once(self, monkeypatch):
        _write_record("2026-01-01 type=expense amount=10")
        _write_record("2026-01-02 type=income amount=5")
        import builtins
        real_open = builtins.open
        reads = []
        def counting_open(*a, **kw):
            if isinstance(a[0], str) and a[0].endswith(".log"):
                reads.append(a[0])
            return real_open(*a, **kw)
        monkeypatch.setattr(builtins, "open", counting_open)
        svc.get_records(["type=expense"], "all")
        svc.get_records(["type=income"], "all")
        svc.get_records([], "all")
        log_reads = [p for p in reads if "records" in p]
        # The second and third calls must hit the pf: cache, not re-open files.
        assert len(log_reads) == 1