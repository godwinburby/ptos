import copy
import pytest
import ptos


BASE_SCHEMA = {
    "types": {"allowed": ["expense", "income"]},
    "type": {
        "expense": {
            "required": ["amount", "category"],
            "fields": {
                "category": {
                    "options": ["food", "transport"]
                },
                "vendor": {
                    "parent": "category",
                    "options": {
                        "food": ["restaurant", "grocery"],
                        "transport": ["gas", "bus"]
                    }
                }
            }
        }
    },
    "shared": {
        "payment_method": {
            "options": ["cash", "card"]
        }
    },
    "global_fields": {
        "project": {
            "options": ["proj_a", "proj_b"]
        }
    }
}


def _schema():
    return copy.deepcopy(BASE_SCHEMA)


class TestAddFieldOption:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        self.saved = []
        monkeypatch.setattr(ptos, "get_schema", _schema)
        monkeypatch.setattr(ptos, "_save_schema", lambda s: self.saved.append(s))

    def test_flat_adds_option(self):
        result = ptos.add_field_option("expense", "category", "utilities", "flat")
        assert result["success"] == True
        assert "utilities" in self.saved[0]["type"]["expense"]["fields"]["category"]["options"]

    def test_flat_duplicate_is_noop(self):
        result = ptos.add_field_option("expense", "category", "food", "flat")
        assert result["success"] == True

    def test_flat_missing_type(self):
        result = ptos.add_field_option("nonexistent", "category", "x", "flat")
        assert result["success"] == False
        assert "not found" in result["error"]

    def test_flat_missing_field(self):
        result = ptos.add_field_option("expense", "nope", "x", "flat")
        assert result["success"] == False
        assert "not found" in result["error"]

    def test_flat_not_a_list(self, monkeypatch):
        bad = _schema()
        bad["type"]["expense"]["fields"]["category"]["options"] = {}
        monkeypatch.setattr(ptos, "get_schema", lambda: bad)
        result = ptos.add_field_option("expense", "category", "x", "flat")
        assert result["success"] == False
        assert "Not a flat options" in result["error"]

    def test_parent_dependent_adds_option(self):
        result = ptos.add_field_option(
            "expense", "vendor", "deli", "parent_dependent",
            parent_value="food"
        )
        assert result["success"] == True
        opts = self.saved[0]["type"]["expense"]["fields"]["vendor"]["options"]["food"]
        assert "deli" in opts

    def test_parent_dependent_duplicate(self):
        result = ptos.add_field_option(
            "expense", "vendor", "restaurant", "parent_dependent",
            parent_value="food"
        )
        assert result["success"] == True

    def test_parent_dependent_missing_parent_value(self):
        result = ptos.add_field_option(
            "expense", "vendor", "x", "parent_dependent",
            parent_value="nonexistent"
        )
        assert result["success"] == False
        assert "not found" in result["error"]

    def test_shared_adds_option(self):
        result = ptos.add_field_option("", "", "credit", "shared", shared_key="payment_method")
        assert result["success"] == True
        assert "credit" in self.saved[0]["shared"]["payment_method"]["options"]

    def test_shared_duplicate(self):
        result = ptos.add_field_option("", "", "cash", "shared", shared_key="payment_method")
        assert result["success"] == True

    def test_shared_missing_key(self):
        result = ptos.add_field_option("", "", "x", "shared")
        assert result["success"] == False
        assert "No shared_key" in result["error"]

    def test_shared_key_not_found(self):
        result = ptos.add_field_option("", "", "x", "shared", shared_key="nope")
        assert result["success"] == False
        assert "not found" in result["error"]

    def test_unknown_source(self):
        result = ptos.add_field_option("", "", "x", "invalid")
        assert result["success"] == False
        assert "Unknown option_source" in result["error"]

    def test_empty_option(self):
        result = ptos.add_field_option("expense", "category", "", "flat")
        assert result["success"] == False
        assert "Empty option" in result["error"]


