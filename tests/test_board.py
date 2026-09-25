import pytest
import datetime as dt
import os
import json
import re
import tomli_w
import ptos
from ptos_service import (get_board_data, advance_record, save_queries_full,
                          PTOSError, board_move_record, save_board, move_record)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_queries(boards):
    """Write board configs into the test queries.toml."""
    qpath = ptos.QUERIES_PATH
    existing = {}
    if os.path.exists(qpath):
        with open(qpath, "rb") as f:
            import tomllib
            existing = tomllib.load(f)
    for name, cfg in boards.items():
        existing[f"board.{name}"] = cfg
    with open(qpath, "wb") as f:
        tomli_w.dump(existing, f)
    ptos._invalidate_all()


def _write_record(date_str, line_text):
    """Write a single record line to the appropriate year file."""
    year = date_str[:4]
    rdir = ptos.RECORDS_DIR
    os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(rdir, f"{year}.log"), "a", encoding="utf-8") as f:
        f.write(line_text + "\n")


# ── filter_fields_for_type ────────────────────────────────────────────────────

class TestFilterFieldsForType:
    def test_basic(self, sample_schema):
        fields = ptos.filter_fields_for_type("expense", sample_schema)
        assert "date" in fields
        assert "type" in fields
        assert "project" in fields  # global_field
        assert "notes" in fields    # global_field
        assert "domain" in fields
        assert "category" in fields
        assert "amount" in fields
        assert "pay_method" in fields
        assert "vendor" in fields
        assert "receipt_no" in fields  # from conditions
        assert fields == sorted(set(fields))

    def test_includes_required(self, sample_schema):
        fields = ptos.filter_fields_for_type("income", sample_schema)
        assert "source" in fields
        assert "amount" in fields

    def test_excludes_unrelated_fields(self, sample_schema):
        expense_fields = set(ptos.filter_fields_for_type("expense", sample_schema))
        income_fields = set(ptos.filter_fields_for_type("income", sample_schema))
        assert "pay_method" in expense_fields
        assert "pay_method" not in income_fields


# ── get_column_field_overlap ──────────────────────────────────────────────────

class TestGetColumnFieldOverlap:
    def test_empty_list(self, sample_schema):
        assert ptos.get_column_field_overlap([], sample_schema) == []

    def test_single_type(self, sample_schema):
        result = ptos.get_column_field_overlap(["expense"], sample_schema)
        assert "date" in result
        assert "type" in result
        assert "project" in result
        assert "amount" in result

    def test_intersection(self, sample_schema):
        result = ptos.get_column_field_overlap(["expense", "income"], sample_schema)
        assert "date" in result
        assert "type" in result
        assert "project" in result
        assert "notes" in result
        assert "amount" in result
        assert "domain" not in result
        assert "source" not in result
        assert "pay_method" not in result

    def test_no_common_fields(self, sample_schema):
        result = ptos.get_column_field_overlap(["expense", "expense"], sample_schema)
        assert "date" in result
        assert "amount" in result


# ── get_board_data ────────────────────────────────────────────────────────────

