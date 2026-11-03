"""Tests for ptos_web._valid_log_filename."""
import os

import pytest

import ptos
import ptos_service as svc
from ptos_web import _valid_log_filename

ACCEPTED = ["a.log", "grp/a.log", "grp\\a.log", "grp/sub/a.log"]
REJECTED = [
    "../a.log", "a/../b.log", "/etc/passwd", "\\\\server\\share\\x.log",
    "C:\\x.log", "C:x.log", "a//b.log", "./a.log", "a.log/", "", None, " ",
]


@pytest.mark.parametrize("name", ACCEPTED)
def test_accepted(name):
    assert _valid_log_filename(name) is True


@pytest.mark.parametrize("name", REJECTED)
def test_rejected(name):
    assert _valid_log_filename(name) is False


def test_path_within():
    rd = svc.RECORDS_DIR
    assert ptos._path_within(os.path.join(rd, "grp", "a.log"), rd) is True
    assert ptos._path_within(os.path.join(rd, "..", "x.log"), rd) is False
