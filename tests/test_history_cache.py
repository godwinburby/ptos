import datetime as dt
import os
import ptos
import ptos_service as svc


def _write_record(line):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    path = os.path.join(ptos.RECORDS_DIR, f"{line[:4]}.log")
    with open(path, "w", encoding="utf-8") as f:
        f.write(line + "\n")


def _record_dict(line, lineno=0):
    return {"filepath": os.path.join(ptos.RECORDS_DIR, f"{line[:4]}.log"),
            "line": line, "lineno": lineno}


def _set_ttl(monkeypatch, value):
    """Pin [cache] suggestion_ttl_seconds for this test."""
    real = ptos.get_config
    def patched():
        cfg = dict(real())
        cfg["cache"] = dict(cfg.get("cache") or {})
        cfg["cache"]["suggestion_ttl_seconds"] = value
        return cfg
    monkeypatch.setattr(ptos, "get_config", patched)


class _Clock:
    def __init__(self):
        self.now = 1000.0
    def __call__(self):
        return self.now
    def advance(self, seconds):
        self.now += seconds


def _counting_scans(monkeypatch):
    calls = []
    original = ptos.scan_records
    def counting_scan(*a, **kw):
        calls.append(a)
        return original(*a, **kw)
    monkeypatch.setattr(ptos, "scan_records", counting_scan)
    return calls


