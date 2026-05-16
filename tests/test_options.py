import ptos


class TestResolveOptions:
    def test_flat_list(self):
        schema = {}
        type_schema = {
            "fields": {
                "category": {
                    "options": ["food", "transport", "other"]
                }
            }
        }
        assert ptos.resolve_options(schema, type_schema, "category") == ["food", "transport", "other"]

    def test_shared_reference(self):
        schema = {
            "shared": {
                "source": {
                    "options": ["salary", "freelance", "other"]
                }
            }
        }
        type_schema = {
            "fields": {
                "source": {
                    "use": "shared.source"
                }
            }
        }
        assert ptos.resolve_options(schema, type_schema, "source") == ["salary", "freelance", "other"]

    def test_parent_dependent_returns_none(self):
        type_schema = {
            "fields": {
                "category": {
                    "parent": "domain",
                    "options": {
                        "self": ["food", "transport"],
                        "work": ["supplies", "travel"],
                    }
                }
            }
        }
        assert ptos.resolve_options({}, type_schema, "category") is None

    def test_no_options_returns_none(self):
        type_schema = {"fields": {"note": {}}}
        assert ptos.resolve_options({}, type_schema, "note") is None

    def test_shared_missing_key(self):
        schema = {"shared": {}}
        type_schema = {
            "fields": {
                "source": {"use": "shared.source"}
            }
        }
        assert ptos.resolve_options(schema, type_schema, "source") is None

    def test_shared_not_in_schema(self):
        type_schema = {
            "fields": {
                "source": {"use": "shared.source"}
            }
        }
        assert ptos.resolve_options({}, type_schema, "source") is None


class TestResolveOptionsForValue:
    def test_matching_parent_value(self):
        type_schema = {
            "fields": {
                "category": {
                    "options": {
                        "self": ["food", "transport"],
                        "work": ["supplies", "travel"],
                    }
                }
            }
        }
        assert ptos.resolve_options_for_value(type_schema, "category", "self") == ["food", "transport"]

    def test_non_matching_parent_value(self):
        type_schema = {
            "fields": {
                "category": {
                    "options": {
                        "self": ["food", "transport"],
                    }
                }
            }
        }
        assert ptos.resolve_options_for_value(type_schema, "category", "work") == []

    def test_field_has_no_options(self):
        type_schema = {"fields": {"note": {}}}
        assert ptos.resolve_options_for_value(type_schema, "note", "anything") == []

    def test_non_dict_options(self):
        type_schema = {
            "fields": {
                "category": {"options": ["flat"]}
            }
        }
        assert ptos.resolve_options_for_value(type_schema, "category", "x") == []

    def test_field_not_in_type_schema(self):
        assert ptos.resolve_options_for_value({}, "missing_field", "val") == []
