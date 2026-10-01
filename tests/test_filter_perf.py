"""Tests for the apply_where scan fast path.

apply_where() runs once per record, so any per-line work that does not depend
on the record is paid for every record in the log. Two such costs were
removed: re-tokenizing the filter string, and computing derived fields that
the filter never references.

Every scan here passes an explicit start/end range -- never a defaulted time
window -- so these tests cannot break on a month rollover.
"""
import datetime as dt
import os

import pytest

import ptos


def _clean_cache():
    ptos._CACHE.clear()
    ptos._invalidate_all()


def _write_records(lines):
    """Write record lines into the log file for their own year."""
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    by_year = {}
    for line in lines:
        d, _, _ = ptos.parse_line(line)
        by_year.setdefault(d.year, []).append(line)
    for year, group in by_year.items():
        with open(os.path.join(ptos.RECORDS_DIR, f"{year}.log"),
                  "w", encoding="utf-8") as f:
            f.write("\n".join(group) + "\n")


D_MIN, D_MAX = dt.date.min, dt.date.max
FIXED_DATE = "2026-03-04"


class TestTokenCache:
    def test_cached_matches_uncached(self):
        exprs = [
            "type=capture",
            "type=expense AND domain!=work",
            "type=expense AND domain=home AND category=food AND (tag=bakery OR tag=snacks)",
            "NOT stage=closed AND amount>=500",
            "amount > 100",
            "tag ~= auto",
        ]
        for expr in exprs:
            assert (ptos._tok_where_cached(expr)
                    == ptos._tok_where(expr)), expr

    def test_cache_populates_and_reuses(self):
        _clean_cache()
        assert ptos._WHERE_TOKEN_CACHE == {}
        first = ptos._tok_where_cached("type=capture")
        assert ptos._WHERE_TOKEN_CACHE == {"type=capture": first}
        # second call returns the identical object, not a re-tokenized copy
        assert ptos._tok_where_cached("type=capture") is first
        assert len(ptos._WHERE_TOKEN_CACHE) == 1

    def test_invalidate_all_clears_cache(self):
        ptos._tok_where_cached("type=capture")
        ptos._is_expression_cached("type=a AND b")
        ptos._filter_derived_cached(["type=capture"])
        assert ptos._WHERE_TOKEN_CACHE
        assert ptos._IS_EXPRESSION_CACHE
        assert ptos._FILTER_DERIVED_CACHE
        _clean_cache()
        assert ptos._WHERE_TOKEN_CACHE == {}
        assert ptos._IS_EXPRESSION_CACHE == {}
        assert ptos._FILTER_DERIVED_CACHE == {}

    def test_is_expression_cache_matches_uncached(self):
        for expr in ["type=capture", "a=1 AND b=2", "NOT a=1",
                     "(a=1 OR b=2)", "tag=auto"]:
            assert (ptos._is_expression_cached(expr)
                    == bool(ptos._is_expression(expr))), expr

    def test_filter_derived_cache_matches_uncached(self):
        _clean_cache()
        _add_derived_field("days_since", "(today - date).days")
        for filters in (["type=capture"], ["days_since>5"], ["type=a", "days_since>2"]):
            assert (ptos._filter_derived_cached(filters)
                    == ptos._filter_derived_fields(filters)), filters

    def test_unchanged_results_after_invalidation(self):
        kv = {"type": "expense", "domain": "work", "category": "food",
              "amount": "50", "_date": dt.date(2026, 3, 4)}
        filt = ["type=expense AND domain=work"]
        _clean_cache()
        before = ptos.apply_where(kv, filt)
        for _ in range(50):
            ptos.apply_where(kv, filt)
        ptos._invalidate_all()
        assert ptos.apply_where(kv, filt) == before


def _add_derived_field(name, expr, rtype=None):
    """Add a derived field to the live schema (the starter has none)."""
    schema = ptos.get_schema()
    if rtype is None:
        schema.setdefault("fields", {})[name] = {"derived": expr}
    else:
        schema.setdefault("type", {}).setdefault(rtype, {}).setdefault(
            "derived_fields", {})[name] = {"expr": expr}
    ptos._CACHE["schema"] = schema
    # drop only the derived_fields memo so the new field is picked up
    ptos._CACHE.pop("derived_fields", None)
    ptos._WHERE_TOKEN_CACHE.clear()


