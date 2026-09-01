from ptos import apply_where, _is_expression


class TestIsExpression:
    def test_simple_condition_is_not_expression(self):
        assert not _is_expression("type=expense")

    def test_and_is_expression(self):
        assert _is_expression("type=expense AND amount>50")

    def test_or_is_expression(self):
        assert _is_expression("type=expense OR type=income")

    def test_parentheses_expression(self):
        assert _is_expression("(type=expense)")

    def test_not_is_expression(self):
        assert _is_expression("NOT type=expense")


class TestApplyWhere:
    def test_no_filters_passes(self):
        assert apply_where({"type": "expense"}, []) == True
        assert apply_where({"type": "expense"}, None) == True

    def test_equal_match(self):
        assert apply_where({"type": "expense"}, ["type=expense"]) == True

    def test_equal_no_match(self):
        assert apply_where({"type": "income"}, ["type=expense"]) == False

    def test_not_equal_match(self):
        assert apply_where({"type": "income"}, ["type!=expense"]) == True

    def test_not_equal_no_match(self):
        assert apply_where({"type": "expense"}, ["type!=expense"]) == False

    def test_contains_match(self):
        assert apply_where({"vendor": "some_store"}, ["vendor~store"]) == True

    def test_contains_no_match(self):
        assert apply_where({"vendor": "some_store"}, ["vendor~other"]) == False

    def test_not_contains(self):
        assert apply_where({"vendor": "some_store"}, ["vendor!~other"]) == True

    def test_greater_than_numeric(self):
        assert apply_where({"amount": "100"}, ["amount>50"]) == True
        assert apply_where({"amount": "30"}, ["amount>50"]) == False

    def test_less_than_numeric(self):
        assert apply_where({"amount": "30"}, ["amount<50"]) == True

    def test_missing_key_returns_false(self):
        assert apply_where({"type": "expense"}, ["amount>50"]) == False

    def test_list_field_contains(self):
        assert apply_where({"tag": ["food", "groceries"]}, ["tag=food"]) == True
        assert apply_where({"tag": ["food", "groceries"]}, ["tag=other"]) == False

    def test_unparseable_cond_returns_true(self):
        assert apply_where({"type": "expense"}, ["bad"]) == True

    def test_legacy_anded_filters(self):
        kv = {"type": "expense", "domain": "self"}
        assert apply_where(kv, ["type=expense", "domain=self"]) == True
        assert apply_where(kv, ["type=expense", "domain=work"]) == False
        assert apply_where(kv, ["type=income"]) == False

    def test_expression_and(self):
        kv = {"type": "expense", "amount": "100"}
        assert apply_where(kv, ["type=expense AND amount>50"]) == True
        assert apply_where(kv, ["type=expense AND amount<50"]) == False

    def test_expression_or(self):
        kv = {"category": "food"}
        assert apply_where(kv, ["category=food OR category=transport"]) == True
        assert apply_where(kv, ["category=other OR category=none"]) == False

    def test_expression_not(self):
        kv = {"type": "expense", "stage": "open"}
        assert apply_where(kv, ["NOT stage=closed"]) == True
        assert apply_where(kv, ["NOT stage=open"]) == False

    def test_expression_parentheses(self):
        kv = {"type": "expense", "amount": "100"}
        assert apply_where(kv, ["(type=expense OR type=income) AND amount>50"]) == True
        assert apply_where(kv, ["(type=income) AND amount>50"]) == False

    def test_inequality_numeric(self):
        kv = {"amount": "75"}
        assert apply_where(kv, ["amount>=50"]) == True
        assert apply_where(kv, ["amount>=100"]) == False
        assert apply_where(kv, ["amount<=75"]) == True
        assert apply_where(kv, ["amount<75"]) == False


class TestSpacedOperators:
    """Operators may be written with surrounding whitespace, e.g. `tag != snacks`."""

    def test_spaced_not_equal_in_expression(self):
        kv = {"type": "expense", "domain": "work", "tag": ["food", "snacks"]}
        assert apply_where(kv, ["type=expense AND domain=work AND tag != snacks"]) == False
        kv2 = {"type": "expense", "domain": "work", "tag": ["food"]}
        assert apply_where(kv2, ["type=expense AND domain=work AND tag != snacks"]) == True

    def test_spaced_not_equal_single(self):
        assert apply_where({"tag": ["snacks"]}, ["tag != snacks"]) == False
        assert apply_where({"tag": ["food"]}, ["tag != snacks"]) == True

    def test_spaced_contains(self):
        assert apply_where({"name": "john smith"}, ["name ~ john"]) == True
        assert apply_where({"name": "john smith"}, ["name ~ jane"]) == False

    def test_spaced_not_contains(self):
        assert apply_where({"name": "john smith"}, ["name !~ jane"]) == True
        assert apply_where({"name": "john smith"}, ["name !~ john"]) == False

    def test_spaced_comparison_and_continued_expression(self):
        kv = {"amount": "80", "type": "expense"}
        assert apply_where(kv, ["amount >= 50 AND type = expense"]) == True
        assert apply_where(kv, ["amount <= 50 AND type = expense"]) == False

    def test_spaced_equals_not_keyword(self):
        assert apply_where({"category": "home"}, ["category = home"]) == True
        assert apply_where({"category": "office"}, ["category = home"]) == False

    def test_unspaced_still_works_after_spacing(self):
        kv = {"amount": "75"}
        assert apply_where(kv, ["amount >= 50"]) == True
        assert apply_where(kv, ["amount>=100"]) == False

    def test_matches_not_expression_equivalent(self):
        kv = {"type": "expense", "domain": "work", "tag": ["food", "snacks"]}
        assert apply_where(kv, ["tag != snacks"]) == \
               apply_where(kv, ["NOT (tag=snacks)"])
        kv2 = {"type": "expense", "domain": "work", "tag": ["food"]}
        assert apply_where(kv2, ["tag != snacks"]) == \
               apply_where(kv2, ["NOT (tag=snacks)"])


class TestNotEqualsMissingKey:
    """A missing field must satisfy `!=` (NaN-like), like `NOT (field=x)`."""

    def test_missing_key_not_equal_returns_true(self):
        assert apply_where({"type": "expense"}, ["tag != snacks"]) == True

    def test_missing_key_not_equal_in_expression(self):
        kv = {"type": "expense", "domain": "work"}
        assert apply_where(kv, ["type=expense AND tag != snacks"]) == True

    def test_missing_key_equals_returns_false(self):
        assert apply_where({"type": "expense"}, ["tag = snacks"]) == False

    def test_missing_key_matches_not_equivalent(self):
        kv = {"type": "expense", "domain": "work"}
        assert apply_where(kv, ["tag != snacks"]) == \
               apply_where(kv, ["NOT (tag=snacks)"])

    def test_missing_key_ordered_op_returns_false(self):
        assert apply_where({"type": "expense"}, ["amount > 50"]) == False
        assert apply_where({"type": "expense"}, ["amount <= 50"]) == False

    def test_missing_key_not_contains_returns_true(self):
        assert apply_where({"type": "expense"}, ["tag !~ snacks"]) == True
