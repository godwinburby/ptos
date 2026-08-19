import os
from pathlib import Path
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


class TestInstantPresets:
    """Single presets flagged `instant = true` save via /api/preset_add
    instead of opening the add form."""

    def _write_presets(self, tmp_path, monkeypatch):
        presets_path = Path(ptos.PRESETS_PATH)
        presets_path.parent.mkdir(parents=True, exist_ok=True)
        presets_path.write_text(
            '[presets.exercise]\n'
            'type = "habit"\n'
            'name = "exercise"\n'
            'instant = true\n'
            'note = "daily workout"\n'
            '\n'
            '[presets.snacks]\n'
            'type = "expense"\n'
            'domain = "home"\n'
            'category = "food"\n'
            'amount = 50\n'
            '\n'
            '[presets.commute]\n'
            'records = ["auto", "bus"]\n'
            '\n'
            '[presets.auto]\n'
            'type = "expense"\n'
            'domain = "self"\n'
            'category = "transport"\n'
            'amount = 60\n'
            'note = "uber to station"\n'
            '\n'
            '[presets.bus]\n'
            'type = "expense"\n'
            'domain = "self"\n'
            'category = "transport"\n'
            'amount = 30\n',
            encoding="utf-8",
        )
        ptos._invalidate("presets")

    def _records(self, tmp_path):
        records_dir = ptos.RECORDS_DIR
        os.makedirs(records_dir, exist_ok=True)
        files = list(Path(records_dir).glob("*.log"))
        if not files:
            return []
        return files[0].read_text(encoding="utf-8").strip().splitlines()

    def test_instant_preset_appends_record(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/preset_add", json={"name": "exercise"})
        data = resp.get_json()
        assert data["ok"] is True
        assert data["count"] == 1
        lines = self._records(tmp_path)
        assert len(lines) == 1
        assert "type=habit" in lines[0]
        assert "name=exercise" in lines[0]

    def test_instant_preset_applies_stored_note(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/preset_add", json={"name": "exercise"})
        data = resp.get_json()
        assert data["ok"] is True, data.get("error")
        lines = self._records(tmp_path)
        assert "| daily workout" in lines[0]

    def test_multi_preset_applies_per_record_notes(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/preset_add", json={"name": "commute"})
        data = resp.get_json()
        assert data["ok"] is True, data.get("error")
        lines = self._records(tmp_path)
        assert "| uber to station" in lines[0]
        assert "|" not in lines[1]

    def test_non_instant_preset_rejected(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/preset_add", json={"name": "snacks"})
        data = resp.get_json()
        assert data["ok"] is False
        assert "not a multi-record or instant preset" in data["error"]

    def test_unknown_preset_rejected(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/preset_add", json={"name": "nope"})
        data = resp.get_json()
        assert data["ok"] is False

    def test_multi_preset_still_works(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/preset_add", json={"name": "commute"})
        data = resp.get_json()
        assert data["ok"] is True
        assert data["count"] == 2

    def test_instant_preset_excluded_from_multi_card(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        from ptos_web import _multi_presets
        multi = _multi_presets()
        assert "exercise" not in multi
        assert "commute" in multi

    def test_add_page_renders_instant_chip(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/add")
        html = resp.get_data(as_text=True)
        assert 'data-name="exercise"' in html
        assert 'class="preset-chip preset-instant"' in html

    def test_add_page_renders_edit_pencil_and_warning(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        html = client.get("/add").get_data(as_text=True)
        assert 'class="preset-edit" title="Edit preset"' in html
        assert 'href="/add?preset=exercise"' in html
        home_html = client.get("/").get_data(as_text=True)
        assert 'class="preset-edit" title="Edit preset"' in home_html
        edit_html = client.get("/add?preset=exercise").get_data(as_text=True)
        assert "_existingPresets" in edit_html
        assert '_loadedPresetName = "exercise"' in edit_html
        assert 'preset-name-input").value = "exercise"' in edit_html

    def test_preset_instant_toggle_on(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/preset_instant", json={"name": "snacks", "instant": True})
        assert resp.get_json()["ok"] is True
        import tomllib
        data = tomllib.loads(Path(ptos.PRESETS_PATH).read_text(encoding="utf-8"))
        assert data["presets"]["snacks"].get("instant") is True

    def test_preset_instant_toggle_off(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/preset_instant", json={"name": "exercise", "instant": False})
        assert resp.get_json()["ok"] is True
        import tomllib
        data = tomllib.loads(Path(ptos.PRESETS_PATH).read_text(encoding="utf-8"))
        assert "instant" not in data["presets"]["exercise"]

    def test_preset_instant_toggle_unknown(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/preset_instant", json={"name": "nope", "instant": True})
        assert resp.get_json()["ok"] is False

    def test_save_preset_with_instant(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/save_preset", json={
            "name": "walk",
            "record": {"type": "habit", "name": "walk"},
            "note": "",
            "instant": True,
        })
        assert resp.get_json()["ok"] is True
        import tomllib
        data = tomllib.loads(Path(ptos.PRESETS_PATH).read_text(encoding="utf-8"))
        assert data["presets"]["walk"]["instant"] is True

    def test_save_preset_default_not_instant(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/save_preset", json={
            "name": "walk",
            "record": {"type": "habit", "name": "walk"},
            "note": "",
        })
        assert resp.get_json()["ok"] is True
        import tomllib
        data = tomllib.loads(Path(ptos.PRESETS_PATH).read_text(encoding="utf-8"))
        assert "instant" not in data["presets"]["walk"]

    def test_set_preset_instant_direct(self, tmp_path, monkeypatch):
        self._write_presets(tmp_path, monkeypatch)
        import ptos_service
        ptos_service.set_preset_instant("snacks", True)
        ptos._invalidate("presets")
        import tomllib
        data = tomllib.loads(Path(ptos.PRESETS_PATH).read_text(encoding="utf-8"))
        assert data["presets"]["snacks"].get("instant") is True
