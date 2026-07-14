import os
import pytest
import ptos


@pytest.fixture
def doctor_env(tmp_path, monkeypatch):
    """Set up isolated environment for doctor checks."""
    config_dir = tmp_path / "config"
    records_dir = tmp_path / "records"
    todo_dir = tmp_path / "todo"
    config_dir.mkdir()
    records_dir.mkdir()
    todo_dir.mkdir()

    monkeypatch.setattr(ptos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(ptos, "SCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(ptos, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(ptos, "RECORDS_DIR", str(records_dir))
    monkeypatch.setattr(ptos, "TODO_DIR", str(todo_dir))
    monkeypatch.setattr(ptos, "TEMPLATE_DIR", str(tmp_path / "templates"))
    monkeypatch.setattr(ptos, "SCHEMA_PATH", str(config_dir / "schema.toml"))
    monkeypatch.setattr(ptos, "QUERIES_PATH", str(config_dir / "queries.toml"))
    monkeypatch.setattr(ptos, "CONFIG_PATH", str(config_dir / "config.toml"))
    monkeypatch.setattr(ptos, "PRESETS_PATH", str(config_dir / "presets.toml"))
    ptos._CACHE.clear()
    yield tmp_path
    ptos._CACHE.clear()


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestDoctorTomlValidity:
    def test_valid_toml_ok(self, doctor_env):
        _write(doctor_env / "config" / "schema.toml", '[fields]\namount = {type = "int"}\n')
        _write(doctor_env / "config" / "queries.toml", '[my_query]\nwhere = "type=expense"\n')
        _write(doctor_env / "config" / "presets.toml", '[presets.coffee]\ntype = "expense"\n')
        _write(doctor_env / "config" / "config.toml", '[user]\nname = "Test"\n')
        ptos._CACHE.clear()
        errors, warnings, messages, fixes = ptos.doctor_check()
        toml_msgs = [m for m in messages if m[0].startswith("TOML")]
        assert len(toml_msgs) == 4
        assert all("Valid syntax" in m[1] for m in toml_msgs)

    def test_malformed_toml_catches_error(self, doctor_env):
        _write(doctor_env / "config" / "schema.toml", '[fields\ninvalid = =\n')
        _write(doctor_env / "config" / "queries.toml", '')
        _write(doctor_env / "config" / "presets.toml", '')
        _write(doctor_env / "config" / "config.toml", '')
        ptos._CACHE.clear()
        errors, warnings, messages, fixes = ptos.doctor_check()
        assert any("invalid TOML" in e for e in errors)


class TestDoctorConfigShape:
    def test_no_int_fields_warns(self, doctor_env):
        _write(doctor_env / "config" / "schema.toml", '[fields]\nname = {type = "string"}\n')
        ptos._CACHE.clear()
        errors, warnings, messages, fixes = ptos.doctor_check()
        assert any("no fields declared type" in w for w in warnings)

    def test_int_fields_ok(self, doctor_env):
        _write(doctor_env / "config" / "schema.toml", '[fields]\namount = {type = "int"}\n')
        ptos._CACHE.clear()
        errors, warnings, messages, fixes = ptos.doctor_check()
        int_msgs = [m for m in messages if "numeric" in m[0].lower()]
        assert len(int_msgs) == 1
        assert "1 declared" in int_msgs[0][1]


class TestDoctorPtosHome:
    def test_temp_path_fails(self, doctor_env, tmp_path):
        import tempfile
        bootstrap = doctor_env / ".ptos_home"
        fake_home = os.path.join(tempfile.gettempdir(), "fake_ptos")
        bootstrap.write_text(fake_home, encoding="utf-8")
        ptos._CACHE.clear()
        errors, warnings, messages, fixes = ptos.doctor_check()
        assert any("temp path" in e for e in errors)

    def test_pytest_path_fails(self, doctor_env):
        bootstrap = doctor_env / ".ptos_home"
        bootstrap.write_text("/tmp/pytest-of-user/test123", encoding="utf-8")
        ptos._CACHE.clear()
        errors, warnings, messages, fixes = ptos.doctor_check()
        assert any("temp path" in e for e in errors)

    def test_missing_path_fails(self, doctor_env):
        bootstrap = doctor_env / ".ptos_home"
        bootstrap.write_text("/nonexistent/path/to/data", encoding="utf-8")
        ptos._CACHE.clear()
        errors, warnings, messages, fixes = ptos.doctor_check()
        assert any("nonexistent path" in e for e in errors)

    def test_valid_path_ok(self, doctor_env):
        bootstrap = doctor_env / ".ptos_home"
        bootstrap.write_text(str(doctor_env), encoding="utf-8")
        ptos._CACHE.clear()
        errors, warnings, messages, fixes = ptos.doctor_check()
        home_msgs = [m for m in messages if m[0] == ".ptos_home"]
        assert len(home_msgs) == 1


class TestDoctorDataSanity:
    def test_empty_log_warns(self, doctor_env):
        log_file = doctor_env / "records" / f"{ptos.dt.date.today().year}.log"
        log_file.write_text("", encoding="utf-8")
        ptos._CACHE.clear()
        errors, warnings, messages, fixes = ptos.doctor_check()
        assert any("0 bytes" in w for w in warnings)

    def test_nonempty_log_ok(self, doctor_env):
        log_file = doctor_env / "records" / f"{ptos.dt.date.today().year}.log"
        log_file.write_text("2026-07-14 type=test\n", encoding="utf-8")
        ptos._CACHE.clear()
        errors, warnings, messages, fixes = ptos.doctor_check()
        log_msgs = [m for m in messages if "bytes" in m[1]]
        assert len(log_msgs) >= 1

    def test_empty_config_dir_warns(self, doctor_env):
        empty_dir = doctor_env / "config" / "empty_stuff"
        empty_dir.mkdir()
        ptos._CACHE.clear()
        errors, warnings, messages, fixes = ptos.doctor_check()
        assert any("empty" in w for w in warnings)

    def test_empty_todo_dir_warns(self, doctor_env):
        todo_dir = doctor_env / "todo"
        for f in todo_dir.iterdir():
            f.unlink()
        ptos._CACHE.clear()
        errors, warnings, messages, fixes = ptos.doctor_check()
        assert any("todo/" in w and "empty" in w for w in warnings)


class TestDoctorIsolation:
    def test_one_bad_thing_only_that_reports(self, doctor_env):
        _write(doctor_env / "config" / "schema.toml", "NOT VALID TOML = = =")
        _write(doctor_env / "config" / "queries.toml", '[q]\nwhere = "x"\n')
        _write(doctor_env / "config" / "presets.toml", '[p]\ntype = "x"\n')
        _write(doctor_env / "config" / "config.toml", '[u]\nname = "x"\n')
        log_file = doctor_env / "records" / f"{ptos.dt.date.today().year}.log"
        log_file.write_text("2026-07-14 type=test\n", encoding="utf-8")
        ptos._CACHE.clear()
        errors, warnings, messages, fixes = ptos.doctor_check()
        toml_errors = [e for e in errors if "invalid TOML" in e]
        assert len(toml_errors) == 1
        toml_ok = [m for m in messages if m[0].startswith("TOML")]
        assert len(toml_ok) == 3
