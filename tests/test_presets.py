import ptos
from ptos_service import get_frequent_presets, increment_preset_use


class TestGetFrequentPresets:
    def test_top_n_by_use_count(self, monkeypatch):
        presets = {
            "coffee": {"type": "expense", "use_count": 10},
            "lunch": {"type": "expense", "use_count": 5},
            "snacks": {"type": "expense", "use_count": 3},
            "commute": {"type": "expense", "use_count": 1},
            "tea": {"type": "expense", "use_count": 0},
        }
        monkeypatch.setattr(ptos, "get_presets", lambda: presets)
        freq, rem = get_frequent_presets(3)
        assert freq == ["coffee", "lunch", "snacks"]
        assert rem == ["commute", "tea"]

    def test_remaining_alphabetical(self, monkeypatch):
        presets = {
            "zebra": {"type": "expense", "use_count": 0},
            "alpha": {"type": "expense", "use_count": 0},
            "beta": {"type": "expense", "use_count": 0},
        }
        monkeypatch.setattr(ptos, "get_presets", lambda: presets)
        freq, rem = get_frequent_presets(2)
        assert freq == ["alpha", "beta"]
        assert rem == ["zebra"]

    def test_remaining_alphabetical_mixed_usage(self, monkeypatch):
        presets = {
            "coffee": {"type": "expense", "use_count": 10},
            "aaa": {"type": "expense", "use_count": 1},
            "zzz": {"type": "expense", "use_count": 0},
            "mmm": {"type": "expense", "use_count": 0},
        }
        monkeypatch.setattr(ptos, "get_presets", lambda: presets)
        freq, rem = get_frequent_presets(2)
        assert freq == ["coffee", "aaa"]
        assert rem == ["mmm", "zzz"]

    def test_excludes_multi_record_presets(self, monkeypatch):
        presets = {
            "single": {"type": "expense", "use_count": 5},
            "morning": {"records": [{"type": "exercise"}, {"type": "learning"}]},
        }
        monkeypatch.setattr(ptos, "get_presets", lambda: presets)
        freq, rem = get_frequent_presets(3)
        assert "morning" not in freq and "morning" not in rem
        assert "single" in freq

    def test_excludes_alias_presets(self, monkeypatch):
        presets = {
            "real": {"type": "expense", "use_count": 3},
            "c": {"alias": "real"},
        }
        monkeypatch.setattr(ptos, "get_presets", lambda: presets)
        freq, rem = get_frequent_presets(3)
        assert "c" not in freq and "c" not in rem
        assert "real" in freq

    def test_empty_presets(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_presets", lambda: {})
        freq, rem = get_frequent_presets(6)
        assert freq == []
        assert rem == []

    def test_no_use_count_treated_as_zero(self, monkeypatch):
        presets = {
            "alpha": {"type": "expense"},
            "beta": {"type": "expense", "use_count": 5},
        }
        monkeypatch.setattr(ptos, "get_presets", lambda: presets)
        freq, rem = get_frequent_presets(1)
        assert freq == ["beta"]
        assert rem == ["alpha"]


class TestIncrementPresetUse:
    def test_increments_existing_count(self, tmp_path, monkeypatch):
        presets_path = tmp_path / "presets.toml"
        presets_path.write_text(
            '[presets]\n[presets.coffee]\ntype = "expense"\nuse_count = 5\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(ptos, "PRESETS_PATH", str(presets_path))
        monkeypatch.setattr(ptos, "BASE_DIR", str(tmp_path))
        increment_preset_use("coffee")
        import tomllib
        data = tomllib.loads(presets_path.read_text(encoding="utf-8"))
        assert data["presets"]["coffee"]["use_count"] == 6

    def test_creates_count_when_missing(self, tmp_path, monkeypatch):
        presets_path = tmp_path / "presets.toml"
        presets_path.write_text(
            '[presets]\n[presets.coffee]\ntype = "expense"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(ptos, "PRESETS_PATH", str(presets_path))
        monkeypatch.setattr(ptos, "BASE_DIR", str(tmp_path))
        increment_preset_use("coffee")
        import tomllib
        data = tomllib.loads(presets_path.read_text(encoding="utf-8"))
        assert data["presets"]["coffee"]["use_count"] == 1

    def test_nonexistent_preset_is_noop(self, tmp_path, monkeypatch):
        presets_path = tmp_path / "presets.toml"
        presets_path.write_text(
            '[presets]\n[presets.coffee]\ntype = "expense"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(ptos, "PRESETS_PATH", str(presets_path))
        monkeypatch.setattr(ptos, "BASE_DIR", str(tmp_path))
        increment_preset_use("nonexistent")
        import tomllib
        data = tomllib.loads(presets_path.read_text(encoding="utf-8"))
        assert "nonexistent" not in data["presets"]

    def test_missing_file_is_noop(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "PRESETS_PATH", str(tmp_path / "nope.toml"))
        monkeypatch.setattr(ptos, "BASE_DIR", str(tmp_path))
        increment_preset_use("coffee")
        assert not (tmp_path / "nope.toml").exists()
