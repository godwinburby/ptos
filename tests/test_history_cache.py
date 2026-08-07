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
