import os
import pytest
import ptos


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    records_dir = tmp_path / "records"
    config_dir.mkdir()
    records_dir.mkdir()

    _write(config_dir / "config.toml", """
[user]
name = "TestUser"

[display]
currency = "$"
date_format = "us"

[backup]
folders = ["records", "config"]
max_full_backups = 5
max_config_backups = 3
backup_if_files_changed = true
""")
    _write(config_dir / "schema.toml", """
[global_fields.person]
type = "string"
options = ["alice", "bob"]

[global_fields.context]
type = "string"
""")
    _write(config_dir / "queries.toml", """
[my_query]
where = "type=expense"
time = "this-month"
""")
    _write(config_dir / "presets.toml", """
[presets.coffee]
type = "expense"
category = "food"

[presets.travel]
type = "expense"
category = "travel"
""")
    _write(tmp_path / ".version", "abc123\n")

    records_dir.joinpath("2025.log").write_text("", encoding="utf-8")
    records_dir.joinpath("2026.log").write_text("", encoding="utf-8")

    monkeypatch.setattr(ptos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(ptos, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(ptos, "RECORDS_DIR", str(records_dir))
    monkeypatch.setattr(ptos, "SCHEMA_PATH", str(config_dir / "schema.toml"))
    monkeypatch.setattr(ptos, "CONFIG_PATH", str(config_dir / "config.toml"))
    monkeypatch.setattr(ptos, "QUERIES_PATH", str(config_dir / "queries.toml"))
    monkeypatch.setattr(ptos, "PRESETS_PATH", str(config_dir / "presets.toml"))
    monkeypatch.setattr(ptos, "VERSION_FILE", str(tmp_path / ".version"))
    ptos._CACHE.clear()
    yield
    ptos._CACHE.clear()


class TestGetConfig:
    def test_returns_config_dict(self, cfg):
        config = ptos.get_config()
        assert config["user"]["name"] == "TestUser"
        assert config["display"]["currency"] == "$"

    def test_missing_file_returns_empty(self, monkeypatch):
        monkeypatch.setattr(ptos, "CONFIG_PATH", "/nonexistent/config.toml")
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        assert ptos.get_config() == {}


class TestGetQueries:
    def test_returns_queries_dict(self, cfg):
        queries = ptos.get_queries()
        assert "my_query" in queries
        assert queries["my_query"]["where"] == "type=expense"


class TestGetPresets:
    def test_returns_presets_dict(self, cfg):
        presets = ptos.get_presets()
        assert "coffee" in presets
        assert presets["coffee"]["category"] == "food"

    def test_missing_file_returns_empty(self, monkeypatch):
        monkeypatch.setattr(ptos, "PRESETS_PATH", "/nonexistent/presets.toml")
        assert ptos.get_presets() == {}


class TestGetLogFiles:
    def test_lists_log_files(self, cfg):
        files = ptos.get_log_files()
        assert "2025.log" in files
        assert "2026.log" in files

    def test_excludes_conflicts(self, cfg, tmp_path):
        records_dir = tmp_path / "records"
        records_dir.joinpath("2026 (conflict).log").write_text("")
        files = ptos.get_log_files()
        assert "2026 (conflict).log" not in files

    def test_empty_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "empty"))
        assert ptos.get_log_files() == []


class TestGetGlobalFields:
    def test_returns_global_fields(self, cfg):
        fields = ptos.get_global_fields()
        assert "person" in fields
        assert fields["person"]["type"] == "string"

    def test_accepts_schema_param(self, cfg):
        fields = ptos.get_global_fields(schema={"global_fields": {"custom": {"type": "int"}}})
        assert fields == {"custom": {"type": "int"}}

    def test_none_when_not_configured(self, cfg):
        fields = ptos.get_global_fields(schema={})
        assert fields == {}


