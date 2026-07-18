import os
import zipfile
import ptos


class TestBackupData:
    def _setup(self, tmp_path):
        base = tmp_path / "ptos"
        config_dir = base / "config"
        records_dir = base / "records"
        backup_dir = base / "backups"
        config_dir.mkdir(parents=True)
        records_dir.mkdir(parents=True)
        backup_dir.mkdir(parents=True)
        (config_dir / "schema.toml").write_text(
            '[types]\nallowed = ["expense"]\n', encoding="utf-8"
        )
        (config_dir / "queries.toml").write_text(
            '[test]\nwhere = "type=expense"\n', encoding="utf-8"
        )
        (records_dir / "2026.log").write_text(
            "2026-01-15 type=expense domain=work amount=50\n", encoding="utf-8"
        )
        return base, config_dir, records_dir, backup_dir

    def test_creates_full_backup_zip(self, tmp_path, monkeypatch):
        base, config_dir, records_dir, backup_dir = self._setup(tmp_path)
        monkeypatch.setattr(ptos, "BASE_DIR", str(base))
        monkeypatch.setattr(ptos, "CONFIG_DIR", str(config_dir))
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(records_dir))
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(backup_dir))
        monkeypatch.setattr(ptos, "get_backup_folders", lambda: ["config", "records"])
        monkeypatch.setattr(ptos, "_cleanup_old_backups", lambda: None)

        result = ptos.backup_data()
        assert result.startswith(str(backup_dir))
        assert result.endswith(".zip")
        assert os.path.exists(result)

        with zipfile.ZipFile(result, "r") as zf:
            names = zf.namelist()
        assert "config/schema.toml" in names
        assert "config/queries.toml" in names
        assert "records/2026.log" in names

    def test_backup_skips_bak_and_tmp(self, tmp_path, monkeypatch):
        base, config_dir, records_dir, backup_dir = self._setup(tmp_path)
        (records_dir / "2026.bak").write_text("backup")
        (records_dir / ".temp.tmp").write_text("temp")
        monkeypatch.setattr(ptos, "BASE_DIR", str(base))
        monkeypatch.setattr(ptos, "CONFIG_DIR", str(config_dir))
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(records_dir))
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(backup_dir))
        monkeypatch.setattr(ptos, "get_backup_folders", lambda: ["config", "records"])
        monkeypatch.setattr(ptos, "_cleanup_old_backups", lambda: None)

        result = ptos.backup_data()
        with zipfile.ZipFile(result, "r") as zf:
            names = zf.namelist()
        assert "records/2026.bak" not in names
        assert "records/.temp.tmp" not in names

    def test_raises_when_config_missing(self, tmp_path, monkeypatch):
        base = tmp_path / "ptos"
        backup_dir = base / "backups"
        backup_dir.mkdir(parents=True)
        monkeypatch.setattr(ptos, "CONFIG_DIR", str(base / "config"))
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(base / "records"))
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(backup_dir))
        monkeypatch.setattr(ptos, "get_backup_folders", lambda: ["config"])

        import pytest
        with pytest.raises(Exception, match="config/ folder missing"):
            ptos.backup_data()


class TestBackupConfig:
    def test_creates_config_backup_zip(self, tmp_path, monkeypatch):
        base = tmp_path / "ptos"
        config_dir = base / "config"
        backup_dir = base / "backups"
        config_dir.mkdir(parents=True)
        backup_dir.mkdir(parents=True)
        (config_dir / "schema.toml").write_text("data", encoding="utf-8")
        (config_dir / "queries.toml").write_text("data", encoding="utf-8")
        # Non-toml files should be excluded
        (config_dir / "notes.txt").write_text("ignored", encoding="utf-8")
        monkeypatch.setattr(ptos, "BASE_DIR", str(base))
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(backup_dir))
        monkeypatch.setattr(ptos, "_cleanup_old_backups", lambda: None)

        result = ptos.backup_config()
        assert result.startswith(str(backup_dir))
        assert result.endswith(".zip")
        assert os.path.exists(result)

        with zipfile.ZipFile(result, "r") as zf:
            names = zf.namelist()
        assert "config/schema.toml" in names
        assert "config/queries.toml" in names
        assert "config/notes.txt" not in names


class TestBackupIfNeeded:
    def test_creates_when_needed(self, monkeypatch):
        monkeypatch.setattr(ptos, "should_backup", lambda: True)
        monkeypatch.setattr(ptos, "backup_data", lambda force=False: "/fake/backup.zip")
        created, path = ptos.backup_if_needed()
        assert created is True
        assert path == "/fake/backup.zip"

    def test_skips_when_no_changes(self, monkeypatch):
        monkeypatch.setattr(ptos, "should_backup", lambda: False)
        created, path = ptos.backup_if_needed()
        assert created is False
        assert path is None

    def test_handles_exception_gracefully(self, monkeypatch):
        monkeypatch.setattr(ptos, "should_backup", lambda: True)
        monkeypatch.setattr(ptos, "backup_data", lambda force=False: (_ for _ in ()).throw(Exception("boom")))
        created, path = ptos.backup_if_needed()
        assert created is False
        assert path is None


class TestMigrateBackupDir:
    def test_moves_old_backups_to_sibling(self, tmp_path, monkeypatch):
        old_base = tmp_path / "ptos-data"
        old_backups = old_base / "backups"
        old_backups.mkdir(parents=True)
        (old_backups / "backup.zip").write_text("data")
        new_backup_dir = tmp_path / "ptos-backups"
        monkeypatch.setattr(ptos, "BASE_DIR", str(old_base))
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(new_backup_dir))
        ptos.migrate_backup_dir()
        assert (new_backup_dir / "backup.zip").exists()
        assert not old_backups.exists()

    def test_noop_when_no_old_backups(self, tmp_path, monkeypatch):
        old_base = tmp_path / "ptos-data"
        old_base.mkdir(parents=True)
        new_backup_dir = tmp_path / "ptos-backups"
        monkeypatch.setattr(ptos, "BASE_DIR", str(old_base))
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(new_backup_dir))
        ptos.migrate_backup_dir()
        assert not new_backup_dir.exists()

    def test_noop_when_sibling_already_exists(self, tmp_path, monkeypatch):
        old_base = tmp_path / "ptos-data"
        old_backups = old_base / "backups"
        old_backups.mkdir(parents=True)
        (old_backups / "old.zip").write_text("old")
        new_backup_dir = tmp_path / "ptos-backups"
        new_backup_dir.mkdir(parents=True)
        (new_backup_dir / "existing.zip").write_text("existing")
        monkeypatch.setattr(ptos, "BASE_DIR", str(old_base))
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(new_backup_dir))
        ptos.migrate_backup_dir()
        assert (new_backup_dir / "existing.zip").exists()
        assert (old_backups / "old.zip").exists()

    def test_respects_env_override(self, tmp_path, monkeypatch):
        old_base = tmp_path / "ptos-data"
        old_backups = old_base / "backups"
        old_backups.mkdir(parents=True)
        custom_dir = tmp_path / "my-backups"
        monkeypatch.setattr(ptos, "BASE_DIR", str(old_base))
        monkeypatch.setattr(ptos, "BACKUP_DIR", str(custom_dir))
        ptos.migrate_backup_dir()
        assert (custom_dir / "backups").exists() or custom_dir.exists()