class TestGetBoardData:
    def test_unknown_board(self):
        _write_queries({})
        with pytest.raises(PTOSError):
            get_board_data("nonexistent_board")

    def test_no_columns(self):
        _write_queries({"test_board": {"columns": []}})
        with pytest.raises(PTOSError):
            get_board_data("test_board")

    def test_column_type_not_in_schema(self):
        _write_queries({"test_board": {"columns": ["bogus_type"]}})
        with pytest.raises(PTOSError):
            get_board_data("test_board")

    def test_time_window_all(self):
        _write_queries({"b": {"columns": ["expense"], "time_window": "all"}})
        result = get_board_data("b")
        assert result["time_window"] == "all"
        assert "expense" in result["data"]

    def test_time_window_this_week(self):
        _write_queries({"b": {"columns": ["expense"], "time_window": "this-week"}})
        result = get_board_data("b")
        assert result["time_window"] == "this-week"

    def test_time_window_last_month(self):
        _write_queries({"b": {"columns": ["expense"], "time_window": "last-month"}})
        result = get_board_data("b")
        assert result["time_window"] == "last-month"

    def test_time_window_last_3_months(self):
        _write_queries({"b": {"columns": ["expense"], "time_window": "last-3-months"}})
        result = get_board_data("b")
        assert result["time_window"] == "last-3-months"

    def test_time_window_this_year(self):
        _write_queries({"b": {"columns": ["expense"], "time_window": "this-year"}})
        result = get_board_data("b")
        assert result["time_window"] == "this-year"

    def test_time_window_default_this_month(self):
        _write_queries({"b": {"columns": ["expense"]}})
        result = get_board_data("b")
        assert result["time_window"] == "this-month"

    def test_time_window_today(self):
        _write_queries({"b": {"columns": ["expense"], "time_window": "td"}})
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense amount=1")
        other = dt.date.today().replace(day=2) if dt.date.today().day == 1 else dt.date.today().replace(day=1)
        _write_record(other.isoformat(), f"{other.isoformat()} type=expense amount=2")
        result = get_board_data("b")
        assert result["time_window"] == "td"
        amounts = [r["amount"] for r in result["data"].get("expense", [])]
        assert amounts == ["1"]

    def test_time_window_last_week(self):
        _write_queries({"b": {"columns": ["expense"], "time_window": "lw"}})
        start, end = ptos.resolve_time("lw", {})
        _write_record(start.isoformat(), f"{start.isoformat()} type=expense amount=1")
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense amount=2")
        result = get_board_data("b")
        amounts = [r["amount"] for r in result["data"].get("expense", [])]
        assert amounts == ["1"]

    def test_time_window_last_quarter(self):
        _write_queries({"b": {"columns": ["expense"], "time_window": "lq"}})
        start, end = ptos.resolve_time("lq", {})
        _write_record(start.isoformat(), f"{start.isoformat()} type=expense amount=1")
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense amount=2")
        result = get_board_data("b")
        amounts = [r["amount"] for r in result["data"].get("expense", [])]
        assert amounts == ["1"]

    def test_time_window_last_year(self):
        _write_queries({"b": {"columns": ["expense"], "time_window": "ly"}})
        start, end = ptos.resolve_time("ly", {})
        _write_record(start.isoformat(), f"{start.isoformat()} type=expense amount=1")
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense amount=2")
        result = get_board_data("b")
        amounts = [r["amount"] for r in result["data"].get("expense", [])]
        assert amounts == ["1"]

    def test_time_window_param_literal_year(self):
        _write_queries({"b": {"columns": ["expense"], "time_window": "all"}})
        year = str(dt.date.today().year - 1)
        _write_record(f"{year}-06-01", f"{year}-06-01 type=expense amount=1")
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense amount=2")
        result = get_board_data("b", time=year)
        assert result["time_window"] == year
        amounts = [r["amount"] for r in result["data"].get("expense", [])]
        assert amounts == ["1"]

    def test_time_window_param_literal_month(self):
        _write_queries({"b": {"columns": ["expense"]}})
        year, month = dt.date.today().year, str(dt.date.today().month).zfill(2)
        key = f"{year}-{month}"
        _write_record(f"{key}-01", f"{key}-01 type=expense amount=1")
        from datetime import date as _date
        other = (_date(year, 1, 1) + dt.timedelta(days=400)).isoformat() if month == "01" else f"{year}-01-01"
        _write_record(other, f"{other} type=expense amount=2")
        result = get_board_data("b", time=key)
        assert result["time_window"] == key
        amounts = [r["amount"] for r in result["data"].get("expense", [])]
        assert "2" not in amounts

    def test_time_window_param_from_date_to_date(self):
        _write_queries({"b": {"columns": ["expense"]}})
        _write_record("2026-06-01", "2026-06-01 type=expense amount=1")
        _write_record("2026-06-10", "2026-06-10 type=expense amount=2")
        _write_record("2026-07-01", "2026-07-01 type=expense amount=3")
        result = get_board_data("b", from_date="2026-06-01", to_date="2026-06-30")
        assert result["time_window"] == "range"
        amounts = [r["amount"] for r in result["data"].get("expense", [])]
        assert amounts == ["2", "1"]

    def test_time_param_precedence_over_config(self):
        _write_queries({"b": {"columns": ["expense"], "time_window": "all"}})
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense amount=1")
        _write_record("2020-01-01", "2020-01-01 type=expense amount=2")
        result = get_board_data("b", time="td")
        assert result["time_window"] == "td"
        amounts = [r["amount"] for r in result["data"].get("expense", [])]
        assert amounts == ["1"]

    def test_limit_truncates(self):
        _write_queries({"b": {"columns": ["expense"], "limit": 1}})
        today = dt.date.today().isoformat()
        for i in range(3):
            _write_record(today, f"{today} type=expense amount={i}")
        result = get_board_data("b")
        assert len(result["data"].get("expense", [])) == 1
        assert result["truncated"].get("expense") == 3

    def test_limit_zero_returns_all(self):
        _write_queries({"b": {"columns": ["expense"], "limit": 0}})
        result = get_board_data("b")
        assert "expense" in result["data"]
        assert result["truncated"] == {}

    def test_card_title_fields_list(self):
        _write_queries({"b": {"columns": ["expense"],
                              "card_title_fields": ["project", "amount"]}})
        result = get_board_data("b")
        assert result["card_title_fields"] == ["project", "amount"]

    def test_card_title_fields_string(self):
        _write_queries({"b": {"columns": ["expense"],
                              "card_title_fields": "project, amount"}})
        result = get_board_data("b")
        assert result["card_title_fields"] == ["project", "amount"]

    def test_card_title_fields_fallback(self):
        _write_queries({"b": {"columns": ["expense"],
                              "card_title_fields": 123}})
        result = get_board_data("b")
        assert result["card_title_fields"] == []


# ── board rollups ──────────────────────────────────────────────────────────────

class TestBoardRollup:
    def _write_amounts(self, amounts, col_type="expense", field="amount"):
        today = dt.date.today().isoformat()
        for a in amounts:
            _write_record(today, f"{today} type={col_type} {field}={a}")

    def test_default_no_rollup_field(self):
        _write_queries({"b": {"columns": ["expense"]}})
        result = get_board_data("b")
        assert result["rollups"]["expense"] is None
        assert result["rollup_op"] == "count"

    def test_default_op_count(self):
        _write_queries({"b": {"columns": ["expense"], "rollup_field": "amount"}})
        self._write_amounts([1, 2, 3])
        result = get_board_data("b")
        assert result["rollup_op"] == "count"
        assert result["rollups"]["expense"] == 3

    def test_sum(self):
        _write_queries({"b": {"columns": ["expense"],
                              "rollup_field": "amount", "rollup_op": "sum"}})
        self._write_amounts([10, 20, 30])
        result = get_board_data("b")
        assert result["rollups"]["expense"] == 60

    def test_avg(self):
        _write_queries({"b": {"columns": ["expense"],
                              "rollup_field": "amount", "rollup_op": "avg"}})
        self._write_amounts([10, 20, 30])
        result = get_board_data("b")
        assert result["rollups"]["expense"] == 20

    def test_avg_no_records(self):
        _write_queries({"b": {"columns": ["expense"],
                              "rollup_field": "amount", "rollup_op": "avg"}})
        result = get_board_data("b")
        assert result["rollups"]["expense"] is None

    def test_sum_skips_non_numeric(self):
        _write_queries({"b": {"columns": ["expense"],
                              "rollup_field": "amount", "rollup_op": "sum"}})
        self._write_amounts([10, "abc", 20])
        result = get_board_data("b")
        assert result["rollups"]["expense"] == 30

    def test_sum_over_full_set_before_limit(self):
        _write_queries({"b": {"columns": ["expense"], "limit": 1,
                              "rollup_field": "amount", "rollup_op": "sum"}})
        self._write_amounts([10, 20, 30])
        result = get_board_data("b")
        assert len(result["data"]["expense"]) == 1
        assert result["rollups"]["expense"] == 60

    def test_rollup_skipped_for_type_missing_field(self):
        _write_queries({"b": {"columns": ["expense", "exercise"],
                              "rollup_field": "amount", "rollup_op": "sum"}})
        self._write_amounts([10, 20], col_type="expense")
        self._write_amounts([5], col_type="exercise", field="duration")
        result = get_board_data("b")
        assert result["rollups"]["expense"] == 30
        assert result["rollups"]["exercise"] is None

    def test_missing_field_value_treated_as_skip(self):
        _write_queries({"b": {"columns": ["expense"],
                              "rollup_field": "amount", "rollup_op": "sum"}})
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense amount=10")
        _write_record(today, f"{today} type=expense")
        result = get_board_data("b")
        assert result["rollups"]["expense"] == 10


