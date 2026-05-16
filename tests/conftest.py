import pytest
import datetime as dt


@pytest.fixture
def sample_schema():
    """A minimal but realistic schema dict matching ptos.py schema format."""
    return {
        "types": {"allowed": ["expense", "income", "journal"]},
        "type": {
            "expense": {
                "required": ["domain", "category", "amount"],
                "fields": {
                    "domain": {"options": ["self", "work", "joint"]},
                    "category": {
                        "options": {
                            "self": ["food", "transport", "utilities"],
                            "work": ["supplies", "travel"],
                        },
                        "parent": "domain",
                    },
                    "amount": {},
                    "pay_method": {"options": ["cash", "card", "transfer"]},
                    "vendor": {},
                },
                "tags": {
                    "category": {
                        "options": {
                            "food": ["groceries", "dining", "coffee"],
                            "transport": ["fuel", "parking", "fare"],
                            "utilities": ["electricity", "water", "internet"],
                            "supplies": ["office", "hardware"],
                        }
                    }
                },
                "conditions": {
                    "receipt_no": {"when": {"category": "utilities"}},
                },
            },
            "income": {
                "required": ["source", "amount"],
                "fields": {
                    "source": {"options": ["salary", "freelance", "gift"]},
                    "amount": {"is_int": True},
                },
            },
        },
        "fields": {
            "amount": {"type": "int"},
        },
        "global_fields": {
            "project": {"options": ["proj_a", "proj_b"]},
            "notes": {},
        },
        "shared": {
            "color": {"options": ["red", "green", "blue"]},
        },
    }


@pytest.fixture
def sample_schema_new_format():
    """Schema using the new [types]/[type_schema] format."""
    return {
        "types": {"allowed": ["expense", "income"]},
        "type_schema": {
            "expense": {
                "required": ["domain", "category", "amount"],
                "fields": {
                    "domain": {"options": ["self", "work"]},
                    "category": {
                        "parent": "domain",
                        "options": {
                            "self": ["food", "transport"],
                            "work": ["supplies"],
                        },
                    },
                    "amount": {},
                },
            },
            "income": {
                "required": ["source", "amount"],
                "fields": {
                    "source": {"options": ["salary", "freelance"]},
                    "amount": {},
                },
            },
        },
        "fields": {"amount": {"type": "int"}},
        "global_fields": {"project": {"options": ["proj_a"]}},
    }


@pytest.fixture
def valid_record():
    """A valid expense record."""
    return {
        "type": "expense",
        "domain": "self",
        "category": "food",
        "amount": "50",
        "tag": ["groceries"],
        "pay_method": "card",
    }


class MockInput:
    """Helper to simulate interactive input for tests that prompt the user."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.idx = 0

    def __call__(self, prompt=""):
        if self.idx >= len(self.answers):
            raise EOFError("No more mock answers")
        ans = self.answers[self.idx]
        self.idx += 1
        return ans
