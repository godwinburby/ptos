import pytest
import ptos
import ptos_cli


def _run(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["ptos"] + list(argv))
    ptos_cli.main()


class TestCliGetConfig:
    def test_scalar(self, monkeypatch, capsys):
        _run(monkeypatch, "--get-config", "server.port")
        assert "5000" in capsys.readouterr().out

    def test_section_dumps_all(self, monkeypatch, capsys):
        _run(monkeypatch, "--get-config", "server")
        out = capsys.readouterr().out
        assert "port=5000" in out
        assert "host=127.0.0.1" in out

    def test_unset(self, monkeypatch, capsys):
        _run(monkeypatch, "--get-config", "nope.missing")
        assert "is not set" in capsys.readouterr().out

    def test_nested_leaf(self, monkeypatch, capsys):
        _run(monkeypatch, "--get-config", "todo.priority_labels.A")
        assert "Critical" in capsys.readouterr().out


class TestCliSetConfig:
    def test_sets_and_persists_scalar(self, monkeypatch, capsys):
        _run(monkeypatch, "--set-config", "server.port", "8080")
        out = capsys.readouterr().out
        assert "server.port=8080" in out
        assert ptos.get_config()["server"]["port"] == 8080

    def test_bool_coercion(self, monkeypatch, capsys):
        _run(monkeypatch, "--set-config", "sync.enabled", "false")
        assert ptos.get_config()["sync"]["enabled"] is False

    def test_int_and_str_preserved(self, monkeypatch, capsys):
        _run(monkeypatch, "--set-config", "home.quick_presets", "5")
        assert ptos.get_config()["home"]["quick_presets"] == 5
        _run(monkeypatch, "--set-config", "user.name", "Ada")
        assert ptos.get_config()["user"]["name"] == "Ada"

    def test_creates_missing_sections(self, monkeypatch, capsys):
        _run(monkeypatch, "--set-config", "custom.deep.value", "7")
        assert ptos.get_config()["custom"]["deep"]["value"] == 7

    def test_missing_config_exits(self, monkeypatch, tmp_path):
        import os
        monkeypatch.setattr(ptos, "CONFIG_PATH", str(tmp_path / "nope.toml"))
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, "--set-config", "a.b", "1")
        assert "config.toml not found" in str(exc.value.code)