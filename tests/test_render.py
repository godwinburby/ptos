import ptos


class TestRenderGroup:
    def test_with_amount(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "currency", lambda: "₹")
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        counts = {("expense",): 2, ("income",): 1}
        sums = {("expense",): 80, ("income",): 100}
        ptos.render_group(counts, sums, True, ["type"])
        out = capsys.readouterr().out
        assert "expense" in out
        assert "income" in out
        assert "Total" in out

    def test_without_amount(self, capsys):
        counts = {("expense",): 2}
        ptos.render_group(counts, {}, False, ["type"])
        out = capsys.readouterr().out
        assert "expense" in out
        assert "Total" in out

    def test_multi_key(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "currency", lambda: "₹")
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        counts = {("work", "food"): 3, ("home", "grocery"): 2}
        sums = {("work", "food"): 150, ("home", "grocery"): 80}
        ptos.render_group(counts, sums, True, ["domain", "category"])
        out = capsys.readouterr().out
        assert "work" in out
        assert "food" in out
        assert "home" in out

    def test_empty_counts(self, capsys):
        ptos.render_group({}, {}, False, ["type"])
        out = capsys.readouterr().out
        assert "Total" in out


class TestRenderPivot:
    def test_basic_pivot(self, capsys):
        table = {"work": {"expense": 50, "income": 100}, "home": {"expense": 30}}
        cols = ["expense", "income"]
        rows = ["work", "home"]
        ptos.render_pivot(table, cols, rows, "domain")
        out = capsys.readouterr().out
        assert "work" in out
        assert "home" in out
        assert "expense" in out
        assert "income" in out
        assert "Total" in out

    def test_single_row(self, capsys):
        table = {"work": {"expense": 50}}
        cols = ["expense"]
        rows = ["work"]
        ptos.render_pivot(table, cols, rows, "domain")
        out = capsys.readouterr().out
        assert "work" in out
        assert "Total" in out


class TestRenderSummary:
    def test_basic_summary(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "currency", lambda: "₹")
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        results = ["2026-01-15 type=expense amount=50",
                   "2026-01-16 type=expense amount=30"]
        ptos.render_summary(results, "2026-01-01", "2026-01-31", "this-month",
                           ["type=expense"], 80)
        out = capsys.readouterr().out
        assert "Time range" in out
        assert "Data span" in out
        assert "Records" in out
        assert "Filters" in out
        assert "Total" in out

    def test_no_filters_no_total(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "currency", lambda: "")
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        ptos.render_summary([], "2026-01-01", "2026-01-31", "this-month", [], 0)
        out = capsys.readouterr().out
        assert "Time range" in out
        assert "Records" in out
        assert "Filters" not in out
        assert "Total" not in out

    def test_with_sum_field(self, capsys, monkeypatch):
        monkeypatch.setattr(ptos, "currency", lambda: "₹")
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        results = ["2026-01-15 type=expense duration=30"]
        ptos.render_summary(results, "2026-01-01", "2026-01-31", "this-month",
                           [], 30, sum_field="duration")
        out = capsys.readouterr().out
        assert "Total (duration)" in out
        assert "Average (duration)" in out


class TestPrintDoctorResults:
    def test_all_ok(self, capsys):
        ptos.print_doctor_results([], [], [("config/", "Folder exists")], [])
        out = capsys.readouterr().out
        assert "PTOS Doctor" in out
        assert "All checks passed!" in out

    def test_with_errors(self, capsys):
        ptos.print_doctor_results(
            ["config/config.toml missing"],
            [],
            [("config/", "Folder exists")],
            []
        )
        out = capsys.readouterr().out
        assert "FAIL" in out
        assert "Summary: 1 error(s)" in out

    def test_with_warnings(self, capsys):
        ptos.print_doctor_results(
            [],
            ["records/ folder missing"],
            [("config/", "Folder exists")],
            []
        )
        out = capsys.readouterr().out
        assert "WARN" in out
        assert "warning(s)" in out

    def test_with_fixes(self, capsys):
        ptos.print_doctor_results([], [], [], ["Created config/ folder"], fix=True)
        out = capsys.readouterr().out
        assert "Fixes applied" in out
        assert "Created config/ folder" in out

    def test_verbose_mode(self, capsys):
        ptos.print_doctor_results(
            [],
            [],
            [("config/", "Folder exists"), ("records/", "Folder exists")],
            [],
            verbose=True
        )
        out = capsys.readouterr().out
        assert "Checks:" in out
        assert "OK" in out
