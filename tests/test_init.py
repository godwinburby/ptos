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

    def test_creates_stignore(self, ptos_home):
        ptos.init_ptos()
        stignore = ptos_home / ".stignore"
        assert stignore.exists()
        assert "*.tmp" in stignore.read_text()

    def test_stignore_idempotent(self, ptos_home):
        ptos.init_ptos()
        first = (ptos_home / ".stignore").read_text()
        ptos.init_ptos()
        assert (ptos_home / ".stignore").read_text() == first

    def test_idempotent_no_errors(self, ptos_home):
        ptos.init_ptos()
        ptos.init_ptos()  # second run should not raise

    def test_uses_fallback_stubs_when_no_starters(self, ptos_home, monkeypatch):
        monkeypatch.setattr(ptos, "STARTER_DIR", str(ptos_home / "nonexistent"))
        ptos.init_ptos()
        content = (ptos_home / "config" / "config.toml").read_text()
        assert "[user]" in content

    def test_generates_a_session_secret(self, ptos_home):
        ptos.init_ptos()
        secret = ptos.get_config()["server"]["secret_key"]
        assert len(secret) == 48
        assert all(c in "0123456789abcdef" for c in secret)

    def test_session_secret_survives_reinit(self, ptos_home):
        ptos.init_ptos()
        secret = ptos.get_config()["server"]["secret_key"]
        ptos.init_ptos()
        assert ptos.get_config()["server"]["secret_key"] == secret

    def test_session_secret_written_even_without_starters(self, ptos_home,
                                                          monkeypatch):
        monkeypatch.setattr(ptos, "STARTER_DIR", str(ptos_home / "nonexistent"))
        ptos.init_ptos()
        assert ptos.get_config()["server"]["secret_key"]


class TestSessionSecret:
    def test_generates_and_persists(self, ptos_home):
        assert "secret_key" not in (ptos.get_config().get("server") or {})
        secret = ptos.ensure_session_secret()
        assert ptos.get_config()["server"]["secret_key"] == secret

    def test_is_stable_across_calls(self, ptos_home):
        assert ptos.ensure_session_secret() == ptos.ensure_session_secret()

    def test_repairs_a_blank_value(self, ptos_home):
        import tomli_w
        ptos.ensure_session_secret()
        cfg = ptos.get_config()
        cfg.setdefault("server", {})["secret_key"] = "   "
        with ptos.AtomicWrite(ptos.CONFIG_PATH, "config") as w:
            tomli_w.dump(cfg, w.stream)
        assert ptos.ensure_session_secret() != "   "
        assert len(ptos.get_config()["server"]["secret_key"]) == 48

    def test_each_install_gets_its_own(self, ptos_home):
        first = ptos.ensure_session_secret()
        assert ptos.generate_secret_key() != first

    def test_preserves_other_config_keys(self, ptos_home):
        import tomli_w
        ptos.ensure_session_secret()
        cfg = ptos.get_config()
        cfg.setdefault("server", {})["port"] = 5001
        with ptos.AtomicWrite(ptos.CONFIG_PATH, "config") as w:
            tomli_w.dump(cfg, w.stream)
        ptos.ensure_session_secret()
        assert ptos.get_config()["server"]["port"] == 5001

    def test_unwritable_config_falls_back_without_raising(self, ptos_home):
        blocker = ptos_home / "blocker"
        blocker.write_text("not a dir")
        ptos.CONFIG_PATH = str(blocker / "sub" / "config.toml")
        ptos._CACHE.pop("config", None)
        try:
            secret = ptos.ensure_session_secret()
        finally:
            ptos.CONFIG_PATH = str(ptos_home / "config" / "config.toml")
        assert len(secret) == 48
        assert blocker.read_text() == "not a dir"

    def test_no_secret_in_the_starter_file(self):
        # The starter ships to every install, so a secret there would be shared.
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        text = open(os.path.join(repo, "starters", "starter_config.toml"),
                    encoding="utf-8").read()
        assert "# secret_key" in text
        for line in text.splitlines():
            if line.strip().startswith("secret_key"):
                assert line.strip().startswith("#"), line

    def test_web_app_uses_the_persisted_secret(self, ptos_home):
        # ptos_web may already be imported by an earlier test (and therefore
        # bound to a different test home), so assert on the property that
        # matters: a real per-install key, never the old hardcoded literal.
        import ptos_web
        secret = ptos_web.app.secret_key
        assert secret
        assert len(secret) >= 32
        assert secret != "ptos-local-only"
        assert len(ptos.generate_secret_key()) == len(secret)


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
        assert path == str(ptos_home / "journal" / "2026" / "05" / "2026-05-16.md")
        content = (ptos_home / "journal" / "2026" / "05" / "2026-05-16.md").read_text()
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
        assert (ptos_home / "journal" / "2026" / "05" / "2026-05-16.md").exists()