# ── board cross-column match highlight ────────────────────────────────────────

class TestBoardMatchHighlight:
    def _board(self, match_field="project", columns=("expense", "exercise"),
               limit=None, extra=None):
        cfg = {"columns": list(columns), "match_field": match_field}
        if limit:
            cfg["limit"] = limit
        if extra:
            cfg.update(extra)
        _write_queries({"b": cfg})

    def test_match_field_returned(self):
        self._board()
        result = get_board_data("b")
        assert result["match_field"] == "project"

    def test_no_match_field_returns_none(self):
        _write_queries({"b": {"columns": ["expense"]}})
        result = get_board_data("b")
        assert result["match_field"] is None

    def test_blank_match_field_returns_none(self):
        _write_queries({"b": {"columns": ["expense"], "match_field": "   "}})
        result = get_board_data("b")
        assert result["match_field"] is None

    def test_same_value_across_columns_same_color(self):
        self._board()
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense project=alpha amount=1")
        _write_record(today, f"{today} type=exercise project=alpha duration=10")
        result = get_board_data("b")
        exp = result["data"]["expense"][0]
        exe = result["data"]["exercise"][0]
        assert exp["_link_color"] == exe["_link_color"]
        assert exp["_link_group"] == "alpha"
        assert exe["_link_group"] == "alpha"

    def test_lone_value_uncolored(self):
        self._board()
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense project=beta amount=1")
        result = get_board_data("b")
        exp = result["data"]["expense"][0]
        assert "_link_color" not in exp
        assert "_link_group" not in exp

    def test_empty_match_value_skipped(self):
        self._board()
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense amount=1")
        _write_record(today, f"{today} type=exercise duration=10")
        result = get_board_data("b")
        for r in result["data"]["expense"] + result["data"]["exercise"]:
            assert "_link_color" not in r

    def test_color_stable_for_value(self):
        self._board()
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense project=alpha amount=1")
        _write_record(today, f"{today} type=exercise project=alpha duration=10")
        result1 = get_board_data("b")
        result2 = get_board_data("b")
        assert (result1["data"]["expense"][0]["_link_color"] ==
                result2["data"]["expense"][0]["_link_color"])

    def test_matching_over_full_set_before_limit(self):
        # Matching counts siblings over the FULL per-column set before limit
        # truncation (like rollups), so a value whose only sibling was truncated
        # out of a column is still treated as matched on the visible cards.
        self._board(limit=1, extra={"time_window": "all"})
        _write_record("2024-01-01", "2024-01-01 type=expense project=alpha amount=1")
        _write_record("2026-09-01", "2026-09-01 type=expense project=gamma amount=2")
        _write_record("2026-09-01", "2026-09-01 type=exercise project=alpha duration=10")
        result = get_board_data("b")
        # expense is truncated to the newest 1 (gamma); alpha's record dropped
        assert result["truncated"].get("expense") == 2
        assert [r["project"] for r in result["data"]["expense"]] == ["gamma"]
        exe = result["data"]["exercise"][0]
        assert exe["_link_group"] == "alpha"
        assert "_link_color" in exe

    def test_two_values_same_color_per_group(self):
        self._board()
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense project=alpha amount=1")
        _write_record(today, f"{today} type=exercise project=alpha duration=10")
        _write_record(today, f"{today} type=expense project=beta amount=2")
        _write_record(today, f"{today} type=exercise project=beta duration=20")
        result = get_board_data("b")
        alpha = [r for r in result["data"]["expense"] if r["project"] == "alpha"][0]
        beta = [r for r in result["data"]["expense"] if r["project"] == "beta"][0]
        assert alpha["_link_color"] != beta["_link_color"]

    def test_no_color_overlap_for_distinct_codes(self):
        # Every distinct matched code gets its own color (up to the palette
        # size), so different codes never share a color in one view.
        self._board()
        today = dt.date.today().isoformat()
        for i in range(16):
            code = f"c{i:02d}"
            _write_record(today, f"{today} type=expense project={code} amount=1")
            _write_record(today, f"{today} type=exercise project={code} duration=10")
        result = get_board_data("b")
        colors = {r["_link_group"]: r["_link_color"]
                  for col in result["data"].values() for r in col
                  if r.get("_link_color")}
        assert len(colors) == 16
        assert len(set(colors.values())) == 16
        # two different codes never share a color
        assert colors["c00"] != colors["c01"]
        assert colors["c00"] != colors["c15"]


# ── board client grid (row-per-matched-value) ─────────────────────────────────