class TestBackupConfig:
    def test_backup_config(self, cfg):
        bc = ptos.get_backup_config()
        assert bc["folders"] == ["records", "config"]
        assert bc["max_full_backups"] == 5
        assert bc["max_config_backups"] == 3

    def test_backup_folders(self, cfg):
        folders = ptos.get_backup_folders()
        assert "records" in folders
        assert "config" in folders

    def test_backup_folders_filters_missing(self, cfg, monkeypatch):
        monkeypatch.setattr(ptos, "get_backup_config", lambda: {"folders": ["records", "nonexistent"]})
        folders = ptos.get_backup_folders()
        assert "records" in folders
        assert "nonexistent" not in folders

    def test_max_backups(self, cfg):
        assert ptos.get_backup_max_backups() == 5

    def test_max_backups_default(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_backup_config", lambda: {})
        assert ptos.get_backup_max_backups() == 10  # MAX_BACKUPS

    def test_max_config_backups(self, cfg):
        assert ptos.get_backup_max_config_backups() == 3

    def test_max_config_backups_default(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_backup_config", lambda: {})
        assert ptos.get_backup_max_config_backups() == 10


class TestVersion:
    def test_get_current_version(self, cfg):
        assert ptos.get_current_version() == "abc123"

    def test_get_version_none_when_missing(self, monkeypatch):
        monkeypatch.setattr(ptos, "VERSION_FILE", "/nonexistent/.version")
        assert ptos.get_current_version() is None

    def test_save_current_version(self, cfg, tmp_path):
        ptos.save_current_version("def456")
        assert (tmp_path / ".version").read_text().strip() == "def456"

    def test_init_version_skips_if_exists(self, tmp_path, monkeypatch):
        ver_file = tmp_path / ".version"
        ver_file.write_text("existing")
        monkeypatch.setattr(ptos, "VERSION_FILE", str(ver_file))
        monkeypatch.setattr(ptos, "BASE_DIR", str(tmp_path))
        ptos.init_version()
        assert ver_file.read_text().strip() == "existing"

    def test_init_version_uses_git(self, tmp_path, monkeypatch):
        ver_file = tmp_path / ".version"
        monkeypatch.setattr(ptos, "VERSION_FILE", str(ver_file))
        monkeypatch.setattr(ptos, "BASE_DIR", str(tmp_path))
        monkeypatch.setattr(ptos, "SCRIPT_DIR", str(tmp_path))
        (tmp_path / ".git").mkdir()
        import subprocess
        orig = subprocess.run
        def fake_run(*a, **kw):
            class Res:
                returncode = 0
                stdout = "deadbeef\n"
                stderr = ""
            return Res()
        monkeypatch.setattr(subprocess, "run", fake_run)
        ptos.init_version()
        assert ver_file.read_text().strip() == "deadbeef"

    def test_init_version_uses_github_fallback(self, tmp_path, monkeypatch):
        ver_file = tmp_path / ".version"
        monkeypatch.setattr(ptos, "VERSION_FILE", str(ver_file))
        monkeypatch.setattr(ptos, "BASE_DIR", str(tmp_path))
        monkeypatch.setattr(ptos, "SCRIPT_DIR", str(tmp_path))
        class FakeResponse:
            def read(self): return b'{"sha": "fromapi"}'
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def __iter__(self): return iter([b'{"sha": "fromapi"}'])
        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResponse())
        ptos.init_version()
        assert ver_file.read_text().strip() == "fromapi"


class TestResolveEditor:
    def test_config_takes_priority(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_config", lambda: {"editor": {"command": "nvim"}})
        monkeypatch.delenv("EDITOR", raising=False)
        assert ptos.resolve_editor() == ["nvim"]

    def test_env_var_when_no_config(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        monkeypatch.setenv("EDITOR", "code --wait")
        assert ptos.resolve_editor() == ["code", "--wait"]

    def test_fallback_notepad_on_windows(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        monkeypatch.delenv("EDITOR", raising=False)
        monkeypatch.setattr(os, "name", "nt")
        assert ptos.resolve_editor() == ["notepad"]

    def test_fallback_nvim_on_unix(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        monkeypatch.delenv("EDITOR", raising=False)
        monkeypatch.setattr(os, "name", "posix")
        assert ptos.resolve_editor() == ["nvim"]


class TestCurrency:
    def test_currency_from_config(self, cfg):
        assert ptos.currency() == "$"

    def test_currency_default(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        assert ptos.currency() == ""

    def test_date_format_from_config(self, cfg):
        assert ptos.date_format() == "us"

    def test_date_format_default(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        assert ptos.date_format() == "indian"


class TestSetUserName:
    def test_sets_name(self, cfg, capsys):
        ptos.set_user_name("Alice")
        out = capsys.readouterr().out
        assert "Alice" in out
        config = ptos.get_config()
        assert config["user"]["name"] == "Alice"

    def test_empty_name_exits(self, cfg):
        with pytest.raises(SystemExit):
            ptos.set_user_name("")

    def test_whitespace_name_exits(self, cfg):
        with pytest.raises(SystemExit):
            ptos.set_user_name("   ")

    def test_handles_missing_config(self, monkeypatch):
        monkeypatch.setattr(ptos, "CONFIG_PATH", "/nonexistent/config.toml")
        with pytest.raises(SystemExit):
            ptos.set_user_name("Bob")


class TestSetDateFormat:
    def test_sets_valid_format(self, cfg):
        ptos.set_date_format("iso")
        assert ptos.date_format() == "iso"

    def test_invalid_format_exits(self, cfg):
        with pytest.raises(SystemExit):
            ptos.set_date_format("garbage")

    def test_empty_format_exits(self, cfg):
        with pytest.raises(SystemExit):
            ptos.set_date_format("")

    def test_none_format_exits(self, cfg):
        with pytest.raises(SystemExit):
            ptos.set_date_format(None)


class TestSavePreset:
    def test_save_as_preset(self, cfg):
        ptos.save_as_preset("lunch", {"type": "expense", "amount": "25"})
        presets = ptos.get_presets()
        assert "lunch" in presets
        assert presets["lunch"]["amount"] == "25"

    def test_save_with_note(self, cfg):
        ptos.save_as_preset("dinner", {"type": "expense"}, note="evening meal")
        presets = ptos.get_presets()
        assert presets["dinner"]["note"] == "evening meal"

    def test_delete_preset(self, cfg):
        ptos.delete_preset("coffee")
        presets = ptos.get_presets()
        assert "coffee" not in presets

    def test_delete_nonexistent_preset(self, cfg):
        with pytest.raises(ValueError, match="not found"):
            ptos.delete_preset("nonexistent")
