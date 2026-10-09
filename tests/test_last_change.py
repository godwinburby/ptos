import os
import re
import time

import ptos
from ptos_service import get_last_change

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

    def test_hour_label_shows_minutes(self):
        os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
        rp = os.path.join(ptos.RECORDS_DIR, "2026.log")
        with open(rp, "w", encoding="utf-8") as f:
            f.write("2026-10-09 type=x\n")
        _set_all_mtime(time.time() - 3900)
        ptos._reset_last_change()
        assert get_last_change()["label"] == "1 hr 5 min ago"


class TestLastChangeMarkup:
    def _read(self, *parts):
        with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
            return f.read()

    def test_base_carries_epoch_and_prefix(self):
        base = self._read("web_templates", "base.html")
        assert 'class="last-change" data-epoch="{{ last_change.epoch }}"' in base
        assert 'data-prefix="· changed "' in base
        assert 'data-prefix="Last change: "' in base

    def test_base_loads_the_ticker_via_av(self):
        base = self._read("web_templates", "base.html")
        assert base.count("av('/static/js/last_change.js')") == 1

    def test_ticker_recomputes_from_the_epoch(self):
        js = self._read("web_static", "js", "last_change.js")
        assert ".last-change[data-epoch]" in js
        assert "getAttribute(\"data-epoch\")" in js
        assert "setInterval(refresh, 30000)" in js
        assert "visibilitychange" in js
        assert "pageshow" in js

    def test_ticker_mirrors_the_hour_minute_phrasing(self):
        js = self._read("web_static", "js", "last_change.js")
        assert '" hr "' in js
        assert '" min ago"' in js

    def test_ticker_has_no_jinja(self):
        js = self._read("web_static", "js", "last_change.js")
        assert "{{" not in js
        assert "{%" not in js


class TestQueriesScrollsToResults:
    def test_mobile_scroll_helper_wired_into_chip_and_threshold(self):
        html = open(os.path.join(REPO, "web_templates", "queries.html"),
                    encoding="utf-8").read()
        assert "function _scrollToResults()" in html
        assert "max-width: 767px" in html
        chip = re.search(r"function _selectChip\b.*?\n}", html, re.S).group(0)
        assert "_scrollToResults()" in chip
        thr = re.search(r"function _selectThreshold\b.*?\n}", html, re.S).group(0)
        assert "_scrollToResults()" in thr