class TestBoardGrid:
    def _board(self, match_field="project", columns=("expense", "exercise")):
        _write_queries({"b": {"columns": list(columns),
                               "match_field": match_field,
                               "time_window": "all"}})

    def test_grid_rows_built_for_shared_value(self):
        self._board()
        _write_record("2026-07-01", "2026-07-01 type=expense project=alpha amount=1")
        _write_record("2026-07-02", "2026-07-02 type=expense project=alpha amount=2")
        _write_record("2026-07-03", "2026-07-03 type=exercise project=alpha duration=10")
        result = get_board_data("b")
        assert result["has_matching"] is True
        assert len(result["grid_rows"]) == 1
        row = result["grid_rows"][0]
        assert row["value"] == "alpha"
        assert row["color"] == row["cells"]["expense"][0]["_link_color"]
        # stacked in the cell, preserving per-column order (newest first)
        assert [r["amount"] for r in row["cells"]["expense"]] == ["2", "1"]
        assert len(row["cells"]["exercise"]) == 1
        assert row["cells"]["exercise"][0]["duration"] == "10"

    def test_cells_blank_where_no_record(self):
        # Board with 3 columns; alpha is matched across expense+exercise but has
        # no income record (blank income cell); beta is matched in all three.
        _write_queries({"b": {"columns": ["expense", "exercise", "income"],
                              "match_field": "project",
                              "time_window": "all"}})
        _write_record("2026-07-01", "2026-07-01 type=expense project=alpha amount=1")
        _write_record("2026-07-03", "2026-07-03 type=exercise project=alpha duration=10")
        _write_record("2026-07-04", "2026-07-04 type=expense project=beta amount=5")
        _write_record("2026-07-05", "2026-07-05 type=exercise project=beta duration=20")
        _write_record("2026-07-06", "2026-07-06 type=income project=beta source=salary")
        result = get_board_data("b")
        rows = {r["value"]: r for r in result["grid_rows"]}
        assert set(rows) == {"alpha", "beta"}
        # alpha has no income record -> blank income cell
        assert rows["alpha"]["cells"]["income"] == []
        assert len(rows["alpha"]["cells"]["expense"]) == 1
        # beta has all three
        assert len(rows["beta"]["cells"]["income"]) == 1

    def test_lone_value_goes_to_unmatched(self):
        self._board()
        _write_record("2026-07-01", "2026-07-01 type=expense project=lone amount=1")
        _write_record("2026-07-02", "2026-07-02 type=expense amount=9")
        result = get_board_data("b")
        # lone appears only in expense (no sibling) -> no matched row
        assert result["grid_rows"] == []
        assert result["has_matching"] is False
        # both the lone and the missing-value records land in unmatched, per column
        unmatched_exp = result["unmatched"]["expense"]
        assert {r.get("project") for r in unmatched_exp} == {"lone", None}
        unmatched_exp = result["unmatched"]["expense"]
        assert {r.get("project") for r in unmatched_exp} == {"lone", None}

    def test_no_matching_when_no_shared_value(self):
        self._board()
        _write_record("2026-07-01", "2026-07-01 type=expense project=only amount=1")
        result = get_board_data("b")
        assert result["has_matching"] is False
        assert result["grid_rows"] == []
        assert result["unmatched"]["expense"][0]["project"] == "only"

    def test_no_match_field_disables_grid(self):
        _write_queries({"b": {"columns": ["expense"]}})
        _write_record("2026-07-01", "2026-07-01 type=expense project=alpha amount=1")
        result = get_board_data("b")
        assert result["grid_rows"] == []
        assert result["unmatched"] == {}
        assert result["has_matching"] is False

    def test_grid_rows_sorted(self):
        self._board()
        _write_record("2026-07-01", "2026-07-01 type=expense project=zeta amount=1")
        _write_record("2026-07-01", "2026-07-01 type=expense project=alpha amount=2")
        _write_record("2026-07-01", "2026-07-01 type=exercise project=zeta duration=10")
        _write_record("2026-07-01", "2026-07-01 type=exercise project=alpha duration=20")
        result = get_board_data("b")
        assert [r["value"] for r in result["grid_rows"]] == ["alpha", "zeta"]


# ── board route time params ──────────────────────────────────────────────────

class TestSaveQueriesFullBoard:
    def _save(self, boards):
        save_queries_full({}, {}, {}, raw_boards=boards)

    def test_persists_rollup(self):
        self._save({"b": {"columns": ["expense"],
                          "rollup_field": "amount", "rollup_op": "sum"}})
        result = get_board_data("b")
        assert result["rollup_op"] == "sum"
        assert result["rollups"]["expense"] is not None

    def test_omits_rollup_when_field_absent(self):
        self._save({"b": {"columns": ["expense"]}})
        with open(ptos.QUERIES_PATH, "rb") as f:
            import tomllib
            data = tomllib.load(f)
        assert "rollup_field" not in data["board.b"]
        result = get_board_data("b")
        assert result["rollup_op"] == "count"
        assert result["rollups"]["expense"] is None

    def test_default_op_count(self):
        self._save({"b": {"columns": ["expense"],
                          "rollup_field": "amount"}})
        with open(ptos.QUERIES_PATH, "rb") as f:
            import tomllib
            data = tomllib.load(f)
        assert data["board.b"]["rollup_op"] == "count"

    def test_rejects_non_aggregatable_field(self):
        with pytest.raises(PTOSError, match="not aggregatable"):
            self._save({"b": {"columns": ["expense"],
                              "rollup_field": "domain", "rollup_op": "sum"}})

    def test_rejects_field_not_applicable_to_any_column(self):
        with pytest.raises(PTOSError, match="does not apply"):
            self._save({"b": {"columns": ["expense"],
                              "rollup_field": "duration", "rollup_op": "sum"}})

    def test_rejects_empty_columns(self):
        with pytest.raises(PTOSError, match="non-empty columns"):
            self._save({"b": {"columns": []}})

    def test_rejects_invalid_name(self):
        with pytest.raises(PTOSError, match="Invalid name"):
            self._save({"My Board": {"columns": ["expense"]}})

    def test_persists_match_field(self):
        self._save({"b": {"columns": ["expense"], "match_field": "client_code"}})
        with open(ptos.QUERIES_PATH, "rb") as f:
            import tomllib
            data = tomllib.load(f)
        assert data["board.b"]["match_field"] == "client_code"
        result = get_board_data("b")
        assert result["match_field"] == "client_code"

    def test_omits_match_field_when_absent(self):
        self._save({"b": {"columns": ["expense"]}})
        with open(ptos.QUERIES_PATH, "rb") as f:
            import tomllib
            data = tomllib.load(f)
        assert "match_field" not in data["board.b"]

    def test_omits_blank_match_field(self):
        self._save({"b": {"columns": ["expense"], "match_field": "   "}})
        with open(ptos.QUERIES_PATH, "rb") as f:
            import tomllib
            data = tomllib.load(f)
        assert "match_field" not in data["board.b"]


