import os
import pytest
import ptos
import ptos_cli
import ptos_service as svc


def _write_record(line):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    path = os.path.join(ptos.RECORDS_DIR, f"{line[:4]}.log")
    with open(path, "w", encoding="utf-8") as f:
        f.write(line + "\n")


class TestJournalPath:
    def test_creates_file_for_date(self):
        path = ptos.get_journal_path("2026-07-15")
        assert os.path.isfile(path)
        assert path == os.path.join(ptos.JOURNAL_DIR, "2026", "07", "2026-07-15.md")

    def test_reuses_existing_file(self):
        first = ptos.get_journal_path("2026-07-15")
        second = ptos.get_journal_path("2026-07-15")
        assert first == second

    def test_uses_template(self):
        path = ptos.get_journal_path("2026-07-15")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "2026-07-15" in content

    def test_today_journal_delegates(self):
        today_str = ptos.today().isoformat()
        assert ptos.get_today_journal() == ptos.get_journal_path(today_str)


class FakeDashboardArgs:
    def __init__(self, name, metrics, highlight=None):
        self.add_dashboard = name
        self.metrics = metrics
        self.highlight = highlight


def _norm_query(q):
    """save_queries_full normalises a single group string to a one-item list."""
    if not isinstance(q, dict):
        return q
    q = dict(q)
    if isinstance(q.get("group"), str):
        q["group"] = [q["group"]]
    return q


class TestAddDashboard:
    def test_adds_dashboard(self, capsys):
        ptos_cli._handle_add_dashboard(FakeDashboardArgs("overview", ["total_income", "total_expenses"]))
        assert "overview" in capsys.readouterr().out
        q = ptos.get_queries()
        assert "overview" in q["dashboards"]
        assert q["dashboards"]["overview"]["metrics"] == ["total_income", "total_expenses"]

    def test_empty_metrics_allowed(self, capsys):
        ptos_cli._handle_add_dashboard(FakeDashboardArgs("empty", []))
        q = ptos.get_queries()
        assert q["dashboards"]["empty"] == {}

    def test_preserves_existing_state(self, capsys):
        before = ptos.get_queries()
        ptos_cli._handle_add_dashboard(FakeDashboardArgs("overview", ["total_income"]))
        after = ptos.get_queries()
        for k, v in before.items():
            if k == "dashboards":
                continue
            # starter stores [board.patient_journey] nested under "board";
            # the handler normalises it to flat "board.patient_journey"
            if k == "board" and isinstance(v, dict):
                for sub_name, sub in v.items():
                    assert f"board.{sub_name}" in after
                    assert _norm_query(after[f"board.{sub_name}"]) == _norm_query(sub)
                continue
            assert k in after, k
            assert _norm_query(after[k]) == _norm_query(v), k
        for name, db in before.get("dashboards", {}).items():
            assert after["dashboards"][name] == db

    def test_preserves_config_keys(self, capsys):
        ptos_cli._handle_add_dashboard(FakeDashboardArgs("overview", ["total_income"]))
        q = ptos.get_queries()
        assert "board.patient_journey" in q
        assert "habit.meditation" in q
        assert "habit.walk" in q

    def test_duplicate_dashboard_exits(self, capsys):
        ptos_cli._handle_add_dashboard(FakeDashboardArgs("dup", ["total_income"]))
        with pytest.raises(SystemExit):
            ptos_cli._handle_add_dashboard(FakeDashboardArgs("dup", ["avg_mood"]))

    def test_missing_metric_warns(self, capsys):
        ptos_cli._handle_add_dashboard(FakeDashboardArgs("warn", ["does_not_exist"]))
        assert "does_not_exist" in capsys.readouterr().out

    def test_invalid_name_raises(self, capsys):
        with pytest.raises(SystemExit):
            ptos_cli._handle_add_dashboard(FakeDashboardArgs("Bad Name", ["total_income"]))


class TestInteractiveSuggest:
    def test_returns_history_defaults(self):
        _write_record("2026-01-01 type=expense domain=work category=supplies amount=10")
        defaults = ptos_cli._interactive_suggest("expense", {})
        assert defaults["domain"] == "work"
        assert defaults["category"] == "supplies"

    def test_merges_free_text_values(self):
        _write_record("2026-01-01 type=expense vendor=acme amount=10")
        _write_record("2026-01-02 type=expense vendor=acme amount=20")
        defaults = ptos_cli._interactive_suggest("expense", {})
        assert defaults["vendor"] == "acme"

    def test_returns_empty_on_unknown_type(self):
        assert ptos_cli._interactive_suggest("nope", {}) == {}