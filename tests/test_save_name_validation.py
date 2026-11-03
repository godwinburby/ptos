"""Tests for name validation on the six scoped save functions."""
import textwrap

import pytest
import tomllib
import tomli_w

import ptos
import ptos_service as svc
from ptos import PTOSError

BAD_NAMES = ["Bad Name!", "a.b", "UPPER", "x\"]\n"]


@pytest.fixture(autouse=True)
def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(ptos, "QUERIES_PATH", str(tmp_path / "queries.toml"))
    monkeypatch.setattr(svc, "QUERIES_PATH", str(tmp_path / "queries.toml"))
    with open(ptos.QUERIES_PATH, "w", encoding="utf-8") as f:
        f.write("")
    ptos._invalidate_all()


VALID_CFG = {
    "board": {"columns": ["task"]},
    "habit": {"filters": ["type=habit name=run"], "weeks": 8},
    "calendar": {"filters": ["type=expense"]},
    "threshold": {"metric": "expenses", "direction": "max"},
    "todo": {"project": "x"},
    "due": {"type": "todo", "key": "due", "days": 7},
}

KIND_PREFIX = {"todo": "todo"}


def _call(kind, name, cfg):
    if kind == "board":
        return svc.save_board(name, cfg)
    if kind == "habit":
        return svc.save_habit(name, cfg)
    if kind == "calendar":
        return svc.save_calendar(name, cfg)
    if kind == "threshold":
        return svc.save_threshold(name, cfg)
    if kind == "todo":
        return svc.save_todo_view(name, cfg)
    if kind == "due":
        return svc.save_due(name, cfg)


@pytest.mark.parametrize("kind", list(VALID_CFG))
@pytest.mark.parametrize("bad", BAD_NAMES + ["   "])
def test_bad_name_rejected(kind, bad):
    with pytest.raises(PTOSError):
        _call(kind, bad, dict(VALID_CFG[kind]))


@pytest.mark.parametrize("kind", list(VALID_CFG))
def test_good_name_accepted(kind):
    res = _call(kind, "good_name", dict(VALID_CFG[kind]))
    assert res.get("ok") is True


def test_legacy_name_edit_accepted():
    legacy = "Bad Name!"
    # seed a habit entry with the legacy (bad) name directly
    data = {"habit." + legacy: {"filters": ["type=habit"], "weeks": 12}}
    with open(ptos.QUERIES_PATH, "w", encoding="utf-8") as f:
        f.write(tomli_w.dumps(data))
    ptos._invalidate_all()
    # editing the existing entry with the same bad name must succeed
    res = svc.save_habit(legacy, {"filters": ["type=habit name=run"], "weeks": 8})
    assert res.get("ok") is True
