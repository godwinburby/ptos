import pytest
import ptos

FIXTURE_SCHEMA = {
    "fields": {
        "amount": {"type": "int", "dimension": False, "aggregatable": True},
        "domain": {"type": "string", "dimension": True},
        "category": {"type": "string", "dimension": True},
    },
    "type": {
        "expense": {
            "required": ["domain", "category", "amount"],
        }
    }
}


@pytest.fixture(autouse=True)
def clear_cache():
    ptos._CACHE.clear()
    yield
    ptos._CACHE.clear()


class TestShowFields:
    def test_shows_field_names(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: FIXTURE_SCHEMA)
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        results = [
            "2026-01-15 type=expense domain=work category=food amount=50",
            "2026-01-16 type=expense domain=home category=grocery amount=30",
        ]
        ptos.show_fields(results)
        out = capsys.readouterr().out
        assert "[expense]" in out
        assert "domain" in out
        assert "category" in out
        assert "amount" in out

    def test_shows_sample_values(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: FIXTURE_SCHEMA)
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        results = ["2026-01-15 type=expense domain=work amount=50"]
        ptos.show_fields(results)
        out = capsys.readouterr().out
        assert "work" in out
        assert "50" in out

    def test_recommends_dimensions(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: FIXTURE_SCHEMA)
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        results = [
            f"2026-01-{i:02d} type=expense domain={'work' if i < 5 else 'home'} amount=50"
            for i in range(1, 11)
        ]
        ptos.show_fields(results)
        out = capsys.readouterr().out
        assert "★" in out
        assert "recommended dimension" in out

    def test_suggests_group_commands(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: FIXTURE_SCHEMA)
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        results = [
            f"2026-01-{i:02d} type=expense domain={'work' if i < 5 else 'home'} amount=50"
            for i in range(1, 11)
        ]
        ptos.show_fields(results)
        out = capsys.readouterr().out
        assert "Suggested group" in out
        assert "ptos -y expense -G" in out

    def test_suggests_pivot_commands(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: FIXTURE_SCHEMA)
        monkeypatch.setattr(ptos, "get_config", lambda: {
            "discovery": {"pivot_pairs": [["domain", "category"]]}
        })
        results = [
            f"2026-01-{i:02d} type=expense domain={'work' if i < 5 else 'home'} category=food amount=50"
            for i in range(1, 11)
        ]
        ptos.show_fields(results)
        out = capsys.readouterr().out
        assert "Suggested pivot" in out
        assert "ptos -y expense -v" in out

    def test_empty_results(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: FIXTURE_SCHEMA)
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        ptos.show_fields([])
        out = capsys.readouterr().out
        assert "Fields by record type" in out

    def test_unknown_type(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: FIXTURE_SCHEMA)
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        results = ["2026-01-15 type=unknown domain=work amount=50"]
        ptos.show_fields(results)
        out = capsys.readouterr().out
        assert "[unknown]" in out
