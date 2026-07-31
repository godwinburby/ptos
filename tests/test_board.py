import pytest
import datetime as dt
import os
import tomli_w
import ptos
from ptos_service import get_board_data, advance_record, save_queries_full, PTOSError


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
        _write_record(dt.date.today().replace(day=1).isoformat(),
                      f"{dt.date.today().replace(day=1).isoformat()} type=expense amount=2")
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


# ── save_queries_full board persistence ───────────────────────────────────────

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


# ── update_board_time_window ──────────────────────────────────────────────────

class TestUpdateBoardTimeWindow:
    def test_updates_time_window(self):
        _write_queries({"b": {"columns": ["expense"], "time_window": "tm"}})
        from ptos_service import update_board_time_window
        result = update_board_time_window("b", "ly")
        assert result["ok"] is True
        assert result["time_window"] == "ly"
        got = get_board_data("b")
        assert got["time_window"] == "ly"

    def test_unknown_board(self):
        _write_queries({})
        from ptos_service import update_board_time_window
        with pytest.raises(PTOSError):
            update_board_time_window("nonexistent", "ly")

    def test_invalid_time_window(self):
        _write_queries({"b": {"columns": ["expense"], "time_window": "tm"}})
        from ptos_service import update_board_time_window
        with pytest.raises(PTOSError):
            update_board_time_window("b", "bogus-window")
