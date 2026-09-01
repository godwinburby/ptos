import pytest
import os
import datetime as dt
import ptos
import ptos_service as svc


def _d(day):
    return dt.date.today().replace(day=day).isoformat()


def _write_queries(content):
    os.makedirs(os.path.dirname(ptos.QUERIES_PATH), exist_ok=True)
    with open(ptos.QUERIES_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    ptos._invalidate("queries")


def _write_schema():
    os.makedirs(os.path.dirname(ptos.SCHEMA_PATH), exist_ok=True)
    with open(ptos.SCHEMA_PATH, "w", encoding="utf-8") as f:
        f.write(
            '[types]\n'
            'allowed = ["expense", "income"]\n'
            '\n'
            '[type.expense]\n'
            'required = ["domain", "category", "amount"]\n'
            '\n'
            '[type.expense.fields.domain]\n'
            'options = ["self", "work"]\n'
            '\n'
            '[type.expense.fields.category]\n'
            'options = ["food", "transport"]\n'
            '\n'
            '[type.expense.fields.amount]\n'
            'type = "int"\n'
            '\n'
            '[type.income]\n'
            'required = ["source", "amount"]\n'
            '\n'
            '[type.income.fields.source]\n'
            'options = ["salary", "freelance"]\n'
            '\n'
            '[type.income.fields.amount]\n'
            'type = "int"\n'
        )
    ptos._invalidate("schema")


def _write_records(lines):
    records_path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
    os.makedirs(os.path.dirname(records_path), exist_ok=True)
    with open(records_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n" if lines else "")
    ptos._invalidate("records")


EXPENSE_THRESHOLD = (
    '[food_q]\n'
    'where = "type=expense AND category=food"\n'
    'time = "this-month"\n'
    'sum = true\n'
    '\n'
    '["threshold.food_spend"]\n'
    'metric = "food_q"\n'
    'agg = "sum"\n'
    'sum_field = "amount"\n'
    'value = 5000\n'
    'direction = "max"\n'
    'time = "this-month"\n'
)

INCOME_THRESHOLD = (
    '[income_q]\n'
    'where = "type=income"\n'
    'time = "this-month"\n'
    'sum = true\n'
    '\n'
    '["threshold.income_target"]\n'
    'metric = "income_q"\n'
    'agg = "sum"\n'
    'sum_field = "amount"\n'
    'value = 10000\n'
    'direction = "min"\n'
    'time = "this-month"\n'
)


class TestGetThresholds:
    def test_reads_threshold_sections(self):
        _write_queries(EXPENSE_THRESHOLD)
        thr = ptos.get_thresholds()
        assert "food_spend" in thr
        assert thr["food_spend"]["metric"] == "food_q"
        assert thr["food_spend"]["value"] == 5000

    def test_empty_when_no_thresholds(self):
        _write_queries('[some_query]\nwhere = "type=expense"\n')
        assert ptos.get_thresholds() == {}


class TestResolveValue:
    def test_resolves_metric(self):
        _write_schema()
        _write_queries(
            '[food_q]\n'
            'where = "type=expense AND category=food"\n'
            'time = "this-month"\n'
            'sum = true\n'
            '\n'
            '[metrics.food_total]\n'
            'sum = "food_q"\n'
            'field = "amount"\n'
        )
        _write_records([
            f"{_d(1)} type=expense domain=self category=food amount=200",
            f"{_d(2)} type=expense domain=self category=food amount=300",
        ])
        val = svc._resolve_value("food_total", {}, "this-month")
        assert val == 500

    def test_resolves_plain_query_count(self):
        _write_queries(
            '[food_q]\n'
            'where = "type=expense AND category=food"\n'
            'time = "this-month"\n'
        )
        _write_records([
            f"{_d(1)} type=expense domain=self category=food amount=100",
            f"{_d(2)} type=expense domain=self category=food amount=200",
        ])
        val = svc._resolve_value("food_q", {"agg": "count"}, "this-month")
        assert val == 2

    def test_resolves_plain_query_sum(self):
        _write_queries(
            '[food_q]\n'
            'where = "type=expense AND category=food"\n'
            'time = "this-month"\n'
            'sum = true\n'
        )
        _write_records([
            f"{_d(1)} type=expense domain=self category=food amount=100",
            f"{_d(2)} type=expense domain=self category=food amount=200",
        ])
        val = svc._resolve_value("food_q", {"agg": "sum", "sum_field": "amount"}, "this-month")
        assert val == 300

    def test_raises_on_unknown_ref(self):
        _write_queries("")
        with pytest.raises(Exception, match="not a known metric or query"):
            svc._resolve_value("nonexistent", {}, "this-month")


class TestGetThresholdStatus:
    def test_max_direction_ok(self):
        _write_queries(EXPENSE_THRESHOLD)
        _write_records([f"{_d(1)} type=expense domain=self category=food amount=2000"])
        status = svc.get_threshold_status("food_spend")
        assert status["name"] == "food_spend"
        assert status["raw"] == 2000
        assert status["target"] == 5000
        assert status["direction"] == "max"
        assert status["status"] == "ok"
        assert status["pct"] == pytest.approx(40.0)

    def test_max_direction_warning(self):
        _write_queries(EXPENSE_THRESHOLD)
        _write_records([f"{_d(1)} type=expense domain=self category=food amount=4200"])
        status = svc.get_threshold_status("food_spend")
        assert status["status"] == "warning"
        assert status["pct"] == pytest.approx(84.0)

    def test_max_direction_over(self):
        _write_queries(EXPENSE_THRESHOLD)
        _write_records([f"{_d(1)} type=expense domain=self category=food amount=5500"])
        status = svc.get_threshold_status("food_spend")
        assert status["status"] == "over"
        assert status["pct"] == pytest.approx(110.0)

    def test_min_direction_met(self):
        _write_queries(INCOME_THRESHOLD)
        _write_records([f"{_d(1)} type=income source=salary amount=12000"])
        status = svc.get_threshold_status("income_target")
        assert status["status"] == "met"
        assert status["pct"] == pytest.approx(120.0)

    def test_min_direction_warning_below_50(self):
        _write_queries(INCOME_THRESHOLD)
        _write_records([f"{_d(1)} type=income source=salary amount=3000"])
        status = svc.get_threshold_status("income_target")
        assert status["status"] == "warning"
        assert status["pct"] == pytest.approx(30.0)

    def test_min_direction_ok_above_50(self):
        _write_queries(INCOME_THRESHOLD)
        _write_records([f"{_d(1)} type=income source=salary amount=7000"])
        status = svc.get_threshold_status("income_target")
        assert status["status"] == "ok"
        assert status["pct"] == pytest.approx(70.0)

    def test_missing_threshold_raises(self):
        _write_queries("")
        with pytest.raises(Exception, match="not found"):
            svc.get_threshold_status("nonexistent")

    def test_no_data_returns_zero(self):
        _write_queries(EXPENSE_THRESHOLD)
        _write_records([])
        status = svc.get_threshold_status("food_spend")
        assert status["raw"] == 0
        assert status["pct"] == 0.0
        assert status["status"] == "ok"

    def test_target_as_metric_ref(self):
        _write_queries(
            '[income_q]\n'
            'where = "type=income"\n'
            'time = "this-month"\n'
            'sum = true\n'
            '\n'
            '[income_target_q]\n'
            'where = "type=income AND source=salary"\n'
            'time = "this-month"\n'
            'sum = true\n'
            '\n'
            '["threshold.income_vs_last"]\n'
            'metric = "income_q"\n'
            'agg = "sum"\n'
            'sum_field = "amount"\n'
            'value = "income_target_q"\n'
            'direction = "min"\n'
            'time = "this-month"\n'
        )
        _write_records([
            f"{_d(1)} type=income source=salary amount=8000",
            f"{_d(2)} type=income source=freelance amount=2000",
        ])
        status = svc.get_threshold_status("income_vs_last")
        assert status["raw"] == 10000
        assert status["target"] == 8000
        assert status["status"] == "met"


class TestGetAllThresholdStatus:
    def test_returns_all(self):
        _write_queries(
            EXPENSE_THRESHOLD +
            '\n'
            '["threshold.food_count"]\n'
            'metric = "food_q"\n'
            'agg = "count"\n'
            'value = 10\n'
            'direction = "max"\n'
            'time = "this-month"\n'
        )
        _write_records([f"{_d(1)} type=expense domain=self category=food amount=100"])
        results = svc.get_all_threshold_status()
        names = {r["name"] for r in results}
        assert "food_spend" in names
        assert "food_count" in names
        assert len(results) == 2

    def test_empty_when_no_thresholds(self):
        _write_queries("")
        assert svc.get_all_threshold_status() == []


class TestGetMatchingThresholds:
    def test_matches_record(self):
        _write_queries(EXPENSE_THRESHOLD)
        _write_records([])
        record = {"type": "expense", "category": "food", "amount": "100"}
        matches = svc.get_matching_thresholds(record)
        names = [m["name"] for m in matches]
        assert "food_spend" in names

    def test_no_match_wrong_type(self):
        _write_queries(EXPENSE_THRESHOLD)
        _write_records([])
        record = {"type": "income", "source": "salary", "amount": "5000"}
        matches = svc.get_matching_thresholds(record)
        assert len(matches) == 0

    def test_empty_record_matches_nothing(self):
        _write_queries(EXPENSE_THRESHOLD)
        _write_records([])
        matches = svc.get_matching_thresholds({})
        assert len(matches) == 0


class TestSaveQueriesFullThresholds:
    def test_round_trip(self):
        _write_queries("")
        thr = {
            "food_spend": {
                "metric": "food_q",
                "agg": "sum",
                "sum_field": "amount",
                "value": 5000,
                "direction": "max",
                "time": "this-month",
                "unit": "",
            }
        }
        svc.save_queries_full({}, {}, {}, raw_thresholds=thr)
        result = ptos.get_thresholds()
        assert "food_spend" in result
        assert result["food_spend"]["metric"] == "food_q"
        assert result["food_spend"]["value"] == 5000

    def test_empty_metric_raises(self):
        _write_queries("")
        thr = {"bad": {"metric": "", "direction": "max"}}
        with pytest.raises(Exception, match="must have a metric"):
            svc.save_queries_full({}, {}, {}, raw_thresholds=thr)

    def test_preserves_queries_and_metrics(self):
        _write_queries(
            '[food_q]\n'
            'where = "type=expense"\n'
            'time = "this-month"\n'
            '\n'
            '[metrics.food_total]\n'
            'sum = "food_q"\n'
            '\n'
            '["threshold.food_spend"]\n'
            'metric = "food_q"\n'
            'agg = "sum"\n'
            'sum_field = "amount"\n'
            'value = 5000\n'
            'direction = "max"\n'
            'time = "this-month"\n'
        )
        q = ptos.get_queries()
        assert "threshold.food_spend" in q
        assert "food_q" in q
        assert "metrics" in q
        assert "food_total" in q["metrics"]
        thr = {"food_spend": {"metric": "food_q", "direction": "max", "value": 5000}}
        svc.save_queries_full(
            {"food_q": {"where": "type=expense", "time": "this-month", "sum": True}},
            {"food_total": {"kind": "sum", "base": "food_q"}},
            {},
            raw_thresholds=thr,
        )
        q2 = ptos.get_queries()
        assert "food_q" in q2
        assert "metrics" in q2
        assert "food_total" in q2["metrics"]
        assert "threshold.food_spend" in q2
