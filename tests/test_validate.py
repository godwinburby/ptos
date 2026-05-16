import pytest
from ptos import validate_record, resolve_tags


class TestValidateRecord:
    def test_valid_record(self, sample_schema, valid_record):
        problems = validate_record(sample_schema, valid_record)
        assert problems == []

    def test_invalid_type(self, sample_schema):
        problems = validate_record(sample_schema, {"type": "invalid_type"})
        assert any("Invalid type" in p for p in problems)

    def test_missing_required(self, sample_schema):
        problems = validate_record(sample_schema, {"type": "expense"})
        assert any("Missing required field: domain" in p for p in problems)
        assert any("Missing required field: category" in p for p in problems)
        assert any("Missing required field: amount" in p for p in problems)

    def test_unknown_field(self, sample_schema, valid_record):
        valid_record["nonexistent"] = "value"
        problems = validate_record(sample_schema, valid_record)
        assert any("Unknown field" in p for p in problems)

    def test_invalid_option_value(self, sample_schema):
        record = {
            "type": "expense",
            "domain": "self",
            "category": "invalid_category",
            "amount": "50",
        }
        problems = validate_record(sample_schema, record)
        assert any("Invalid value" in p for p in problems)

    def test_int_field_validation(self, sample_schema):
        """amount is marked as type=int in [fields] metadata."""
        record = {"type": "income", "source": "salary", "amount": "abc"}
        problems = validate_record(sample_schema, record)
        assert any("must be integer" in p for p in problems)

    def test_conditional_required_satisfied(self, sample_schema):
        """receipt_no required when category=utilities."""
        record = {
            "type": "expense",
            "domain": "self",
            "category": "utilities",
            "amount": "100",
            "receipt_no": "R001",
        }
        problems = validate_record(sample_schema, record)
        assert problems == []

    def test_conditional_required_missing(self, sample_schema):
        """receipt_no required when category=utilities but missing."""
        record = {
            "type": "expense",
            "domain": "self",
            "category": "utilities",
            "amount": "100",
        }
        problems = validate_record(sample_schema, record)
        assert any("receipt_no" in p for p in problems)

    def test_conditional_not_triggered(self, sample_schema):
        """receipt_no not required when category=food."""
        record = {
            "type": "expense",
            "domain": "self",
            "category": "food",
            "amount": "100",
        }
        problems = validate_record(sample_schema, record)
        assert all("receipt_no" not in p for p in problems)

    def test_global_field_known(self, sample_schema):
        """project is a global field, should be recognized."""
        record = {
            "type": "expense",
            "domain": "self",
            "category": "food",
            "amount": "50",
            "project": "proj_a",
        }
        problems = validate_record(sample_schema, record)
        assert problems == []

    def test_tags_are_known_field(self, sample_schema):
        """tag is always a known field."""
        record = {
            "type": "expense",
            "domain": "self",
            "category": "food",
            "amount": "50",
            "tag": ["groceries"],
        }
        problems = validate_record(sample_schema, record)
        assert all("Unknown field" not in p for p in problems)

    def test_free_text_fields_pass(self, sample_schema):
        """vendor has no options defined — any value is valid."""
        record = {
            "type": "expense",
            "domain": "self",
            "category": "food",
            "amount": "50",
            "vendor": "any_store_123",
        }
        problems = validate_record(sample_schema, record)
        assert all("Invalid value" not in p for p in problems)


class TestResolveTags:
    def test_tags_for_food(self, sample_schema):
        ts = sample_schema["type"]["expense"]
        record = {"type": "expense", "category": "food"}
        tags = resolve_tags(sample_schema, ts, record)
        assert "groceries" in tags
        assert "dining" in tags
        assert "coffee" in tags

    def test_tags_for_transport(self, sample_schema):
        ts = sample_schema["type"]["expense"]
        record = {"type": "expense", "category": "transport"}
        tags = resolve_tags(sample_schema, ts, record)
        assert "fuel" in tags
        assert "parking" in tags
        assert "fare" in tags
        assert "groceries" not in tags

    def test_tags_no_category(self, sample_schema):
        ts = sample_schema["type"]["expense"]
        record = {"type": "expense"}
        tags = resolve_tags(sample_schema, ts, record)
        assert tags == []

    def test_tags_sorted(self, sample_schema):
        ts = sample_schema["type"]["expense"]
        record = {"type": "expense", "category": "transport"}
        tags = resolve_tags(sample_schema, ts, record)
        assert tags == sorted(tags)