class TestHistorySuggestionsCached:
    def test_second_call_no_rescan(self, monkeypatch):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        calls = []
        original = ptos.scan_records
        def counting_scan(*a, **kw):
            calls.append(a)
            return original(*a, **kw)
        monkeypatch.setattr(ptos, "scan_records", counting_scan)
        first = svc.get_history_suggestions("expense")
        n_after_first = len(calls)
        second = svc.get_history_suggestions("expense")
        assert len(calls) == n_after_first
        assert first == second

    def test_append_record_invalidates(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        before = svc.get_history_suggestions("expense")
        assert "domain" in before["field_defaults"]
        assert "history:expense" in ptos._CACHE
        svc.append_record("2026-01-02 type=expense domain=home category=food amount=5")
        assert "history:expense" not in ptos._CACHE
        after = svc.get_history_suggestions("expense")
        assert after["field_defaults"]["domain"] in ("work", "home")

    def test_edit_record_invalidates(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        old = "2026-01-01 type=expense domain=work category=supplies amount=10"
        before = svc.get_history_suggestions("expense")
        assert before["field_defaults"].get("domain") == "work"
        filepath = os.path.join(ptos.RECORDS_DIR, "2026.log")
        svc.edit_record(filepath, old, ["domain=home"], None, lineno=0)
        assert "history:expense" not in ptos._CACHE
        after = svc.get_history_suggestions("expense")
        assert after["field_defaults"]["domain"] == "home"

    def test_delete_record_invalidates(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        old = "2026-01-01 type=expense domain=work category=supplies amount=10"
        filepath = os.path.join(ptos.RECORDS_DIR, "2026.log")
        svc.get_history_suggestions("expense")
        svc.delete_record(filepath, old, lineno=0)
        assert "history:expense" not in ptos._CACHE
        after = svc.get_history_suggestions("expense")
        assert after["field_defaults"] == {}
        assert after["field_values"] == {}

    def test_advance_record_invalidates(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        svc.get_history_suggestions("income")
        old = "2026-01-01 type=expense domain=work category=supplies amount=10"
        result = svc.advance_record(old, 0, "income", {"source": "gift"})
        assert result["ok"] is True
        assert result.get("new_line") is not None
        assert "history:income" not in ptos._CACHE
        after = svc.get_history_suggestions("income")
        assert after["field_defaults"].get("source") == "gift"

    def test_bulk_delete_invalidates(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        svc.get_history_suggestions("expense")
        result = svc.bulk_delete([_record_dict("2026-01-01 type=expense domain=work category=supplies amount=10")])
        assert result["deleted"] == 1
        assert "history:expense" not in ptos._CACHE
        after = svc.get_history_suggestions("expense")
        assert after["field_defaults"] == {}

    def test_bulk_set_invalidates(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        svc.get_history_suggestions("expense")
        result = svc.bulk_set([_record_dict("2026-01-01 type=expense domain=work category=supplies amount=10")],
                              ["domain=home"])
        assert result["updated"] == 1
        assert "history:expense" not in ptos._CACHE
        after = svc.get_history_suggestions("expense")
        assert after["field_defaults"]["domain"] == "home"

    def test_save_schema_invalidates(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        svc.get_history_suggestions("expense")
        assert "history:expense" in ptos._CACHE
        svc.save_schema(ptos.get_schema())
        assert all(not k.startswith("history:") and not k.startswith("condsug:")
                   for k in ptos._CACHE)


class TestSuggestionTtl:
    """The TTL is a backstop for writes that never reach the service (a
    hand-edited .log, a script writing records directly, the /editor rewrite
    path). Own-type writes still invalidate immediately."""

    def test_default_ttl_is_300(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        assert svc._suggestion_ttl() == 300

    def test_ttl_from_config(self, monkeypatch):
        _set_ttl(monkeypatch, 45)
        assert svc._suggestion_ttl() == 45

    def test_garbage_ttl_falls_back_to_default(self, monkeypatch):
        _set_ttl(monkeypatch, "soon")
        assert svc._suggestion_ttl() == 300
        _set_ttl(monkeypatch, -5)
        assert svc._suggestion_ttl() == 300

    def test_history_rebuilt_after_ttl(self, monkeypatch):
        clock = _Clock()
        monkeypatch.setattr(svc, "_monotonic", clock)
        _set_ttl(monkeypatch, 300)
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        calls = _counting_scans(monkeypatch)
        svc.get_history_suggestions("expense")
        assert len(calls) == 1
        clock.advance(299)
        svc.get_history_suggestions("expense")
        assert len(calls) == 1          # still fresh
        clock.advance(2)
        svc.get_history_suggestions("expense")
        assert len(calls) == 2          # aged out

    def test_unhooked_write_shows_up_after_ttl(self, monkeypatch):
        clock = _Clock()
        monkeypatch.setattr(svc, "_monotonic", clock)
        _set_ttl(monkeypatch, 300)
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        assert svc.get_history_suggestions("expense")["field_defaults"].get("domain") == "work"
        # Straight to disk — no service write path, so no invalidation at all
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10\n"
                      "2026-01-02 type=expense domain=home category=food amount=5")
        clock.advance(301)
        assert svc.get_history_suggestions("expense")["field_defaults"].get("domain") in ("work", "home")

    def test_ttl_zero_disables_expiry(self, monkeypatch):
        clock = _Clock()
        monkeypatch.setattr(svc, "_monotonic", clock)
        _set_ttl(monkeypatch, 0)
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        calls = _counting_scans(monkeypatch)
        svc.get_history_suggestions("expense")
        clock.advance(100000)
        svc.get_history_suggestions("expense")
        assert len(calls) == 1

    def test_condsug_expires_too(self, monkeypatch):
        clock = _Clock()
        monkeypatch.setattr(svc, "_monotonic", clock)
        _set_ttl(monkeypatch, 60)
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        calls = _counting_scans(monkeypatch)
        assert svc.get_conditional_suggestions("expense", "domain", "work") == {"category": "supplies"}
        n = len(calls)
        clock.advance(61)
        assert svc.get_conditional_suggestions("expense", "domain", "work") == {"category": "supplies"}
        assert len(calls) == n + 1

    def test_stamp_dropped_with_entry(self, monkeypatch):
        clock = _Clock()
        monkeypatch.setattr(svc, "_monotonic", clock)
        _set_ttl(monkeypatch, 300)
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        svc.get_history_suggestions("expense")
        svc.append_record("2026-01-02 type=expense domain=home category=food amount=5")
        assert "history:expense" not in ptos._CACHE
        assert "history:expense" not in svc._SUGGESTION_STAMP

    def test_engine_side_invalidation_leaves_no_stale_stamp(self, monkeypatch):
        """ptos.check_external_changes pops the key from _CACHE without going
        through the service — a surviving stamp must not resurrect it."""
        clock = _Clock()
        monkeypatch.setattr(svc, "_monotonic", clock)
        _set_ttl(monkeypatch, 300)
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        svc.get_history_suggestions("expense")
        ptos._CACHE.pop("history:expense")
        assert "history:expense" in svc._SUGGESTION_STAMP
        stale_stamp = svc._SUGGESTION_STAMP["history:expense"]
        calls = _counting_scans(monkeypatch)
        clock.advance(10)
        svc.get_history_suggestions("expense")
        assert len(calls) == 1                       # rebuilt, not a false hit
        assert svc._SUGGESTION_STAMP["history:expense"] > stale_stamp


class TestInvalidationBothTypes:
    def test_edit_that_changes_type_invalidates_both(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        svc.get_history_suggestions("expense")
        svc.get_history_suggestions("income")
        old = "2026-01-01 type=expense domain=work category=supplies amount=10"
        filepath = os.path.join(ptos.RECORDS_DIR, "2026.log")
        svc.edit_record(filepath, old, ["type=income"], None, lineno=0)
        assert "history:expense" not in ptos._CACHE
        assert "history:income" not in ptos._CACHE

    def test_bulk_set_type_change_invalidates_both(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        svc.get_history_suggestions("expense")
        svc.get_history_suggestions("income")
        svc.bulk_set([_record_dict("2026-01-01 type=expense domain=work category=supplies amount=10")],
                     ["type=income"])
        assert "history:expense" not in ptos._CACHE
        assert "history:income" not in ptos._CACHE

    def test_bulk_delete_keeps_unrelated_type_cached(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        svc.get_history_suggestions("expense")
        svc.get_history_suggestions("income")
        svc.bulk_delete([_record_dict("2026-01-01 type=expense domain=work category=supplies amount=10")])
        assert "history:expense" not in ptos._CACHE
        assert "history:income" in ptos._CACHE


class TestContextFilterLive:
    def test_filtered_tags_vary_per_context_record(self):
        os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
        lines = [
            "2026-01-01 type=expense domain=work category=supplies amount=10 tag=office",
            "2026-01-02 type=expense domain=work category=travel amount=20 tag=flight",
            "2026-01-03 type=expense domain=home category=food amount=5 tag=groceries",
        ]
        with open(os.path.join(ptos.RECORDS_DIR, "2026.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        work = svc.get_history_suggestions("expense", {"domain": "work"})
        home = svc.get_history_suggestions("expense", {"domain": "home"})
        assert "office" in work["filtered_tags"]
        assert "flight" in work["filtered_tags"]
        assert "office" not in home["filtered_tags"]
        assert "groceries" in home["filtered_tags"]


class TestConditionalSuggestionsCached:
    def test_second_call_identical_no_rescan(self, monkeypatch):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        calls = []
        original = ptos.scan_records
        def counting_scan(*a, **kw):
            calls.append(a)
            return original(*a, **kw)
        monkeypatch.setattr(ptos, "scan_records", counting_scan)
        first = svc.get_conditional_suggestions("expense", "domain", "work")
        n_after_first = len(calls)
        second = svc.get_conditional_suggestions("expense", "domain", "work")
        assert len(calls) == n_after_first
        assert first == second
        assert first.get("category") == "supplies"

    def test_write_invalidates_condsug(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        assert svc.get_conditional_suggestions("expense", "domain", "work").get("category") == "supplies"
        assert "condsug:expense:domain:work" in ptos._CACHE
        svc.append_record("2026-01-02 type=expense domain=work category=travel amount=9")
        assert "condsug:expense:domain:work" not in ptos._CACHE
        after = svc.get_conditional_suggestions("expense", "domain", "work")
        assert after.get("category") in ("supplies", "travel")


class TestGetRecordsCache:
    def test_second_call_no_rescan(self, monkeypatch):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        calls = _counting_scans(monkeypatch)
        first = svc.get_records([], "all")
        n_after_first = len(calls)
        second = svc.get_records([], "all")
        assert len(calls) == n_after_first
        assert first == second

    def test_distinct_params_distinct_entries(self, monkeypatch):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        calls = _counting_scans(monkeypatch)
        svc.get_records([], "all")
        svc.get_records(["type=expense"], "all")
        assert len(calls) == 2

    def test_returned_copy_is_isolated(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        first = svc.get_records([], "all")
        first["kind"] = "records"
        first["records"][0]["date"] = "MUTATED"
        second = svc.get_records([], "all")
        assert "kind" not in second
        assert second["records"][0]["date"] != "MUTATED"

    def test_write_invalidates(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        svc.get_records([], "all")
        assert any(k.startswith("recs:") for k in ptos._CACHE)
        svc.append_record("2026-01-02 type=expense domain=home category=food amount=5")
        assert not any(k.startswith("recs:") for k in ptos._CACHE)
        after = svc.get_records([], "all")
        assert after["count"] == 2

    def test_recs_prefix_watched_for_external_changes(self):
        assert "recs:" in ptos._EXT_RECORD_PREFIXES


class TestRecsDayRollover:
    def test_today_alias_not_served_after_midnight(self, monkeypatch):
        _write_record("2026-01-01 type=expense amount=10")
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 1, 1))
        first = svc.get_records([], "td")
        assert first["count"] == 1
        # Day advances and a new record lands straight on disk (no service
        # write, so nothing invalidates the cache).
        with open(os.path.join(ptos.RECORDS_DIR, "2026.log"), "w",
                  encoding="utf-8") as f:
            f.write("2026-01-01 type=expense amount=10\n"
                    "2026-01-02 type=expense amount=7\n")
        monkeypatch.setattr(ptos, "today", lambda: dt.date(2026, 1, 2))
        second = svc.get_records([], "td")
        assert second["count"] == 1
        assert "2026-01-02" in second["records"][0]["_line"]


class TestRecsStaleStoreGuard:
    def test_stores_when_generation_unchanged(self):
        _write_record("2026-01-01 type=expense amount=10")
        svc.get_records([], "all")
        assert any(k.startswith("recs:") for k in ptos._CACHE)

    def test_no_store_when_invalidated_mid_scan(self, monkeypatch):
        _write_record("2026-01-01 type=expense amount=10")
        original = ptos.scan_records

        def bumping_scan(*a, **kw):
            result = original(*a, **kw)
            ptos.bump_records_gen()
            return result

        monkeypatch.setattr(ptos, "scan_records", bumping_scan)
        svc.get_records([], "all")
        assert not any(k.startswith("recs:") for k in ptos._CACHE)


class TestRecsCacheBounded:
    def test_capped(self):
        _write_record("2026-01-01 type=expense amount=10")
        for i in range(svc._RECS_MAX + 5):
            svc.get_records([f"amount={i}"], "all")
        recs_keys = [k for k in ptos._CACHE if k.startswith("recs:")]
        assert len(recs_keys) == svc._RECS_MAX

    def test_hit_refreshes_recency(self):
        _write_record("2026-01-01 type=expense amount=10")
        for i in range(svc._RECS_MAX):
            svc.get_records([f"amount={i}"], "all")
        assert any("('amount=0',)" in k for k in ptos._CACHE)
        svc.get_records(["amount=0"], "all")           # cache hit, moves to MRU
        for i in range(svc._RECS_MAX, svc._RECS_MAX + 2):
            svc.get_records([f"amount={i}"], "all")
        assert any("('amount=0',)" in k for k in ptos._CACHE)   # refreshed, survived
        assert not any("('amount=1',)" in k for k in ptos._CACHE)  # evicted as oldest


class TestConfigChangeClearsRecs:
    def test_save_config_clears_recs(self):
        _write_record("2026-01-01 type=expense amount=10")
        svc.get_records([], "all")
        assert any(k.startswith("recs:") for k in ptos._CACHE)
        svc.save_config(ptos.get_config())
        assert not any(k.startswith("recs:") for k in ptos._CACHE)

    def test_external_config_change_clears_recs(self):
        _write_record("2026-01-01 type=expense amount=10")
        svc.get_records([], "all")
        ptos._invalidate_from_changes(["config/config.toml"])
        assert not any(k.startswith("recs:") for k in ptos._CACHE)

    def test_external_schema_change_clears_recs(self):
        _write_record("2026-01-01 type=expense amount=10")
        svc.get_records([], "all")
        ptos._invalidate_from_changes(["config/schema.toml"])
        assert not any(k.startswith("recs:") for k in ptos._CACHE)


class TestGetRecordsSingleParse:
    def test_scan_path_does_not_reparse(self, monkeypatch):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        def boom(line, format_date=True):
            raise AssertionError("get_records must not re-parse via _parse_record")
        monkeypatch.setattr(svc, "_parse_record", boom)
        result = svc.get_records([], "all")
        assert result["count"] == 1

    def test_build_row_matches_parse_record(self):
        line = "2026-01-01 type=expense domain=work category=supplies amount=10 | lunch"
        assert (svc._build_row_from_parsed(*ptos.safe_parse_line(line))
                == svc._parse_record(line))

    def test_scan_return_parsed_aligned(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        lines, total, parsed = ptos.scan_records(
            ptos.parse_from_to("2026-01-01"),
            ptos.parse_from_to("2026-12-31", as_end=True),
            [], None, return_parsed=True)
        assert len(parsed) == len(lines) == 1
        d, kv, note = parsed[0]
        assert d.isoformat() == "2026-01-01"
        assert kv["type"] == "expense"
