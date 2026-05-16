import os
import datetime as dt
import pytest
import ptos


@pytest.fixture(autouse=True)
def clear_cache():
    ptos._CACHE.clear()
    yield
    ptos._CACHE.clear()


class TestSaveQuery:
    def test_saves_new_query(self, tmp_path, monkeypatch, capsys):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        queries_path = config_dir / "queries.toml"
        queries_path.write_text("", encoding="utf-8")
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(queries_path))
        monkeypatch.setattr(ptos, "CONFIG_DIR", str(config_dir))

        class FakeArgs:
            where = [["type=expense"]]
            type = None
            tag = None
            time = "this-month"
            date_from = None
            date_to = None
            search = None
            group = None
            pivot = None
            count = None
            sort = None
            trend = None
            sum = None

        monkeypatch.setattr("builtins.input", lambda _: "y")
        ptos.save_query("my_query", FakeArgs(), [])
        out = capsys.readouterr().out
        assert "saved" in out
        content = queries_path.read_text()
        assert "my_query" in content
        assert "type=expense" in content

    def test_overwrite_confirmed(self, tmp_path, monkeypatch, capsys):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        queries_path = config_dir / "queries.toml"
        queries_path.write_text('[existing]\nwhere = "type=expense"\n', encoding="utf-8")
        monkeypatch.setattr(ptos, "QUERIES_PATH", str(queries_path))
        monkeypatch.setattr(ptos, "CONFIG_DIR", str(config_dir))

        class FakeArgs:
            where = [["type=expense"]]
            type = None
            tag = None
            time = "this-month"
            date_from = None
            date_to = None
            search = None
            group = None
            pivot = None
            count = None
            sort = None
            trend = None
            sum = None

        monkeypatch.setattr("builtins.input", lambda _: "y")
        ptos.save_query("existing", FakeArgs(), [])


class TestCheckBackupFolders:
    def test_all_exist(self, tmp_path, monkeypatch):
        (tmp_path / "records").mkdir()
        (tmp_path / "config").mkdir()
        monkeypatch.setattr(ptos, "BASE_DIR", str(tmp_path))
        monkeypatch.setattr(ptos, "get_backup_folders", lambda: ["records", "config"])
        ok, missing = ptos.check_backup_folders()
        assert ok is True
        assert missing == []

    def test_some_missing(self, tmp_path, monkeypatch):
        (tmp_path / "records").mkdir()
        monkeypatch.setattr(ptos, "BASE_DIR", str(tmp_path))
        monkeypatch.setattr(ptos, "get_backup_folders", lambda: ["records", "nonexistent"])
        ok, missing = ptos.check_backup_folders()
        assert ok is False
        assert "nonexistent" in missing
        assert "records" not in missing

    def test_backup_folders_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "get_backup_folders", lambda: [])
        ok, missing = ptos.check_backup_folders()
        assert ok is True
        assert missing == []


class TestListBackups:
    def test_no_backups(self, tmp_path, monkeypatch):
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(backups_dir))
        assert ptos.list_backups() == []

    def test_lists_full_backups(self, tmp_path, monkeypatch):
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()
        (backups_dir / "ptos-backup-full-20260516_120000.zip").write_text("")
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(backups_dir))
        result = ptos.list_backups()
        assert len(result) == 1
        name, mtime, btype = result[0]
        assert "full" in name
        assert btype == "full"

    def test_lists_config_backups(self, tmp_path, monkeypatch):
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()
        (backups_dir / "ptos-backup-config-20260516_120000.zip").write_text("")
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(backups_dir))
        result = ptos.list_backups()
        assert len(result) == 1
        assert result[0][2] == "config"

    def test_ignores_other_files(self, tmp_path, monkeypatch):
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()
        (backups_dir / "ptos-backup-full-20260516_120000.zip").write_text("")
        (backups_dir / "random.txt").write_text("ignored")
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(backups_dir))
        result = ptos.list_backups()
        assert len(result) == 1

    def test_sorted_newest_first(self, tmp_path, monkeypatch):
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()
        old = backups_dir / "ptos-backup-full-20250101_000000.zip"
        old.write_text("")
        os.utime(str(old), (1000000000, 1000000000))
        new = backups_dir / "ptos-backup-full-20260516_120000.zip"
        new.write_text("")
        os.utime(str(new), (2000000000, 2000000000))
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(backups_dir))
        result = ptos.list_backups()
        assert result[0][0] == new.name
        assert result[1][0] == old.name


class TestDeleteBackup:
    def test_deletes_valid_backup(self, tmp_path, monkeypatch):
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()
        f = backups_dir / "ptos-backup-full-20260516_120000.zip"
        f.write_text("data")
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(backups_dir))
        assert ptos.delete_backup(f.name) == True
        assert not f.exists()

    def test_raises_on_missing(self, tmp_path, monkeypatch):
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(backups_dir))
        with pytest.raises(FileNotFoundError):
            ptos.delete_backup("ptos-backup-full-20260516_120000.zip")

    def test_raises_on_invalid_name(self, tmp_path, monkeypatch):
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()
        f = backups_dir / "random.txt"
        f.write_text("data")
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(backups_dir))
        with pytest.raises(ValueError, match="Invalid backup filename"):
            ptos.delete_backup("random.txt")


class TestShouldBackup:
    def test_no_backup_dir_returns_true(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(tmp_path / "nope"))
        monkeypatch.setattr(ptos, "BASE_DIR", str(tmp_path))
        monkeypatch.setattr(ptos, "get_backup_config", lambda: {"backup_if_files_changed": True})
        monkeypatch.setattr(ptos, "get_backup_folders", lambda: [])
        assert ptos.should_backup() == True