class TestAddGlobalFieldOption:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        self.saved = []
        monkeypatch.setattr(ptos, "get_schema", _schema)
        monkeypatch.setattr(ptos, "_save_schema", lambda s: self.saved.append(s))

    def test_adds_option(self):
        result = ptos.add_global_field_option("project", "proj_c")
        assert result["success"] == True
        assert "proj_c" in self.saved[0]["global_fields"]["project"]["options"]

    def test_duplicate_is_noop(self):
        result = ptos.add_global_field_option("project", "proj_a")
        assert result["success"] == True

    def test_missing_field(self):
        result = ptos.add_global_field_option("nope", "x")
        assert result["success"] == False
        assert "not found" in result["error"]

    def test_not_a_dict_field(self, monkeypatch):
        bad_schema = {"global_fields": {"project": ["not", "a", "dict"]}}
        monkeypatch.setattr(ptos, "get_schema", lambda: bad_schema)
        result = ptos.add_global_field_option("project", "x")
        assert result["success"] == False
        assert "Invalid field definition" in result["error"]

    def test_empty_option(self):
        result = ptos.add_global_field_option("project", "")
        assert result["success"] == False
        assert "Empty option" in result["error"]

    def test_save_error_reported(self, monkeypatch):
        def broken_save(_):
            raise RuntimeError("disk full")
        monkeypatch.setattr(ptos, "_save_schema", broken_save)
        result = ptos.add_global_field_option("project", "x")
        assert result["success"] == False
        assert "disk full" in result["error"]


class TestAddTagsToSchema:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        self.saved = []
        monkeypatch.setattr(ptos, "get_schema", _schema)
        monkeypatch.setattr(ptos, "_save_schema", lambda s: self.saved.append(s))

    def test_adds_tag_to_existing_field(self, monkeypatch):
        answers = iter(["y"])
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        ptos.add_tags_to_schema("", "expense", {"type": "expense", "category": "food"}, ["dining"])
        tags = self.saved[0]["type"]["expense"]["tags"]["category"]["food"]
        assert "dining" in tags

    def test_skips_when_input_no(self, monkeypatch):
        answers = iter(["n"])
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        ptos.add_tags_to_schema("", "expense", {"type": "expense", "category": "food"}, ["dining"])
        assert len(self.saved) == 0

    def test_uses_first_required_field_with_value(self, monkeypatch):
        answers = iter(["y"])
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        ptos.add_tags_to_schema("", "expense", {"type": "expense", "category": "transport", "amount": "50"}, ["commute"])
        tags = self.saved[0]["type"]["expense"]["tags"]["amount"]["50"]
        assert "commute" in tags

    def test_creates_missing_sections(self, monkeypatch):
        answers = iter(["y"])
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        minimal_schema = {
            "types": {"allowed": ["expense"]},
            "type": {"expense": {"required": ["amount"], "fields": {}}}
        }
        monkeypatch.setattr(ptos, "get_schema", lambda: minimal_schema)
        ptos.add_tags_to_schema("", "expense", {"type": "expense", "amount": "50"}, ["urgent"])
        saved = self.saved[0]
        assert saved["type"]["expense"]["tags"]["amount"]["50"] == ["urgent"]

    def test_no_context_skips(self, capsys):
        ptos.add_tags_to_schema("", "expense", {"type": "expense"}, ["x"])
        out = capsys.readouterr().out
        assert "Could not determine tag context" in out
        assert len(self.saved) == 0

    def test_save_failure_reported(self, monkeypatch, capsys):
        def broken_save(_):
            raise RuntimeError("permission denied")
        monkeypatch.setattr(ptos, "_save_schema", broken_save)
        answers = iter(["y"])
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        ptos.add_tags_to_schema("", "expense", {"type": "expense", "category": "food"}, ["dining"])
        out = capsys.readouterr().out
        assert "permission denied" in out
