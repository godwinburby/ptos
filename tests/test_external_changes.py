import json
import os
import time

import pytest

import ptos
import ptos_service as svc


@pytest.fixture(autouse=True)
def _clean_watch():
    ptos.reset_external_watch()
    yield
    ptos.reset_external_watch()


def _write_record(year=2026, line=None, name=None):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    path = os.path.join(ptos.RECORDS_DIR, name or f"{year}.log")
    text = line or f"{year}-01-01 type=expense domain=work category=supplies amount=10"
    mode = "a" if os.path.exists(path) else "w"
    with open(path, mode, encoding="utf-8") as f:
        f.write(text + "\n")
    return path


def _touch_config(name, content):
    path = os.path.join(ptos.CONFIG_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _seed_cache():
    """Fill _CACHE with one entry per prefix the watcher can clear."""
    ptos._CACHE["frwl:all"] = [("x", 1)]
    ptos._CACHE["history:expense"] = {"field_defaults": {}}
    ptos._CACHE["condsug:expense:domain:work"] = {"category": "supplies"}
    ptos._CACHE["habit:meditation:tm::"] = {"streak": 1}
    ptos._CACHE["calendar:__all__:2026:10"] = {"total_records": 1}
    ptos._CACHE["log_files"] = ["2026.log"]


class TestSignature:
    def test_signature_lists_record_and_config_files(self):
        _write_record()
        sig = ptos._data_signature()
        names = [rel for rel, _mtime, _size in sig]
        assert "records/2026.log" in names
        assert "config/schema.toml" in names

    def test_signature_ignores_non_log_files(self):
        _write_record()
        with open(os.path.join(ptos.RECORDS_DIR, "notes.txt"), "w", encoding="utf-8") as f:
            f.write("ignored")
        names = [rel for rel, _m, _s in ptos._data_signature()]
        assert not any(rel.endswith("notes.txt") for rel in names)

    def test_signature_is_stable_without_changes(self):
        _write_record()
        assert ptos._data_signature() == ptos._data_signature()

    def test_diff_reports_added_removed_and_modified(self):
        old = (("records/a.log", 1, 10), ("records/b.log", 2, 20))
        new = (("records/a.log", 1, 11), ("records/c.log", 3, 30))
        assert ptos._diff_signature(old, new) == [
            "records/a.log", "records/b.log", "records/c.log"]


class TestCheckExternalChanges:
    def test_first_call_only_baselines(self):
        _write_record()
        result = ptos.check_external_changes(force=True)
        assert result["checked"] is True
        assert result["changed"] is False
        assert result["files"] == []

    def test_throttle_skips_second_call(self):
        _write_record()
        ptos.check_external_changes(force=True)
        second = ptos.check_external_changes()
        assert second["checked"] is False

    def test_no_change_reports_nothing(self):
        _write_record()
        ptos.check_external_changes(force=True)
        result = ptos.check_external_changes(force=True)
        assert result["checked"] is True
        assert result["changed"] is False

    def test_external_record_write_is_detected(self):
        _write_record()
        ptos.check_external_changes(force=True)
        _write_record(line="2026-02-02 type=expense domain=home category=food amount=5")
        result = ptos.check_external_changes(force=True)
        assert result["changed"] is True
        assert result["files"] == ["records/2026.log"]

    def test_external_record_write_drops_record_caches(self):
        _write_record()
        _seed_cache()
        ptos.check_external_changes(force=True)
        _write_record(line="2026-03-03 type=income source=gift amount=1")
        ptos.check_external_changes(force=True)
        assert not [k for k in ptos._CACHE
                    if k.startswith(("frwl:", "history:", "condsug:",
                                     "habit:", "calendar:"))]
        assert "log_files" not in ptos._CACHE

    def test_record_change_keeps_schema_caches(self):
        _write_record()
        ptos._CACHE["schema"] = {"types": {}}
        ptos._CACHE["derived_fields"] = ["x"]
        ptos.check_external_changes(force=True)
        _write_record(line="2026-04-04 type=expense domain=work category=supplies amount=99")
        ptos.check_external_changes(force=True)
        assert ptos._CACHE["schema"] == {"types": {}}
        assert ptos._CACHE["derived_fields"] == ["x"]

    def test_external_schema_change_drops_schema_and_record_caches(self):
        _write_record()
        ptos._CACHE["schema"] = {"types": {}}
        ptos._CACHE["derived_fields"] = ["x"]
        ptos._CACHE["frwl:all"] = [("x", 1)]
        ptos._CACHE["history:expense"] = {}
        ptos.check_external_changes(force=True)
        _touch_config("schema.toml", '[types]\nallowed = ["expense"]\n')
        result = ptos.check_external_changes(force=True)
        assert "config/schema.toml" in result["files"]
        assert "schema" not in ptos._CACHE
        assert "derived_fields" not in ptos._CACHE
        assert "frwl:all" not in ptos._CACHE
        assert "history:expense" not in ptos._CACHE

    def test_schema_change_clears_filter_memos(self):
        _write_record()
        ptos._WHERE_TOKEN_CACHE["a AND b"] = ("a", "AND", "b")
        ptos._IS_EXPRESSION_CACHE["a"] = (True,)
        ptos._FILTER_DERIVED_CACHE["x=1"] = ("x",)
        ptos.check_external_changes(force=True)
        _touch_config("schema.toml", '[types]\nallowed = ["expense"]\n')
        ptos.check_external_changes(force=True)
        assert ptos._WHERE_TOKEN_CACHE == {}
        assert ptos._IS_EXPRESSION_CACHE == {}
        assert ptos._FILTER_DERIVED_CACHE == {}

    def test_external_queries_change_drops_only_queries(self):
        _write_record()
        ptos._CACHE["queries"] = {"query.a": {}}
        ptos._CACHE["schema"] = {"types": {}}
        ptos.check_external_changes(force=True)
        _touch_config("queries.toml", '["query.new"]\nwhere = "type=expense"\n')
        ptos.check_external_changes(force=True)
        assert "queries" not in ptos._CACHE
        assert ptos._CACHE["schema"] == {"types": {}}

    def test_external_config_change_drops_config_only(self):
        _write_record()
        ptos._CACHE["config"] = {"server": {}}
        ptos._CACHE["schema"] = {"types": {}}
        ptos.check_external_changes(force=True)
        _touch_config("config.toml", "[server]\nport = 5000\n")
        ptos.check_external_changes(force=True)
        assert "config" not in ptos._CACHE
        assert ptos._CACHE["schema"] == {"types": {}}

    def test_new_log_file_is_detected(self):
        _write_record(2026)
        ptos.check_external_changes(force=True)
        _write_record(2025)
        result = ptos.check_external_changes(force=True)
        assert "records/2025.log" in result["files"]

    def test_locked_sweep_is_skipped_not_queued(self):
        _write_record()
        assert ptos._EXT_WATCH_LOCK.acquire(blocking=False) is True
        try:
            result = ptos.check_external_changes(force=True)
        finally:
            ptos._EXT_WATCH_LOCK.release()
        assert result["checked"] is False
        assert result["changed"] is False

    def test_reset_rebaselines(self):
        _write_record()
        ptos.check_external_changes(force=True)
        ptos.reset_external_watch()
        assert ptos.check_external_changes(force=True)["changed"] is False

    def test_own_write_does_not_report_as_external(self):
        _write_record()
        ptos.check_external_changes(force=True)
        svc.append_record("2026-05-05 type=expense domain=home category=food amount=7")
        assert ptos.check_external_changes(force=True)["changed"] is False


class TestBackupStateManifest:
    def test_snapshot_comparison_detects_backdated_edit(self):
        os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
        _write_record()
        path = os.path.join(ptos.RECORDS_DIR, "2026.log")
        os.utime(path, (1_000_000, 1_000_000))  # ancient mtime
        ptos.write_backup_state()
        assert ptos.should_backup() is False

        # A sync rewrite with an mtime older than the last backup: the old
        # mtime-only test could not see this.
        os.utime(path, (900_000, 900_000))
        with open(path, "a", encoding="utf-8") as f:
            f.write("2026-06-06 type=expense domain=home category=food amount=3\n")
        os.utime(path, (900_000, 900_000))
        assert ptos.should_backup() is True

    def test_snapshot_detects_new_file(self):
        _write_record()
        ptos.write_backup_state()
        assert ptos.should_backup() is False
        _write_record(2025)
        assert ptos.should_backup() is True

    def test_snapshot_detects_deleted_file(self):
        _write_record()
        ptos.write_backup_state()
        os.remove(os.path.join(ptos.RECORDS_DIR, "2026.log"))
        assert ptos.should_backup() is True

    def test_snapshot_ignores_bak_and_tmp(self):
        _write_record()
        ptos.write_backup_state()
        with open(os.path.join(ptos.RECORDS_DIR, "2026.log.bak"), "w", encoding="utf-8") as f:
            f.write("scratch")
        assert ptos.should_backup() is False

    def test_backup_data_records_snapshot(self):
        _write_record()
        path = ptos.backup_data()
        assert os.path.exists(path)
        with open(ptos._backup_state_path(), encoding="utf-8") as f:
            state = json.load(f)
        assert "records/2026.log" in state
        assert ptos.should_backup() is False

    def test_missing_snapshot_falls_back_to_mtime(self, monkeypatch):
        os.makedirs(ptos.BACKUP_DIR, exist_ok=True)
        # A backup stamped a few seconds ahead — nothing on disk can be newer.
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(time.time() + 5))
        with open(os.path.join(ptos.BACKUP_DIR, f"ptos-backup-full-{stamp}.zip"), "w") as f:
            f.write("stub")
        _write_record()
        assert ptos.should_backup() is False
        # Nothing newer than the old backup, so a baseline snapshot is written
        # and the next call uses exact comparison.
        assert os.path.exists(ptos._backup_state_path())
        with open(ptos._backup_state_path(), encoding="utf-8") as f:
            assert "records/2026.log" in json.load(f)

    def test_missing_snapshot_backups_when_data_is_newer(self):
        os.makedirs(ptos.BACKUP_DIR, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(time.time() - 600))
        with open(os.path.join(ptos.BACKUP_DIR, f"ptos-backup-full-{stamp}.zip"), "w") as f:
            f.write("stub")
        _write_record()
        assert ptos.should_backup() is True
        assert not os.path.exists(ptos._backup_state_path())

    def test_corrupt_snapshot_is_ignored(self):
        _write_record()
        os.makedirs(ptos.BACKUP_DIR, exist_ok=True)
        with open(ptos._backup_state_path(), "w", encoding="utf-8") as f:
            f.write("{not json")
        assert ptos.should_backup() in (True, False)


class TestWebWatcherWiring:
    def test_start_thread_honours_zero(self):
        import ptos_web
        assert ptos_web._start_external_watch_thread.__doc__

    def test_config_key_ships_in_starter(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        text = open(os.path.join(root, "starters", "starter_config.toml"),
                    encoding="utf-8").read()
        assert "external_check_seconds = 5" in text

    def test_page_render_checks_for_external_changes(self, monkeypatch):
        import ptos_web
        calls = []
        original = ptos.check_external_changes

        def counting(force=False):
            calls.append(force)
            return original(force=force)

        monkeypatch.setattr(ptos, "check_external_changes", counting)
        ptos_web.app.test_client().get("/")
        assert calls, "page render did not run the external-change check"
