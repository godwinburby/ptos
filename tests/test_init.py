import os
import pytest
import ptos


@pytest.fixture(autouse=True)
def clear_cache():
    ptos._CACHE.clear()
    yield
    ptos._CACHE.clear()


@pytest.fixture
def ptos_home(tmp_path, monkeypatch):
    monkeypatch.setattr(ptos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(ptos, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
    monkeypatch.setattr(ptos, "JOURNAL_DIR", str(tmp_path / "journal"))
    monkeypatch.setattr(ptos, "TEMPLATE_DIR", str(tmp_path / "templates"))
    monkeypatch.setattr(ptos, "STARTER_DIR", str(tmp_path / "starters"))
    monkeypatch.setattr(ptos, "SCHEMA_PATH", str(tmp_path / "config" / "schema.toml"))
    monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "config" / "queries.toml"))
    monkeypatch.setattr(ptos, "CONFIG_PATH", str(tmp_path / "config" / "config.toml"))
    monkeypatch.setattr(ptos, "PRESETS_PATH", str(tmp_path / "config" / "presets.toml"))
    yield tmp_path


class TestInitPtos:
    def test_creates_directory_structure(self, ptos_home):
        ptos.init_ptos()
        assert (ptos_home / "config").is_dir()
        assert (ptos_home / "records").is_dir()
        assert (ptos_home / "journal").is_dir()
        assert (ptos_home / "templates").is_dir()

    def test_creates_config_files(self, ptos_home):
        ptos.init_ptos()
        assert (ptos_home / "config" / "config.toml").exists()
        assert (ptos_home / "config" / "schema.toml").exists()
        assert (ptos_home / "config" / "queries.toml").exists()
        assert (ptos_home / "config" / "presets.toml").exists()

    def test_creates_daily_template(self, ptos_home):
        ptos.init_ptos()
        assert (ptos_home / "templates" / "daily.md").exists()

    def test_creates_current_year_log(self, ptos_home):
        ptos.init_ptos()
        year = ptos.today().year
        assert (ptos_home / "records" / f"{year}.log").exists()

    def test_idempotent_no_errors(self, ptos_home):
        ptos.init_ptos()
        ptos.init_ptos()  # second run should not raise

    def test_uses_fallback_stubs_when_no_starters(self, ptos_home, monkeypatch):
        monkeypatch.setattr(ptos, "STARTER_DIR", str(ptos_home / "nonexistent"))
        ptos.init_ptos()
        content = (ptos_home / "config" / "config.toml").read_text()
        assert "[user]" in content


class TestDoctorCheck:
    def test_detects_missing_config(self, ptos_home):
        errors, warnings, messages, fixes = ptos.doctor_check()
        assert any("config" in e for e in errors)

    def test_fix_creates_missing_files(self, ptos_home):
        errors, warnings, messages, fixes = ptos.doctor_check(fix=True)
        assert (ptos_home / "config" / "config.toml").exists()
        assert (ptos_home / "config" / "schema.toml").exists()

    def test_ok_after_init(self, ptos_home):
        ptos.init_ptos()
        errors, warnings, messages, fixes = ptos.doctor_check()
        assert len(errors) == 0

    def test_json_output(self, ptos_home):
        result = ptos.doctor_check(json_output=True)
        assert "status" in result
        assert "checks" in result
        assert "errors" in result
        assert "warnings" in result

    def test_json_after_init(self, ptos_home):
        ptos.init_ptos()
        result = ptos.doctor_check(json_output=True)
        assert result["status"] in ("ok", "warnings")


class TestGetTodayJournal:
    def test_creates_journal_from_template(self, ptos_home, monkeypatch):
        ptos.init_ptos()
        monkeypatch.setattr(ptos, "today", lambda: __import__("datetime").date(2026, 5, 16))
        path = ptos.get_today_journal()
        assert path == str(ptos_home / "journal" / "2026" / "2026-05-16.md")
        content = (ptos_home / "journal" / "2026" / "2026-05-16.md").read_text()
        assert "2026-05-16" in content

    def test_returns_existing_path(self, ptos_home, monkeypatch):
        ptos.init_ptos()
        monkeypatch.setattr(ptos, "today", lambda: __import__("datetime").date(2026, 5, 16))
        path1 = ptos.get_today_journal()
        path2 = ptos.get_today_journal()
        assert path1 == path2

    def test_uses_fallback_when_no_template(self, ptos_home, monkeypatch):
        monkeypatch.setattr(ptos, "today", lambda: __import__("datetime").date(2026, 5, 16))
        (ptos_home / "journal").mkdir(parents=True)
        path = ptos.get_today_journal()
        assert (ptos_home / "journal" / "2026" / "2026-05-16.md").exists()