# ── advance_record ────────────────────────────────────────────────────────────

class TestAdvanceRecord:
    def test_copies_shared_fields(self):
        _write_queries({})
        old_line = "2026-07-01 type=expense domain=self category=food amount=50"
        result = advance_record(old_line, 1, "income",
                                target_ctx_fields={"source": "salary"})
        assert result["ok"] is True
        assert result["target_type"] == "income"
        assert "amount=50" in result["new_line"]
        assert "domain" not in result["new_line"]
        assert "category" not in result["new_line"]
        assert result["new_filepath"].endswith(f"{dt.date.today().year}.log")

    def test_target_ctx_fields_override(self):
        _write_queries({})
        old_line = "2026-07-01 type=expense domain=self category=food amount=50"
        result = advance_record(old_line, 1, "income",
                                target_ctx_fields={"source": "salary", "amount": "99"})
        assert result["ok"] is True
        assert "amount=99" in result["new_line"]
        assert "source=salary" in result["new_line"]

    def test_target_type_not_in_schema(self):
        with pytest.raises(PTOSError):
            advance_record("2026-07-01 type=expense", 1, "bogus")

    def test_missing_required_fields(self):
        _write_queries({})
        old_line = "2026-07-01 type=expense domain=self category=food amount=50"
        # income requires "source" which we don't provide
        result = advance_record(old_line, 1, "income")
        assert result["ok"] is True
        assert "source" in result["missing_required"]

    def test_missing_required_does_not_append(self):
        _write_queries({})
        old_line = "2026-07-01 type=expense domain=self category=food amount=50"
        before = set(ptos.get_log_files())
        result = advance_record(old_line, 1, "income")
        assert "source" in result["missing_required"]
        assert "new_filepath" not in result
        assert "new_lineno" not in result
        assert "new_line" not in result
        after = set(ptos.get_log_files())
        assert after == before
        for fname in before:
            with open(os.path.join(ptos.RECORDS_DIR, fname), encoding="utf-8") as f:
                assert "type=income" not in f.read()

    def test_missing_required_returns_draft(self):
        _write_queries({})
        old_line = "2026-07-01 type=expense domain=self category=food amount=50 | shared note"
        result = advance_record(old_line, 1, "income")
        assert "source" in result["missing_required"]
        assert result["target_type"] == "income"
        assert result["draft"] == {"amount": "50"}
        assert result["note"] == "shared note"
        assert "type" not in result["draft"]
        assert "date" not in result["draft"]

    def test_all_required_satisfied_appends(self):
        _write_queries({})
        old_line = "2026-07-01 type=expense domain=self category=food amount=50"
        result = advance_record(old_line, 1, "income",
                                target_ctx_fields={"source": "salary"})
        assert result["ok"] is True
        assert result["missing_required"] == []
        assert "new_filepath" in result
        assert "new_lineno" in result
        with open(result["new_filepath"], encoding="utf-8") as f:
            assert "type=income" in f.read()

    def test_source_record_unchanged(self):
        _write_queries({})
        old_line = "2026-07-01 type=expense domain=self amount=50"
        # Pre-write the source record into the year file
        _write_record("2026-07-01", old_line)
        result = advance_record(old_line, 1, "income",
                                target_ctx_fields={"source": "salary"})
        assert result["ok"] is True
        year_file = result["new_filepath"]
        assert os.path.exists(year_file)
        with open(year_file, encoding="utf-8") as f:
            content = f.read()
        assert old_line in content

    def test_all_missing_required_when_no_shared(self):
        _write_queries({})
        # expense has domain/category/amount, income has source/amount
        # only "amount" is shared — income requires "source"
        old_line = "2026-07-01 type=expense domain=self category=food amount=50"
        result = advance_record(old_line, 1, "income")
        assert result["ok"] is True
        assert "source" in result["missing_required"]

    # ── advance date: always the source record's original date ──────────────

    def test_advance_keeps_source_date(self):
        # The new record always keeps the source record's original date, so an
        # advanced card stays in the period it was dragged from (simple rule).
        _write_queries({})
        old_line = "2026-07-01 type=expense domain=self amount=50"
        result = advance_record(old_line, 1, "income",
                                target_ctx_fields={"source": "salary"})
        assert result["new_line"].startswith("2026-07-01")


# ── board route time params ──────────────────────────────────────────────────

class TestBoardRouteTimeWindow:
    def _get(self, path):
        from ptos_web import app
        client = app.test_client()
        return client.get(path).get_data(as_text=True)

    def test_board_route_uses_shared_time_select_id(self):
        _write_queries({"b": {"columns": ["expense"]}})
        html = self._get("/board?board=b")
        assert 'id="brd-time-select"' in html
        assert 'id="board-time-window"' not in html

    def test_board_route_renders_default_when_no_time(self):
        _write_queries({"b": {"columns": ["expense"]}})
        html = self._get("/board?board=b")
        assert "Default (per board)" in html

    def test_board_route_renders_range_params(self):
        _write_queries({"b": {"columns": ["expense"]}})
        html = self._get("/board?board=b&time=range&from_date=2026-06-01&to_date=2026-06-30")
        assert "Default (per board)" in html
        assert 'value="range"' in html

    def test_board_route_renders_custom_year(self):
        _write_queries({"b": {"columns": ["expense"]}})
        year = str(dt.date.today().year - 1)
        html = self._get(f"/board?board=b&time=year&custom_time={year}")
        assert 'value="year"' in html

    def test_board_route_renders_specific_month(self):
        _write_queries({"b": {"columns": ["expense"]}})
        year, month = dt.date.today().year, str(dt.date.today().month).zfill(2)
        html = self._get(f"/board?board=b&time=month&custom_time={year}-{month}")
        assert '<option value="month" selected' in html
        assert 'id="brd-month-block"' in html


