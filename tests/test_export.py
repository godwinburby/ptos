import pytest
import os
import io
import zipfile
import tomllib

import ptos


@pytest.fixture(autouse=True)
def _clear_cache():
    ptos._invalidate_all()
    yield
    ptos._invalidate_all()


def _write(config_dir, filename, content):
    os.makedirs(config_dir, exist_ok=True)
    path = os.path.join(config_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    ptos._invalidate_all()


class TestExportSchemaBundle:
    def test_all_types_selected(self):
        _write(ptos.CONFIG_DIR, "schema.toml", """
[types]
allowed = ["expense", "income"]

[fields.amount]
type = "int"
dimension = false
aggregatable = true

[global_fields.context]
type = "string"

[type.expense]
required = ["amount"]

[type.expense.fields.amount]

[type.income]
required = ["amount"]

[type.income.fields.amount]
""")
        _write(ptos.CONFIG_DIR, "queries.toml", """
[expenses]
where = "type=expense"
time = "this-month"

[income]
where = "type=income"
time = "this-month"
""")
        _write(ptos.CONFIG_DIR, "presets.toml", """
[presets.coffee]
type = "expense"
amount = 100

[presets.salary]
type = "income"
amount = 5000
""")
        _write(ptos.CONFIG_DIR, "config.toml", """
[user]
name = "Test"
""")

        bundle = ptos.export_schema_bundle(["expense", "income"])
        assert set(bundle["schema"]["types"]["allowed"]) == {"expense", "income"}
        assert "context" in bundle["schema"]["global_fields"]
        assert "expense" in bundle["schema"]["type"]
        assert "income" in bundle["schema"]["type"]
        assert "expenses" in bundle["queries"]
        assert "income" in bundle["queries"]

    def test_single_type_filters_queries(self):
        _write(ptos.CONFIG_DIR, "schema.toml", """
[types]
allowed = ["expense", "income"]

[global_fields.context]
type = "string"

[type.expense]
required = ["amount"]

[type.expense.fields.amount]

[type.income]
required = ["amount"]

[type.income.fields.amount]
""")
        _write(ptos.CONFIG_DIR, "queries.toml", """
[expenses]
where = "type=expense"
time = "this-month"

[income]
where = "type=income"
time = "this-month"
""")
        _write(ptos.CONFIG_DIR, "presets.toml", """
[presets.coffee]
type = "expense"
amount = 100

[presets.salary]
type = "income"
amount = 5000
""")
        _write(ptos.CONFIG_DIR, "config.toml", """
[user]
name = "Test"
""")

        bundle = ptos.export_schema_bundle(["expense"])

        assert bundle["schema"]["types"]["allowed"] == ["expense"]
        assert "expense" in bundle["schema"]["type"]
        assert "income" not in bundle["schema"]["type"]
        assert "expenses" in bundle["queries"]
        assert "income" not in bundle["queries"]
        assert "coffee" in bundle["presets"]["presets"]
        assert "salary" not in bundle["presets"]["presets"]

    def test_global_fields_always_included(self):
        _write(ptos.CONFIG_DIR, "schema.toml", """
[types]
allowed = ["expense"]

[global_fields.context]
type = "string"

[global_fields.project]
type = "string"

[type.expense]
required = ["amount"]

[type.expense.fields.amount]
""")
        _write(ptos.CONFIG_DIR, "queries.toml", "")
        _write(ptos.CONFIG_DIR, "presets.toml", "")
        _write(ptos.CONFIG_DIR, "config.toml", "")

        bundle = ptos.export_schema_bundle(["expense"])
        assert "context" in bundle["schema"]["global_fields"]
        assert "project" in bundle["schema"]["global_fields"]

    def test_metrics_dependency_chain(self):
        _write(ptos.CONFIG_DIR, "schema.toml", """
[types]
allowed = ["expense"]

[global_fields.context]
type = "string"

[type.expense]
required = ["amount"]

[type.expense.fields.amount]
""")
        _write(ptos.CONFIG_DIR, "queries.toml", """
[expenses]
where = "type=expense"
time = "this-month"
sum = true

[food]
where = "type=expense AND category=food"
time = "this-month"
sum = true

[metrics.food_ratio]
ratio = ["food", "expenses"]

[metrics.avg_spend]
avg = "expenses"

[dashboards.spending]
metrics = ["expenses", "food_ratio", "avg_spend"]
""")
        _write(ptos.CONFIG_DIR, "presets.toml", "")
        _write(ptos.CONFIG_DIR, "config.toml", "")

        bundle = ptos.export_schema_bundle(["expense"])
        q = bundle["queries"]
        assert "expenses" in q
        assert "food" in q
        assert "metrics" in q
        assert "food_ratio" in q["metrics"]
        assert "avg_spend" in q["metrics"]
        assert "dashboards" in q
        assert "spending" in q["dashboards"]

    def test_unrelated_metrics_excluded(self):
        _write(ptos.CONFIG_DIR, "schema.toml", """
[types]
allowed = ["expense", "income"]

[global_fields.context]
type = "string"

[type.expense]
required = ["amount"]

[type.expense.fields.amount]

[type.income]
required = ["amount"]

[type.income.fields.amount]
""")
        _write(ptos.CONFIG_DIR, "queries.toml", """
[expenses]
where = "type=expense"
time = "this-month"

[income]
where = "type=income"
time = "this-month"

[metrics.savings_rate]
derived = "income - expenses"
""")
        _write(ptos.CONFIG_DIR, "presets.toml", "")
        _write(ptos.CONFIG_DIR, "config.toml", "")

        bundle = ptos.export_schema_bundle(["expense"])
        q = bundle["queries"]
        assert "expenses" in q
        assert "income" not in q
        assert "metrics" in q
        assert "savings_rate" in q["metrics"]

    def test_no_shared_or_global_fields(self):
        _write(ptos.CONFIG_DIR, "schema.toml", """
[types]
allowed = ["expense"]

[type.expense]
required = ["amount"]

[type.expense.fields.amount]
""")
        _write(ptos.CONFIG_DIR, "queries.toml", "")
        _write(ptos.CONFIG_DIR, "presets.toml", "")
        _write(ptos.CONFIG_DIR, "config.toml", "")

        bundle = ptos.export_schema_bundle(["expense"])
        assert "global_fields" not in bundle["schema"]

    def test_shared_skipped_when_unused(self):
        _write(ptos.CONFIG_DIR, "schema.toml", """
[types]
allowed = ["expense"]

[shared.source]
type = "string"
options = ["salary", "freelance"]

[type.expense]
required = ["amount"]

[type.expense.fields.amount]
""")
        _write(ptos.CONFIG_DIR, "queries.toml", "")
        _write(ptos.CONFIG_DIR, "presets.toml", "")
        _write(ptos.CONFIG_DIR, "config.toml", "")

        bundle = ptos.export_schema_bundle(["expense"])
        assert "shared" not in bundle["schema"]

    def test_shared_included_when_referenced(self):
        _write(ptos.CONFIG_DIR, "schema.toml", """
[types]
allowed = ["expense"]

[shared.source]
type = "string"
options = ["salary", "freelance"]

[shared.payment_method]
type = "string"
options = ["cash", "card"]

[type.expense]
required = ["amount", "source"]

[type.expense.fields.amount]

[type.expense.fields.source]
use = "shared.source"
""")
        _write(ptos.CONFIG_DIR, "queries.toml", "")
        _write(ptos.CONFIG_DIR, "presets.toml", "")
        _write(ptos.CONFIG_DIR, "config.toml", "")

        bundle = ptos.export_schema_bundle(["expense"])
        assert "shared" in bundle["schema"]
        assert "source" in bundle["schema"]["shared"]
        assert "payment_method" not in bundle["schema"]["shared"]

    def test_shared_partial_inclusion(self):
        _write(ptos.CONFIG_DIR, "schema.toml", """
[types]
allowed = ["expense", "income"]

[shared.source]
type = "string"
options = ["salary", "freelance"]

[shared.payment_method]
type = "string"
options = ["cash", "card"]

[type.expense]
required = ["amount", "payment_method"]

[type.expense.fields.amount]

[type.expense.fields.payment_method]
use = "shared.payment_method"

[type.income]
required = ["amount", "source"]

[type.income.fields.amount]

[type.income.fields.source]
use = "shared.source"
""")
        _write(ptos.CONFIG_DIR, "queries.toml", "")
        _write(ptos.CONFIG_DIR, "presets.toml", "")
        _write(ptos.CONFIG_DIR, "config.toml", "")

        bundle = ptos.export_schema_bundle(["expense"])
        assert "shared" in bundle["schema"]
        assert "payment_method" in bundle["schema"]["shared"]
        assert "source" not in bundle["schema"]["shared"]

        bundle2 = ptos.export_schema_bundle(["income"])
        assert "shared" in bundle2["schema"]
        assert "source" in bundle2["schema"]["shared"]
        assert "payment_method" not in bundle2["schema"]["shared"]

    def test_config_always_full(self):
        _write(ptos.CONFIG_DIR, "schema.toml", """
[types]
allowed = ["expense"]

[type.expense]
required = ["amount"]

[type.expense.fields.amount]
""")
        _write(ptos.CONFIG_DIR, "queries.toml", "")
        _write(ptos.CONFIG_DIR, "presets.toml", "")
        _write(ptos.CONFIG_DIR, "config.toml", """
[user]
name = "Alice"

[display]
currency = "$"
""")

        bundle = ptos.export_schema_bundle(["expense"])
        assert bundle["config"]["user"]["name"] == "Alice"
        assert bundle["config"]["display"]["currency"] == "$"

    def test_empty_types(self):
        _write(ptos.CONFIG_DIR, "schema.toml", """
[types]
allowed = ["expense"]

[type.expense]
required = ["amount"]

[type.expense.fields.amount]
""")
        _write(ptos.CONFIG_DIR, "queries.toml", "")
        _write(ptos.CONFIG_DIR, "presets.toml", "")
        _write(ptos.CONFIG_DIR, "config.toml", "")

        bundle = ptos.export_schema_bundle([])
        assert bundle["schema"]["types"]["allowed"] == []
        assert bundle["schema"].get("type") is None


class TestBuildSchemaBundleZip:
    def test_zip_contains_four_files(self):
        _write(ptos.CONFIG_DIR, "schema.toml", """
[types]
allowed = ["expense"]
[type.expense]
required = ["amount"]
[type.expense.fields.amount]
""")
        _write(ptos.CONFIG_DIR, "queries.toml", """
[expenses]
where = "type=expense"
time = "this-month"
""")
        _write(ptos.CONFIG_DIR, "presets.toml", """
[presets.coffee]
type = "expense"
amount = 100
""")
        _write(ptos.CONFIG_DIR, "config.toml", "[user]\nname = \"Test\"\n")

        zip_bytes, filename = ptos.build_schema_bundle_zip(["expense"])
        assert filename.startswith("ptos-schema-share-")
        assert filename.endswith(".zip")

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            assert "config/schema.toml" in names
            assert "config/queries.toml" in names
            assert "config/presets.toml" in names
            assert "config/config.toml" in names

    def test_zip_toml_is_valid(self):
        _write(ptos.CONFIG_DIR, "schema.toml", """
[types]
allowed = ["expense"]
[global_fields.context]
type = "string"
[type.expense]
required = ["amount"]
[type.expense.fields.amount]
""")
        _write(ptos.CONFIG_DIR, "queries.toml", "")
        _write(ptos.CONFIG_DIR, "presets.toml", "")
        _write(ptos.CONFIG_DIR, "config.toml", "[user]\nname = \"Test\"\n")

        zip_bytes, _ = ptos.build_schema_bundle_zip(["expense"])
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            schema_data = tomllib.loads(zf.read("config/schema.toml").decode())
            assert schema_data["types"]["allowed"] == ["expense"]
            assert "context" in schema_data["global_fields"]

            config_data = tomllib.loads(zf.read("config/config.toml").decode())
            assert config_data["user"]["name"] == "Test"
