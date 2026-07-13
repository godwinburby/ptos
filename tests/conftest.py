import pytest
import datetime as dt
import os
import shutil
import ptos


_PATCHED_ATTRS = [
    "BASE_DIR", "SCRIPT_DIR", "CONFIG_DIR", "RECORDS_DIR", "JOURNAL_DIR",
    "TEMPLATE_DIR", "EXPORTS_DIR", "BACKUP_DIR", "TODO_DIR",
    "TODO_PATH", "DONE_PATH", "VERSION_FILE",
    "SCHEMA_PATH", "QUERIES_PATH", "CONFIG_PATH", "PRESETS_PATH",
]

_STARTER_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "starters")
_STARTER_FILES = {
    "schema.toml": "starter_schema.toml",
    "config.toml": "starter_config.toml",
    "queries.toml": "starter_queries.toml",
    "presets.toml": "starter_presets.toml",
}


@pytest.fixture(autouse=True)
def _isolated_ptos_paths(tmp_path, monkeypatch):
    """Force every test onto an isolated tmp dir, regardless of whether
    the test itself remembers to patch paths. A test that needs a
    specific layout can still override individual paths after this
    fixture runs — this just guarantees a safe baseline."""
    base = tmp_path / "ptos_test_home"
    base.mkdir()
    monkeypatch.setattr(ptos, "BASE_DIR", str(base))
    monkeypatch.setattr(ptos, "SCRIPT_DIR", str(base))
    monkeypatch.setattr(ptos, "CONFIG_DIR", str(base / "config"))
    monkeypatch.setattr(ptos, "RECORDS_DIR", str(base / "records"))
    monkeypatch.setattr(ptos, "JOURNAL_DIR", str(base / "journal"))
    monkeypatch.setattr(ptos, "TEMPLATE_DIR", str(base / "templates"))
    monkeypatch.setattr(ptos, "EXPORTS_DIR", str(base / "exports"))
    monkeypatch.setattr(ptos, "BACKUP_DIR", str(base / "backups"))
    monkeypatch.setattr(ptos, "TODO_DIR", str(base / "todo"))
    monkeypatch.setattr(ptos, "TODO_PATH", str(base / "todo" / "todo.txt"))
    monkeypatch.setattr(ptos, "DONE_PATH", str(base / "todo" / "done.txt"))
    monkeypatch.setattr(ptos, "VERSION_FILE", str(base / ".version"))
    (base / "config").mkdir(exist_ok=True)
    (base / "records").mkdir(exist_ok=True)
    (base / "todo").mkdir(exist_ok=True)
    (base / "journal").mkdir(exist_ok=True)
    (base / "templates").mkdir(exist_ok=True)
    (base / "exports").mkdir(exist_ok=True)
    (base / "backups").mkdir(exist_ok=True)
    for dest, src in _STARTER_FILES.items():
        src_path = os.path.join(_STARTER_DIR, src)
        if os.path.exists(src_path):
            shutil.copy2(src_path, str(base / "config" / dest))
    monkeypatch.setattr(ptos, "SCHEMA_PATH", str(base / "config" / "schema.toml"))
    monkeypatch.setattr(ptos, "QUERIES_PATH", str(base / "config" / "queries.toml"))
    monkeypatch.setattr(ptos, "CONFIG_PATH", str(base / "config" / "config.toml"))
    monkeypatch.setattr(ptos, "PRESETS_PATH", str(base / "config" / "presets.toml"))
    yield


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
