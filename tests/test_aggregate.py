import ptos


class TestGroupResults:
    def test_group_by_single_field(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        results = [
            "2026-01-15 type=expense amount=50",
            "2026-01-16 type=expense amount=30",
            "2026-01-17 type=income amount=100",
        ]
        counts, sums, has_amount = ptos.group_results(results, ["type"])
        assert counts == {("expense",): 2, ("income",): 1}
        assert sums == {("expense",): 80, ("income",): 100}
        assert has_amount is True

    def test_group_without_amount(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        results = [
            "2026-01-15 type=expense",
            "2026-01-16 type=expense",
        ]
        counts, sums, has_amount = ptos.group_results(results, ["type"])
        assert counts == {("expense",): 2}
        assert sums == {}
        assert has_amount is False

    def test_group_by_day(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        results = [
            "2026-01-15 type=expense amount=50",
            "2026-01-16 type=expense amount=30",
        ]
        counts, sums, has_amount = ptos.group_results(results, ["day"])
        assert counts == {("2026-01-15",): 1, ("2026-01-16",): 1}
        assert sums == {("2026-01-15",): 50, ("2026-01-16",): 30}

    def test_group_by_month(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        results = [
            "2026-01-15 type=expense amount=50",
            "2026-02-10 type=expense amount=30",
        ]
        counts, sums, has_amount = ptos.group_results(results, ["month"])
        assert counts == {("2026-01",): 1, ("2026-02",): 1}
        assert sums == {("2026-01",): 50, ("2026-02",): 30}

    def test_group_by_year(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        results = [
            "2025-12-31 type=expense amount=50",
            "2026-01-01 type=expense amount=30",
        ]
        counts, sums, has_amount = ptos.group_results(results, ["year"])
        assert counts == {("2025",): 1, ("2026",): 1}

    def test_group_with_sum_field(self):
        results = [
            "2026-01-15 type=expense amount=50 duration=30",
            "2026-01-16 type=expense amount=30 duration=20",
        ]
        counts, sums, has_amount = ptos.group_results(results, ["type"], sum_field="duration")
        assert counts == {("expense",): 2}
        assert sums == {("expense",): 50}
        assert has_amount is True

    def test_group_missing_field(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        results = ["2026-01-15 type=expense amount=50"]
        counts, sums, has_amount = ptos.group_results(results, ["category"])
        assert counts == {("-",): 1}

    def test_empty_results(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        counts, sums, has_amount = ptos.group_results([], ["type"])
        assert counts == {}
        assert sums == {}
        assert has_amount is False


class TestPivotResults:
    def test_pivot_basic(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        results = [
            "2026-01-15 type=expense domain=work amount=50",
            "2026-01-16 type=expense domain=home amount=30",
            "2026-01-17 type=income domain=work amount=100",
        ]
        table, cols, rows = ptos.pivot_results(results, "domain", "type")
        assert set(cols) == {"expense", "income"}
        assert table["work"] == {"expense": 50, "income": 100}
        assert table["home"] == {"expense": 30}

    def test_pivot_count_mode(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        results = [
            "2026-01-15 type=expense domain=work amount=50",
            "2026-01-16 type=expense domain=work amount=30",
            "2026-01-17 type=income domain=work amount=100",
        ]
        table, cols, rows = ptos.pivot_results(results, "domain", "type", count_mode=True)
        assert table["work"] == {"expense": 2, "income": 1}

    def test_pivot_with_sort_col(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        results = [
            "2026-01-15 type=expense domain=work amount=50",
            "2026-01-16 type=income domain=work amount=200",
            "2026-01-17 type=expense domain=home amount=30",
        ]
        table, cols, rows = ptos.pivot_results(results, "domain", "type", sort_col="income")
        assert rows[0] == "work"

    def test_pivot_empty_results(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        table, cols, rows = ptos.pivot_results([], "domain", "type")
        assert table == {}
        assert cols == []
        assert rows == []

    def test_pivot_with_sum_field(self):
        results = [
            "2026-01-15 type=expense domain=work amount=50 duration=30",
            "2026-01-16 type=expense domain=work amount=30 duration=20",
        ]
        table, cols, rows = ptos.pivot_results(results, "domain", "type", sum_field="duration")
        assert table["work"] == {"expense": 50}

    def test_pivot_multi_value_row(self, monkeypatch):
        monkeypatch.setattr(ptos, "numeric_fields", lambda: ["amount"])
        results = ["2026-01-15 type=expense tag=food tag=transport amount=50"]
        table, cols, rows = ptos.pivot_results(results, "tag", "type")
        assert set(table.keys()) == {"food", "transport"}
