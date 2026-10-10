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
        assert "*.bak" in stignore.read_text()

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

    def test_init_writes_no_session_secret(self, ptos_home):
        ptos.init_ptos()
        cfg = ptos.get_config()
        assert "secret_key" not in (cfg.get("server") or {})

    def test_init_writes_no_secret_even_without_starters(self, ptos_home,
                                                         monkeypatch):
        monkeypatch.setattr(ptos, "STARTER_DIR", str(ptos_home / "nonexistent"))
        ptos.init_ptos()
        assert "secret_key" not in (ptos.get_config().get("server") or {})

    def test_init_does_not_modify_a_config_already_holding_a_secret(
            self, ptos_home):
        import tomli_w
        ptos.init_ptos()
        cfg = ptos.get_config()
        cfg.setdefault("server", {})["secret_key"] = "legacy-shared-key"
        with ptos.AtomicWrite(ptos.CONFIG_PATH, "config") as w:
            tomli_w.dump(cfg, w.stream)
        ptos._CACHE.pop("config", None)
        path = os.path.join(ptos_home, "config", "config.toml")
        before = open(path, encoding="utf-8").read()

        ptos.init_ptos()
        ptos._CACHE.pop("config", None)

        assert open(path, encoding="utf-8").read() == before
        assert ptos.get_config()["server"]["secret_key"] == "legacy-shared-key"


class TestInitKeepsConfigComments:
    """--init must never rewrite config.toml wholesale.

    tomli_w drops every comment, so a rewrite silently stripped the starter's
    46 explanatory lines from the file a new user is told to edit by hand.
    """

    @staticmethod
    def _comments(text):
        return {l for l in text.splitlines() if l.strip().startswith("#")}

    @staticmethod
    def _use_real_starters(monkeypatch):
        # ptos_home points STARTER_DIR at a scratch copy that does not exist,
        # so init falls back to its built-in stubs (which carry no comments).
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        monkeypatch.setattr(ptos, "STARTER_DIR",
                            os.path.join(repo, "starters"))
        return os.path.join(repo, "starters", "starter_config.toml")

    def test_fresh_init_keeps_every_starter_comment(self, ptos_home, monkeypatch):
        starter_path = self._use_real_starters(monkeypatch)
        starter = open(starter_path, encoding="utf-8").read()

        # Start from nothing, as a brand-new install would.
        if os.path.exists(ptos.CONFIG_PATH):
            os.remove(ptos.CONFIG_PATH)
        ptos._CACHE.pop("config", None)
        ptos.init_ptos()
        ptos._CACHE.pop("config", None)

        produced = open(ptos.CONFIG_PATH, encoding="utf-8").read()
        starter_comments = self._comments(starter)
        produced_comments = self._comments(produced)
        missing = starter_comments - produced_comments
        added = produced_comments - starter_comments
        assert starter_comments == produced_comments, (
            f"{len(missing)} starter comment(s) lost, {len(added)} unexpected")

    def test_fresh_init_keeps_comment_count(self, ptos_home, monkeypatch):
        starter_path = self._use_real_starters(monkeypatch)
        starter = open(starter_path, encoding="utf-8").read()

        if os.path.exists(ptos.CONFIG_PATH):
            os.remove(ptos.CONFIG_PATH)
        ptos._CACHE.pop("config", None)
        ptos.init_ptos()
        ptos._CACHE.pop("config", None)

        produced = open(ptos.CONFIG_PATH, encoding="utf-8").read()
        assert len(self._comments(produced)) == len(self._comments(starter))

    def test_second_init_changes_nothing(self, ptos_home):
        ptos.init_ptos()
        path = os.path.join(ptos_home, "config", "config.toml")
        before = open(path, encoding="utf-8").read()

        ptos.init_ptos()
        ptos._CACHE.pop("config", None)

        assert open(path, encoding="utf-8").read() == before

    def test_settings_style_rewrite_is_the_documented_limitation(
            self, ptos_home, monkeypatch):
        # Everything written through tomli_w.dump loses comments, which is why
        # the README tells users to hand-edit config.toml to keep them. This
        # pins the *current* behaviour so adopting a comment-preserving writer
        # (or not) stays a deliberate choice rather than an accident.
        import tomli_w
        self._use_real_starters(monkeypatch)
        if os.path.exists(ptos.CONFIG_PATH):
            os.remove(ptos.CONFIG_PATH)
        ptos._CACHE.pop("config", None)
        ptos.init_ptos()
        ptos._CACHE.pop("config", None)

        before = open(ptos.CONFIG_PATH, encoding="utf-8").read()
        assert self._comments(before)

        cfg = ptos.get_config()
        cfg["user"] = {**(cfg.get("user") or {}), "name": "Comment Stripper"}
        with ptos.AtomicWrite(ptos.CONFIG_PATH, "config") as w:
            tomli_w.dump(cfg, w.stream)
        ptos._CACHE.pop("config", None)

        after = open(ptos.CONFIG_PATH, encoding="utf-8").read()
        assert not self._comments(after)
        assert ptos.get_config()["user"]["name"] == "Comment Stripper"


