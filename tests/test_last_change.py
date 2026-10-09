import os
import time

import ptos
from ptos_service import get_last_change


def _all_data_files():
    paths = []
    for d in (ptos.RECORDS_DIR, ptos.TODO_DIR, ptos.JOURNAL_DIR,
              ptos.NOTES_DIR, ptos.CONFIG_DIR):
        for root, _dirs, files in os.walk(d):
            for name in files:
                paths.append(os.path.join(root, name))
    return paths


def _set_all_mtime(t):
    for path in _all_data_files():
        os.utime(path, (t, t))


class TestLatestDataMtime:
    def test_none_when_empty(self):
        for path in _all_data_files():
            os.remove(path)
        ptos._reset_last_change()
        assert ptos.latest_data_mtime() is None

    def test_picks_newest_across_dirs(self):
        os.makedirs(ptos.NOTES_DIR, exist_ok=True)
        future = time.time() + 100
        note = os.path.join(ptos.NOTES_DIR, "n.md")
        with open(note, "w", encoding="utf-8") as f:
            f.write("hi\n")
        os.utime(note, (future, future))
        ptos._reset_last_change()
        assert abs(ptos.latest_data_mtime() - future) < 0.01

    def test_skips_bak_and_tmp(self):
        os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
        keep = time.time() + 100
        rp = os.path.join(ptos.RECORDS_DIR, "2026.log")
        with open(rp, "w", encoding="utf-8") as f:
            f.write("2026-10-09 type=x\n")
        os.utime(rp, (keep, keep))
        for name in ("2026.log.bak", "2026.log.tmp"):
            p = os.path.join(ptos.RECORDS_DIR, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write("x\n")
            os.utime(p, (keep + 500, keep + 500))
        ptos._reset_last_change()
        assert abs(ptos.latest_data_mtime() - keep) < 0.01

    def test_cache_refreshes_after_reset(self):
        ptos._reset_last_change()
        first = ptos.latest_data_mtime()
        os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
        future = time.time() + 100
        rp = os.path.join(ptos.RECORDS_DIR, "2026.log")
        with open(rp, "w", encoding="utf-8") as f:
            f.write("2026-10-09 type=x\n")
        os.utime(rp, (future, future))
        assert ptos.latest_data_mtime() == first
        ptos._reset_last_change()
        assert abs(ptos.latest_data_mtime() - future) < 0.01


class TestGetLastChange:
    def test_empty(self):
        for path in _all_data_files():
            os.remove(path)
        ptos._reset_last_change()
        assert get_last_change() == {
            "label": None, "exact": None, "epoch": None, "iso": None}

    def test_recent_label(self):
        os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
        now = time.time()
        rp = os.path.join(ptos.RECORDS_DIR, "2026.log")
        with open(rp, "w", encoding="utf-8") as f:
            f.write("2026-10-09 type=x\n")
        os.utime(rp, (now, now))
        _set_all_mtime(now)
        ptos._reset_last_change()
        result = get_last_change()
        assert result["label"] == "just now"
        assert result["epoch"] is not None
        assert result["iso"]

    def test_old_label_is_absolute(self):
        os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
        rp = os.path.join(ptos.RECORDS_DIR, "2026.log")
        with open(rp, "w", encoding="utf-8") as f:
            f.write("2026-10-09 type=x\n")
        old = time.time() - 3 * 86400
        _set_all_mtime(old)
        ptos._reset_last_change()
        result = get_last_change()
        assert result["label"] == result["exact"]
        assert "ago" not in result["label"]
