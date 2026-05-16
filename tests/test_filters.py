import pytest
from ptos import (
    _tok_where,
    _eval_cond,
    _parse_expr,
    _eval_node,
    apply_where,
    _is_expression,
)


class TestTokenize:
    def test_simple_condition(self):
        tokens = _tok_where("type=expense")
        assert tokens == [("COND", "type=expense")]

    def test_and_expression(self):
        tokens = _tok_where("type=expense AND amount>50")
        assert ("COND", "type=expense") in tokens
        assert ("COND", "amount>50") in tokens
        assert ("AND", "AND") in tokens

    def test_or_expression(self):
        tokens = _tok_where("category=food OR category=transport")
        assert tokens.count(("OR", "OR")) == 1

    def test_with_parentheses(self):
        tokens = _tok_where("(category=food OR category=transport) AND amount>50")
        assert ("LPAREN", "(") in tokens
        assert ("RPAREN", ")") in tokens

    def test_not_operator(self):
        tokens = _tok_where("NOT stage=closed")
        assert ("NOT", "NOT") in tokens

    def test_operator_case_insensitive(self):
        tokens = _tok_where("type=expense and amount>50")
        assert ("AND", "AND") in tokens

    def test_quoted_value(self):
        tokens = _tok_where('vendor="some store"')
        assert len(tokens) == 1
        assert tokens[0][0] == "COND"
        assert "some store" in tokens[0][1]


class TestEvalCond:
    def test_equal_match(self):
        assert _eval_cond({"type": "expense"}, "type=expense") == True

    def test_equal_no_match(self):
        assert _eval_cond({"type": "income"}, "type=expense") == False

    def test_not_equal_match(self):
        assert _eval_cond({"type": "income"}, "type!=expense") == True

    def test_not_equal_no_match(self):
        assert _eval_cond({"type": "expense"}, "type!=expense") == False

    def test_contains_match(self):
        assert _eval_cond({"vendor": "some_store"}, "vendor~store") == True

    def test_contains_no_match(self):
        assert _eval_cond({"vendor": "some_store"}, "vendor~other") == False

    def test_not_contains(self):
        assert _eval_cond({"vendor": "some_store"}, "vendor!~other") == True

    def test_greater_than_numeric(self):
        assert _eval_cond({"amount": "100"}, "amount>50") == True
        assert _eval_cond({"amount": "30"}, "amount>50") == False

    def test_less_than_numeric(self):
        assert _eval_cond({"amount": "30"}, "amount<50") == True

    def test_date_comparison(self):
        assert _eval_cond({"_date": "2026-01-15"}, "2026-01-01<2026-02-01") == True

    def test_missing_key_returns_false(self):
        assert _eval_cond({"type": "expense"}, "amount>50") == False

    def test_list_field_contains(self):
        assert _eval_cond({"tag": ["food", "groceries"]}, "tag=food") == True
        assert _eval_cond({"tag": ["food", "groceries"]}, "tag=other") == False

    def test_unparseable_cond_returns_true(self):
        assert _eval_cond({"type": "expense"}, "bad") == True


class TestParseExpr:
    def test_single_cond(self):
        tokens = _tok_where("type=expense")
        node, pos = _parse_expr(tokens, 0)
        assert node == ("COND", "type=expense")

    def test_and(self):
        tokens = _tok_where("type=expense AND amount>50")
        node, pos = _parse_expr(tokens, 0)
        assert node[0] == "AND"

    def test_or(self):
        tokens = _tok_where("type=expense OR type=income")
        node, pos = _parse_expr(tokens, 0)
        assert node[0] == "OR"

    def test_parentheses(self):
        tokens = _tok_where("(type=expense OR type=income) AND amount>50")
        node, pos = _parse_expr(tokens, 0)
        assert node[0] == "AND"


class TestEvalNode:
    def test_simple_cond_true(self):
        node = ("COND", "type=expense")
        assert _eval_node(node, {"type": "expense"}) == True

    def test_simple_cond_false(self):
        node = ("COND", "type=expense")
        assert _eval_node(node, {"type": "income"}) == False

    def test_and_both_true(self):
        node = ("AND", ("COND", "type=expense"), ("COND", "amount>50"))
        assert _eval_node(node, {"type": "expense", "amount": "100"}) == True

    def test_and_one_false(self):
        node = ("AND", ("COND", "type=expense"), ("COND", "amount>50"))
        assert _eval_node(node, {"type": "expense", "amount": "30"}) == False

    def test_or_either_true(self):
        node = ("OR", ("COND", "type=expense"), ("COND", "type=income"))
        assert _eval_node(node, {"type": "expense"}) == True
        assert _eval_node(node, {"type": "income"}) == True
        assert _eval_node(node, {"type": "other"}) == False

    def test_not_true(self):
        node = ("NOT", ("COND", "stage=closed"))
        assert _eval_node(node, {"stage": "open"}) == True
        assert _eval_node(node, {"stage": "closed"}) == False


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

    def test_legacy_anded_filters(self):
        kv = {"type": "expense", "domain": "self"}
        assert apply_where(kv, ["type=expense", "domain=self"]) == True
        assert apply_where(kv, ["type=expense", "domain=work"]) == False
        assert apply_where(kv, ["type=income"]) == False

    def test_expression_mode(self):
        kv = {"type": "expense", "amount": "100"}
        assert apply_where(kv, ["type=expense AND amount>50"]) == True
        assert apply_where(kv, ["type=expense AND amount<50"]) == False

    def test_or_expression(self):
        kv = {"category": "food"}
        assert apply_where(kv, ["category=food OR category=transport"]) == True
        assert apply_where(kv, ["category=other OR category=none"]) == False

    def test_not_expression(self):
        kv = {"type": "expense", "stage": "open"}
        assert apply_where(kv, ["NOT stage=closed"]) == True
        assert apply_where(kv, ["NOT stage=open"]) == False

    def test_contains_operator(self):
        kv = {"vendor": "QuickBooks"}
        assert apply_where(kv, ["vendor~quick"]) == True
        assert apply_where(kv, ["vendor~slow"]) == False

    def test_inequality_numeric(self):
        kv = {"amount": "75"}
        assert apply_where(kv, ["amount>=50"]) == True
        assert apply_where(kv, ["amount>=100"]) == False
        assert apply_where(kv, ["amount<=75"]) == True
        assert apply_where(kv, ["amount<75"]) == False