class TestSessionSecret:
    def test_is_ephemeral_and_changing(self, ptos_home):
        first = ptos.session_secret()
        second = ptos.session_secret()
        assert first != second
        assert len(first) == 64
        assert all(c in "0123456789abcdef" for c in first)

    def test_has_at_least_32_bytes_of_entropy(self, ptos_home):
        assert len(ptos.session_secret()) // 2 == 32
        assert len(ptos.generate_secret_key(32)) // 2 == 32

    def test_ptos_secret_key_env_var_is_pinned(self, ptos_home, monkeypatch):
        monkeypatch.setenv("PTOS_SECRET_KEY", "a-fixed-key-for-tooling")
        assert ptos.session_secret() == "a-fixed-key-for-tooling"

    def test_empty_env_var_falls_back_to_a_random_key(self, ptos_home,
                                                      monkeypatch):
        monkeypatch.setenv("PTOS_SECRET_KEY", "")
        secret = ptos.session_secret()
        assert secret
        assert secret != ""

    def test_config_secret_key_is_ignored(self, ptos_home):
        import tomli_w
        ptos.init_ptos()
        cfg = ptos.get_config()
        cfg.setdefault("server", {})["secret_key"] = "a-syncthing-shared-key"
        with ptos.AtomicWrite(ptos.CONFIG_PATH, "config") as w:
            tomli_w.dump(cfg, w.stream)
        ptos._CACHE.pop("config", None)

        secret = ptos.session_secret()
        assert secret != "a-syncthing-shared-key"
        assert len(secret) == 64
        assert "secret_key" in ptos.get_config()["server"]

    def test_reading_a_stale_key_does_not_error_or_repair_it(self, ptos_home):
        import tomli_w
        ptos.init_ptos()
        cfg = ptos.get_config()
        cfg.setdefault("server", {})["secret_key"] = "   "
        with ptos.AtomicWrite(ptos.CONFIG_PATH, "config") as w:
            tomli_w.dump(cfg, w.stream)
        ptos._CACHE.pop("config", None)

        assert ptos.session_secret() != "   "
        assert len(ptos.get_config()["server"]["secret_key"]) == 3

    def test_two_process_starts_produce_different_keys(self, ptos_home):
        # A process start resolves the key once, at import. Two independent
        # resolutions stand in for two starts; neither consults config, so
        # there is nothing for them to converge on.
        starts = {ptos.session_secret() for _ in range(8)}
        assert len(starts) == 8

    def test_no_secret_in_the_starter_file(self):
        # The starter ships to every install, so a secret there would be shared.
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        text = open(os.path.join(repo, "starters", "starter_config.toml"),
                    encoding="utf-8").read()
        assert "# secret_key" in text
        for line in text.splitlines():
            if line.strip().startswith("secret_key"):
                assert line.strip().startswith("#"), line

    def test_web_app_uses_an_ephemeral_secret(self, ptos_home):
        # ptos_web may already be imported by an earlier test (and therefore
        # bound to a different test home), so assert on the property that
        # matters: a real per-install key, never the old hardcoded literal,
        # and nothing read back out of a config file.
        import ptos_web
        secret = ptos_web.app.secret_key
        assert secret
        assert len(secret) >= 32
        assert secret != "ptos-local-only"
        assert secret not in (ptos.get_config().get("server") or {}).values()

    def test_web_app_secret_is_not_the_config_key(self, ptos_home):
        import tomli_w
        import ptos_web
        ptos.init_ptos()
        # A stale key left in config must not become the live one.
        secret = ptos_web.app.secret_key
        cfg = ptos.get_config()
        cfg.setdefault("server", {})["secret_key"] = "stale-value"
        with ptos.AtomicWrite(ptos.CONFIG_PATH, "config") as w:
            tomli_w.dump(cfg, w.stream)
        assert secret != "stale-value"


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