# ── board client-grid view route ─────────────────────────────────────────────

class TestBoardGridView:
    def _get(self, path):
        from ptos_web import app
        client = app.test_client()
        return client.get(path).get_data(as_text=True)

    def _board(self, match_field=True):
        cfg = {"columns": ["expense", "exercise"]}
        if match_field:
            cfg["match_field"] = "project"
        _write_queries({"b": cfg})
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense project=alpha amount=1")
        _write_record(today, f"{today} type=exercise project=alpha duration=10")

    def test_toggle_shown_when_match_field_set(self):
        self._board()
        html = self._get("/board?board=b")
        assert "Client grid" in html
        assert 'switchView(\'grid\')' in html

    def test_toggle_hidden_without_match_field(self):
        self._board(match_field=False)
        html = self._get("/board?board=b")
        assert "Client grid" not in html

    def test_view_grid_renders_grid_markup(self):
        self._board()
        html = self._get("/board?board=b&view=grid")
        assert "bg-table" in html
        assert "Unmatched" in html

    def test_view_grid_persists_board_and_view(self):
        self._board()
        html = self._get("/board?board=b&view=grid")
        assert "switchView('kanban')" in html
        assert "params.set('view', 'grid')" in html
        assert "params.set('board'" in html

    def test_grid_cards_are_draggable(self):
        self._board()
        html = self._get("/board?board=b&view=grid")
        # matched card in a row is draggable with the standard handlers
        assert 'class="board-card hl-' in html
        assert 'draggable="true"' in html
        assert 'ondragstart="onDragStart(event)"' in html
        assert 'ondragend="onDragEnd(event)"' in html

    def test_grid_cells_are_drop_targets(self):
        self._board()
        html = self._get("/board?board=b&view=grid")
        assert 'data-col-type="expense"' in html
        assert 'data-col-type="exercise"' in html
        assert 'ondrop="onDrop(event)"' in html
        assert 'ondragover="onDragOver(event)"' in html

    def test_grid_rows_carry_client_identity(self):
        self._board()
        html = self._get("/board?board=b&view=grid")
        assert 'class="bg-row" data-row="alpha"' in html

    def test_unmatched_cards_draggable_and_lanes_droppable(self):
        # A lone record (single column) goes to Unmatched; its card is draggable
        # and the unmatched lane is a drop target. An alpha matched pair keeps
        # grid_rows non-empty so the Unmatched section renders.
        _write_queries({"b": {"columns": ["expense", "exercise"],
                              "match_field": "project"}})
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense project=lone amount=1")
        _write_record(today, f"{today} type=expense project=alpha amount=2")
        _write_record(today, f"{today} type=exercise project=alpha duration=10")
        html = self._get("/board?board=b&view=grid")
        assert "Unmatched" in html
        assert 'class="bg-unmatched-lane" data-col-type="expense"' in html
        assert 'draggable="true"' in html
        assert 'ondrop="onDrop(event)"' in html

    def test_same_row_drag_guard_present(self):
        self._board()
        html = self._get("/board?board=b&view=grid")
        # the JS enforces matched-drag stays within the same client row
        assert "srcRow" in html
        assert "stay within the same client row" in html
        assert "_sourceType" in html
        assert "_dropType" in html


# ── board_field_overlap endpoint ──────────────────────────────────────────────