class TestDerivedFieldSkip:
    def test_detects_nothing_for_plain_filter(self):
        assert ptos._filter_derived_fields(["type=capture"]) == ()
        assert ptos._filter_derived_fields(["type=expense AND domain=work"]) == ()

    def test_detects_global_derived_field(self):
        _add_derived_field("days_since", "(today - date).days")
        names = ptos._filter_derived_fields(["days_since>5"])
        assert "days_since" in names

    def test_detects_type_scoped_derived_field_by_bare_name(self):
        # stored as "prescription.balance", referenced in filters as "balance"
        _add_derived_field("balance", "amount - advance", rtype="prescription")
        names = ptos._filter_derived_fields(["balance>100"])
        assert "prescription.balance" in names

    def test_conservative_on_substring(self):
        _clean_cache()
        _add_derived_field("balance", "amount - advance")
        # "balance_sheet" contains "balance" -> computes unnecessarily, but the
        # result must still be correct
        kv = {"type": "expense", "amount": "300", "advance": "50",
              "_date": dt.date(2026, 3, 4)}
        assert ptos.apply_where(kv, ["balance_sheet=x"]) is False
        assert ptos.apply_where(kv, ["balance>100"]) is True

    def test_empty_filters(self):
        assert ptos._filter_derived_fields([]) == ()
        assert ptos._filter_derived_fields(None) == ()

    def test_compute_derived_skipped_when_unreferenced(self, monkeypatch):
        calls = []
        real = ptos.compute_derived

        def counting(kv, record_date=None):
            calls.append(1)
            return real(kv, record_date=record_date)

        monkeypatch.setattr(ptos, "compute_derived", counting)
        _clean_cache()

        kv = {"type": "capture", "_date": dt.date(2026, 3, 4)}
        for _ in range(20):
            assert ptos.apply_where(kv, ["type=capture"])
        assert calls == [], "compute_derived ran for a filter with no derived field"

    def test_compute_derived_still_runs_when_referenced(self, monkeypatch):
        calls = []
        real = ptos.compute_derived

        def counting(kv, record_date=None):
            calls.append(1)
            return real(kv, record_date=record_date)

        monkeypatch.setattr(ptos, "compute_derived", counting)
        _clean_cache()
        _add_derived_field("days_since", "(today - date).days")

        kv = {"type": "capture", "_date": dt.date(2026, 3, 4)}
        ptos.apply_where(kv, ["days_since>5"])
        assert calls, "compute_derived was skipped for a derived-referencing filter"

    def test_derived_filter_still_selects_correctly(self):
        # a record 10 days old must satisfy days_since>5, one 1 day old must not
        _clean_cache()
        _add_derived_field("days_since", "(today - date).days")
        today = dt.date.today()
        old = {"type": "capture", "_date": today - dt.timedelta(days=10)}
        new = {"type": "capture", "_date": today - dt.timedelta(days=1)}
        assert ptos.apply_where(old, ["days_since>5"]) is True
        assert ptos.apply_where(new, ["days_since>5"]) is False


class TestFilterEquivalence:
    """Every starter queries.toml filter must behave the same as before."""

    FILTERS = [
        ["type=capture"],
        ["type=expense AND category=food"],
        ["type=expense AND domain!=work"],
        ["type=expense AND domain=home AND category=food AND (tag=bakery OR tag=snacks)"],
        ["type=expense AND tag=snacks AND domain!=work"],
        ["type=assessment AND outcome=deferred"],
        ["type=prescription AND fit=binaural"],
    ]

    RECORDS = [
        f"{FIXED_DATE} type=capture tag=inbox | walked",
        f"{FIXED_DATE} type=expense domain=self category=food amount=50 tag=bakery",
        f"{FIXED_DATE} type=expense domain=work category=food amount=20 tag=snacks",
        f"{FIXED_DATE} type=expense domain=self category=other amount=10",
        f"{FIXED_DATE} type=assessment domain=clinic source=dr outcome=deferred",
        f"{FIXED_DATE} type=prescription amount=300 advance=50 fit=binaural",
    ]

    def _matches(self, filters):
        _write_records(self.RECORDS)
        _clean_cache()
        found, _total = ptos.scan_records(D_MIN, D_MAX, filters, None)
        return sorted(found)

    @pytest.mark.parametrize("filters", FILTERS, ids=lambda f: "|".join(f))
    def test_scan_matches_expected(self, filters):
        for rec in self.RECORDS:
            d, kv, _rest = ptos.parse_line(rec)
            expected = ptos.apply_where(dict(kv, _date=d), filters)
            _clean_cache()
            _write_records([rec])
            found, _t = ptos.scan_records(D_MIN, D_MAX, filters, None)
            assert bool(found) == expected, f"{filters} vs {rec}"

    def test_multi_filter_legacy_chain(self):
        results = self._matches(["type=expense", "category=food"])
        assert results == [
            f"{FIXED_DATE} type=expense domain=self category=food amount=50 tag=bakery",
            f"{FIXED_DATE} type=expense domain=work category=food amount=20 tag=snacks",
        ]

    def test_or_expression(self):
        results = self._matches(["type=capture OR type=assessment"])
        assert len(results) == 2

    def test_no_filter_matches_everything(self):
        results = self._matches([])
        assert len(results) == len(self.RECORDS)


class TestScanSpeedup:
    def test_repeated_filtered_scan_reuses_tokens(self, monkeypatch):
        """The tokenizer must run once per distinct filter, not once per record."""
        calls = []
        real = ptos._tok_where

        def counting(expr):
            calls.append(expr)
            return real(expr)

        _write_records([f"{FIXED_DATE} type=expense amount=1"] * 200)
        _clean_cache()
        monkeypatch.setattr(ptos, "_tok_where", counting)

        ptos.scan_records(D_MIN, D_MAX, ["type=expense"], None)
        assert len(calls) == 1, f"tokenizer ran {len(calls)}x for one filter"

        ptos.scan_records(D_MIN, D_MAX, ["type=expense"], None)
        assert len(calls) == 1, "tokenizer re-ran on a warm cache"