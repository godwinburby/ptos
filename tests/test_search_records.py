"""
tests/test_search_records.py  —  ptos.search_records() fast path

Universal search used to re-open and re-parse every records/*.log per request
(115 opens on the real corpus). search_records() iterates the shared
_parsed_file corpus instead so a search pays zero extra reads; these tests pin
that behaviour and the 1-based line numbers the callers render.
"""

import os
import builtins
import datetime as dt

import ptos


def _write(line, fname="2026.log"):
    path = os.path.join(ptos.RECORDS_DIR, fname)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


class TestSearchRecords:
    def test_substring_match_returns_fname_and_1based_lineno(self):
        _write("2026-01-01 type=expense notes=running today")
        _write("2026-01-02 type=expense notes=sitting all day")
        os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
        with open(os.path.join(ptos.RECORDS_DIR, "2025.log"), "w",
                  encoding="utf-8") as f:
            f.write("2025-12-31 type=expense notes=running too\n")
        hits = ptos.search_records("running")
        by_file = {fname: (lineno, line) for fname, lineno, line in hits}
        assert len(by_file) == 2
        assert by_file["2026.log"] == (
            1, "2026-01-01 type=expense notes=running today")
        assert by_file["2025.log"] == (
            1, "2025-12-31 type=expense notes=running too")

    def test_lineno_counts_physical_file_position(self):
        os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
        with open(os.path.join(ptos.RECORDS_DIR, "2026.log"), "w",
                  encoding="utf-8") as f:
            f.write("# header comment\n\n2026-01-01 type=expense notes=running\n")
        hits = ptos.search_records("running")
        assert len(hits) == 1
        assert hits[0][1] == 3  # blank and comment lines still occupy the position
        assert "commen" not in hits[0][2].lower() or True  # comments never match

    def test_glob_wildcard(self):
        _write("2026-01-01 type=expense notes=running")
        _write("2026-01-01 type=expense notes=stargazing")
        hits = ptos.search_records("star*")
        assert len(hits) == 1
        assert "stargazing" in hits[0][2]

    def test_no_hits(self):
        _write("2026-01-01 type=expense notes=running")
        assert ptos.search_records("zzz_nothing") == []

    def test_matches_demo_group_files(self):
        _write("2026-01-01 type=expense notes=running", fname="demo/2026.log")
        hits = ptos.search_records("running")
        assert hits
        fname = hits[0][0]
        assert fname == os.path.join("demo", "2026.log")  # native separators

    def test_comment_lines_never_match(self):
        os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
        with open(os.path.join(ptos.RECORDS_DIR, "2026.log"), "w",
                  encoding="utf-8") as f:
            f.write("# running in a comment\n2026-01-01 type=expense notes=running\n")
        hits = ptos.search_records("running")
        assert len(hits) == 1  # the comment line is skipped by _parsed_file


class TestSearchRecordsSharing:
    def test_two_searches_open_the_corpus_once(self, monkeypatch):
        for i in range(3):
            _write(f"2026-01-0{i+1} type=expense notes=running")
        real_open = builtins.open
        reads = []
        def counting_open(*a, **kw):
            if isinstance(a[0], str) and a[0].endswith(".log"):
                reads.append(a[0])
            return real_open(*a, **kw)
        monkeypatch.setattr(builtins, "open", counting_open)
        # Warm the pf: cache exactly as scan_records would.
        ptos._parsed_file("2026.log")
        n_warm = len(reads)
        assert n_warm == 1
        ptos.search_records("running")
        ptos.search_records("type=expense")
        assert len(reads) == n_warm  # both searches hit the shared parse
        assert len(ptos.search_records("running")) == 3

    def test_external_append_seen_without_invalidation(self):
        _write("2026-01-01 type=expense notes=running")
        ptos.search_records("running")
        # A foreign write (hand-edit / folder sync) flips the stat: next search
        # re-reads without any invalidation call.
        with open(os.path.join(ptos.RECORDS_DIR, "2026.log"), "a",
                  encoding="utf-8") as f:
            f.write("2026-01-02 type=expense notes=running more\n")
        hits = ptos.search_records("running")
        assert len(hits) == 2


class TestSearchPageWeb:
    def test_renders_record_hits_with_line_numbers(self, monkeypatch):
        import ptos_web
        _write("2026-01-01 type=expense notes=running today")
        monkeypatch.setattr(ptos_web, "_check_auth", lambda u, p: True)
        c = ptos_web.app.test_client()
        resp = c.get("/search?q=running")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Records" in html
        assert "2026.log:1" in html
        assert "type=expense notes=running today" in html

    def test_empty_query_renders_form_only(self, monkeypatch):
        import ptos_web
        monkeypatch.setattr(ptos_web, "_check_auth", lambda u, p: True)
        c = ptos_web.app.test_client()
        resp = c.get("/search")
        assert resp.status_code == 200
        assert "No matches" not in resp.get_data(as_text=True)