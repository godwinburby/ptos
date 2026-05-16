import pytest
import ptos

FIXTURE_SCHEMA = {
    "fields": {
        "amount": {"type": "int", "dimension": False, "aggregatable": True},
        "duration": {"type": "int", "dimension": False, "aggregatable": True},
        "domain": {"type": "string", "dimension": True},
        "category": {"type": "string", "dimension": True},
        "tag": {"type": "string", "dimension": True, "multi": True},
        "timestamp": {"type": "datetime", "dimension": True},
        "description": {"type": "string", "dimension": True},
        "net": {"derived": "amount - discount"},
    },
    "type": {
        "expense": {
            "fields": {
                "net": {"derived": "amount - advance"}
            }
        }
    }
}


@pytest.fixture(autouse=True)
def clear_cache():
    ptos._CACHE.clear()
    yield
    ptos._CACHE.clear()


@pytest.fixture
def schema(monkeypatch):
    monkeypatch.setattr(ptos, "get_schema", lambda: FIXTURE_SCHEMA)


class TestNumericFields:
    def test_returns_int_fields(self, schema):
        result = ptos.numeric_fields()
        assert "amount" in result
        assert "duration" in result
        assert "domain" not in result
        assert sorted(result) == ["amount", "duration"]

    def test_empty_when_no_int_fields(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: {"fields": {"name": {"type": "string"}}})
        assert ptos.numeric_fields() == []

    def test_empty_schema(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: {"fields": {}})
        assert ptos.numeric_fields() == []

    def test_handles_missing_fields_key(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: {})
        assert ptos.numeric_fields() == []


class TestDatetimeFields:
    def test_returns_datetime_fields(self, schema):
        result = ptos.datetime_fields()
        assert result == ["timestamp"]

    def test_empty_when_none(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: {"fields": {"amount": {"type": "int"}}})
        assert ptos.datetime_fields() == []

    def test_handles_missing_fields_key(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: {})
        assert ptos.datetime_fields() == []


class TestNonDimensionFields:
    def test_returns_non_dimension_fields(self, schema):
        result = ptos.non_dimension_fields()
        assert "amount" in result
        assert "duration" in result
        assert "domain" not in result
        assert "timestamp" not in result

    def test_empty_when_all_dimension(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: {"fields": {"domain": {"type": "string", "dimension": True}}})
        assert ptos.non_dimension_fields() == set()

    def test_default_dimension_true(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: {"fields": {"unknown": {"type": "string"}}})
        assert ptos.non_dimension_fields() == set()

    def test_handles_missing_fields_key(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: {})
        assert ptos.non_dimension_fields() == set()


class TestDerivedFields:
    def test_global_derived(self, schema):
        result = ptos.derived_fields()
        assert "net" in result
        assert result["net"]["expr"] == "amount - discount"
        assert result["net"]["rtype"] is None

    def test_type_scoped_derived(self, schema):
        result = ptos.derived_fields()
        assert "expense.net" in result
        assert result["expense.net"]["expr"] == "amount - advance"
        assert result["expense.net"]["rtype"] == "expense"

    def test_no_derived(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: {"fields": {"amount": {"type": "int"}}})
        assert ptos.derived_fields() == {}

    def test_handles_empty_schema(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: {})
        assert ptos.derived_fields() == {}


class TestComputeDerived:
    def test_global_derived_expression(self, schema):
        result = ptos.compute_derived({"amount": "100", "discount": "20"})
        assert result.get("net") == 80

    def test_type_scoped_derived_matches_type(self, schema):
        result = ptos.compute_derived({"type": "expense", "amount": "100", "advance": "30"})
        assert result.get("net") == 70

    def test_type_scoped_skipped_for_wrong_type(self, schema):
        result = ptos.compute_derived({"type": "income", "amount": "100", "advance": "30"})
        assert result.get("net") is None

    def test_no_derived_fields(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_schema", lambda: {"fields": {}})
        assert ptos.compute_derived({"amount": "50"}) == {}

    def test_missing_field_returns_none(self, schema):
        result = ptos.compute_derived({"amount": "100"})
        assert result.get("net") is None

    def test_non_numeric_field_returns_none(self, schema):
        result = ptos.compute_derived({"amount": "abc", "discount": "10"})
        assert result.get("net") is None

    def test_float_result(self, schema):
        result = ptos.compute_derived({"amount": "10", "discount": "3"})
        assert result.get("net") == 7

    def test_unknown_record_type_gets_only_global(self, schema):
        result = ptos.compute_derived({"type": "unknown", "amount": "50", "discount": "10"})
        assert result.get("net") == 40
        assert "expense.net" not in result
