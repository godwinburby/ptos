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