class TestBoardFieldOverlapEndpoint:
    def _post(self, types):
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/board/field-overlap",
                           json={"types": types})
        return resp.get_json()

    def test_aggregatable_all_includes_fields_present_on_any_column(self):
        # amount/duration are aggregatable but only present on one of the
        # two types each — so they appear in aggregatable_all (rollup dropdown)
        # but not in aggregatable_overlap (common-only).
        data = self._post(["expense", "exercise"])
        assert data["ok"] is True
        assert "amount" in data["aggregatable_all"]
        assert "duration" in data["aggregatable_all"]
        assert data["aggregatable_overlap"] == []

    def test_aggregatable_overlap_for_shared_aggregatable_field(self):
        data = self._post(["expense", "income"])
        assert "amount" in data["aggregatable_overlap"]
        assert "amount" in data["aggregatable_all"]

    def test_missing_types(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/board/field-overlap", json={})
        data = resp.get_json()
        assert data["ok"] is False


# ── query-builder boards payload ──────────────────────────────────────────────

class TestQueryBuilderBoardsPayload:
    def test_rollup_fields_round_trip(self):
        _write_queries({"b": {"columns": ["expense"],
                              "rollup_field": "amount", "rollup_op": "sum"}})
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/query-builder")
        html = resp.get_data(as_text=True)
        m = re.search(r"var _bkBoards = (.*?);", html, re.S)
        assert m, "boards JSON not found in rendered page"
        boards = json.loads(m.group(1))
        assert "b" in boards
        assert boards["b"]["rollup_field"] == "amount"
        assert boards["b"]["rollup_op"] == "sum"

    def test_no_rollup_defaults(self):
        _write_queries({"b": {"columns": ["expense"]}})
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/query-builder")
        html = resp.get_data(as_text=True)
        m = re.search(r"var _bkBoards = (.*?);", html, re.S)
        boards = json.loads(m.group(1))
        assert boards["b"]["rollup_field"] == ""
        assert boards["b"]["rollup_op"] == "count"


# ── Status boards (set_field + filter lanes) ──────────────────────────────────

class TestStatusBoardLanes:
    def _cfg(self, columns=None, **kw):
        cfg = {
            "columns": columns or [
                {"label": "Food", "where": "type=expense AND category=food"},
                {"label": "Transport", "where": "type=expense AND category=transport"},
            ],
            "set_field": "category",
            "time_window": "all",
        }
        cfg.update(kw)
        return cfg

    def test_board_loads_lanes_and_set_values(self):
        _write_queries({"status": self._cfg()})
        data = get_board_data("status")
        assert data["set_field"] == "category"
        assert data["columns"] == ["Food", "Transport"]
        assert data["lanes"]["Food"]["set_value"] == "food"
        assert data["lanes"]["Food"]["kind"] == "filter"
        assert data["lanes"]["Transport"]["set_value"] == "transport"
        assert data["lanes"]["Transport"]["types"] == ["expense"]

    def test_records_bucket_into_lanes(self):
        _write_queries({"status": self._cfg()})
        today = dt.date.today().isoformat()
        _write_record(today, f"{today} type=expense domain=self category=food amount=10")
        _write_record(today, f"{today} type=expense domain=self category=transport amount=20")
        data = get_board_data("status")
        assert {r["category"] for r in data["data"]["Food"]} == {"food"}
        assert {r["category"] for r in data["data"]["Transport"]} == {"transport"}

    def test_bare_type_lane_in_status_board_rejected(self):
        _write_queries({"status": {"columns": ["expense", {"label": "Food", "where": "category=food"}],
                                   "set_field": "category"}})
        with pytest.raises(PTOSError):
            get_board_data("status")

    def test_dict_lane_without_set_field_rejected(self):
        _write_queries({"status": {"columns": [{"label": "Food", "where": "category=food"}]}})
        with pytest.raises(PTOSError):
            get_board_data("status")

    def test_non_dict_column_rejected(self):
        _write_queries({"status": {"columns": [42], "set_field": "category"}})
        with pytest.raises(PTOSError):
            get_board_data("status")

    def test_missing_label_rejected(self):
        _write_queries({"status": {"columns": [{"where": "category=food"}], "set_field": "category"}})
        with pytest.raises(PTOSError):
            get_board_data("status")

    def test_missing_where_rejected(self):
        _write_queries({"status": {"columns": [{"label": "Food"}], "set_field": "category"}})
        with pytest.raises(PTOSError):
            get_board_data("status")

    def test_ambiguous_lane_has_no_set_value(self):
        _write_queries({"status": {"columns": [{"label": "Either", "where": "category=food|transport"}],
                                   "set_field": "category"}})
        data = get_board_data("status")
        assert data["lanes"]["Either"]["set_value"] is None

    def test_explicit_set_overrides_derived(self):
        _write_queries({"status": {"columns": [{"label": "Either", "where": "category=food|transport", "set": "food"}],
                                   "set_field": "category"}})
        data = get_board_data("status")
        assert data["lanes"]["Either"]["set_value"] == "food"

    def test_duplicate_lane_labels_rejected(self):
        _write_queries({"status": {"columns": [
            {"label": "Food", "where": "category=food"},
            {"label": "Food", "where": "category=transport"},
        ], "set_field": "category"}})
        with pytest.raises(PTOSError):
            get_board_data("status")


class TestBoardMoveRecord:
    def _setup(self, columns=None):
        _write_queries({"status": {
            "columns": columns or [
                {"label": "Food", "where": "type=expense AND category=food"},
                {"label": "Transport", "where": "type=expense AND category=transport"},
            ],
            "set_field": "category",
            "time_window": "all",
        }})
        today = dt.date.today().isoformat()
        line = f"{today} type=expense domain=self category=food amount=10"
        filepath, lineno = ptos.append_record(line, return_position=True)
        return filepath, line, lineno

    def test_move_rewrites_status_in_place(self):
        filepath, line, lineno = self._setup()
        res = board_move_record("status", filepath, line, lineno, "Transport")
        assert "category=transport" in res["new_line"]
        data = get_board_data("status")
        assert len(data["data"]["Food"]) == 0
        assert len(data["data"]["Transport"]) == 1

    def test_move_to_same_value_is_error(self):
        filepath, line, lineno = self._setup()
        with pytest.raises(PTOSError):
            board_move_record("status", filepath, line, lineno, "Food")

    def test_unknown_lane_rejected(self):
        filepath, line, lineno = self._setup()
        with pytest.raises(PTOSError):
            board_move_record("status", filepath, line, lineno, "Nope")

    def test_non_status_board_rejected(self):
        _write_queries({"typeboard": {"columns": ["expense"]}})
        today = dt.date.today().isoformat()
        line = f"{today} type=expense domain=self category=food amount=10"
        filepath, lineno = ptos.append_record(line, return_position=True)
        with pytest.raises(PTOSError):
            board_move_record("typeboard", filepath, line, lineno, "expense")

    def test_unresolvable_lane_rejected(self):
        filepath, line, lineno = self._setup(columns=[{"label": "Either", "where": "category=food|transport"}])
        with pytest.raises(PTOSError):
            board_move_record("status", filepath, line, lineno, "Either")

    def test_path_escape_rejected(self):
        filepath, line, lineno = self._setup()
        import tempfile
        other = os.path.join(tempfile.gettempdir(), "outside.log")
        with pytest.raises(PTOSError):
            board_move_record("status", other, line, lineno, "Transport")


class TestBoardMoveStampField:
    def _setup(self, stamp_field=None):
        cfg = {
            "status": {
                "columns": [
                    {"label": "Food", "where": "type=expense AND category=food"},
                    {"label": "Transport", "where": "type=expense AND category=transport"},
                ],
                "set_field": "category",
                "time_window": "all",
            }
        }
        if stamp_field:
            cfg["status"]["stamp_field"] = stamp_field
        _write_queries(cfg)
        today = dt.date.today().isoformat()
        line = f"{today} type=expense domain=self category=food amount=10"
        filepath, lineno = ptos.append_record(line, return_position=True)
        return filepath, line, lineno

    def test_move_writes_set_and_stamp_in_one_line(self):
        filepath, line, lineno = self._setup("status_changed")
        res = board_move_record("status", filepath, line, lineno, "Transport")
        nl = res["new_line"]
        assert "category=transport" in nl
        assert f"status_changed={dt.date.today().isoformat()}" in nl
        with open(filepath, encoding="utf-8") as f:
            txt = f.read()
        assert "category=transport" in txt
        assert f"status_changed={dt.date.today().isoformat()}" in txt

    def test_no_stamp_field_single_write(self):
        filepath, line, lineno = self._setup()
        res = board_move_record("status", filepath, line, lineno, "Transport")
        assert "category=transport" in res["new_line"]
        assert "status_changed" not in res["new_line"]

    def test_move_record_default_no_stamp(self):
        filepath, line, lineno = self._setup()
        res = move_record(filepath, line, "category", "transport", lineno=lineno)
        assert "category=transport" in res["new_line"]
        assert "status_changed" not in res["new_line"]

    def test_move_record_with_stamp_kwargs(self):
        filepath, line, lineno = self._setup()
        res = move_record(filepath, line, "category", "transport", lineno=lineno,
                          stamp_field="status_changed", stamp_value="2026-09-01")
        assert "category=transport" in res["new_line"]
        assert "status_changed=2026-09-01" in res["new_line"]

    def test_same_status_rejects_only_when_nothing_changes(self):
        filepath, line, lineno = self._setup("status_changed")
        res = board_move_record("status", filepath, line, lineno, "Food")
        # status is already food but the stamp is new → re-stamps, not an error
        assert "status_changed=" in res["new_line"]
        with pytest.raises(PTOSError):
            board_move_record("status", filepath, line, lineno, "Food")

    def test_save_board_persists_stamp_field(self):
        _write_queries({})
        save_board("status", {
            "columns": [{"label": "Food", "where": "category=food"}],
            "set_field": "category",
            "stamp_field": "status_changed",
        })
        import tomllib
        with open(ptos.QUERIES_PATH, "rb") as f:
            entry = tomllib.load(f)["board.status"]
        assert entry["stamp_field"] == "status_changed"


class TestSaveStatusBoard:
    def test_save_queries_full_round_trips_dict_lanes_and_set_field(self):
        _write_queries({})
        save_queries_full({}, {}, {}, raw_boards={"status": {
            "columns": [
                {"label": "Food", "where": "type=expense AND category=food"},
                {"label": "Transport", "where": "type=expense AND category=transport"},
            ],
            "set_field": "category",
            "time_window": "all",
        }})
        import tomllib
        with open(ptos.QUERIES_PATH, "rb") as f:
            entry = tomllib.load(f)["board.status"]
        assert entry["set_field"] == "category"
        assert entry["columns"][0]["label"] == "Food"
        assert entry["columns"][0]["where"] == "type=expense AND category=food"
        assert "set" not in entry["columns"][0]

    def test_save_board_persists_set_field_and_lanes(self):
        _write_queries({})
        save_board("status", {
            "columns": [{"label": "Food", "where": "category=food"}],
            "set_field": "category",
        })
        import tomllib
        with open(ptos.QUERIES_PATH, "rb") as f:
            entry = tomllib.load(f)["board.status"]
        assert entry["set_field"] == "category"
        assert entry["columns"] == [{"label": "Food", "where": "category=food"}]

    def test_save_board_rejects_bare_string_when_set_field(self):
        _write_queries({})
        with pytest.raises(PTOSError):
            save_board("status", {"columns": ["expense"], "set_field": "category"})

    def test_save_board_rejects_dict_lane_without_set_field(self):
        _write_queries({})
        with pytest.raises(PTOSError):
            save_board("status", {"columns": [{"label": "Food", "where": "category=food"}]})

    def test_save_queries_full_rejects_mixed_modes(self):
        _write_queries({})
        with pytest.raises(PTOSError):
            save_queries_full({}, {}, {}, raw_boards={"status": {
                "columns": ["expense", {"label": "Food", "where": "category=food"}],
                "set_field": "category",
            }})


class TestBoardMoveRoute:
    def test_move_via_route(self):
        _write_queries({"status": {
            "columns": [
                {"label": "Food", "where": "type=expense AND category=food"},
                {"label": "Transport", "where": "type=expense AND category=transport"},
            ],
            "set_field": "category",
            "time_window": "all",
        }})
        today = dt.date.today().isoformat()
        filepath, lineno = ptos.append_record(
            f"{today} type=expense domain=self category=food amount=10", return_position=True)
        with open(filepath, encoding="utf-8") as f:
            lines = f.read().splitlines()
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/board/move", json={
            "board": "status", "filepath": filepath, "line": lines[lineno],
            "lineno": lineno, "target_lane": "Transport"})
        data = resp.get_json()
        assert data["ok"] is True
        got = get_board_data("status")
        assert len(got["data"]["Transport"]) == 1
        assert len(got["data"]["Food"]) == 0

    def test_move_route_missing_fields(self):
        _write_queries({"status": {"columns": [{"label": "Food", "where": "category=food"}],
                                   "set_field": "category"}})
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/board/move", json={})
        assert resp.get_json()["ok"] is False

    def test_query_builder_payload_includes_set_field(self):
        _write_queries({"status": {
            "columns": [{"label": "Food", "where": "category=food"}],
            "set_field": "category",
        }})
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/query-builder")
        html = resp.get_data(as_text=True)
        m = re.search(r"var _bkBoards = (.*?);", html, re.S)
        boards = json.loads(m.group(1))
        assert boards["status"]["set_field"] == "category"
        assert boards["status"]["columns"][0]["label"] == "Food"
