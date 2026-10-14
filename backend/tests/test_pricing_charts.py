import math

import pytest

from app import charts
from app.formula import Formula, FormulaError, evaluate
from app.pricing import call_cost, clamp_effort, credits_for_cost, thinking_ceiling


def test_credits_round_up():
    # Plan section 9: $0.0133 on Sonnet -> 4.7 -> 5 credits
    assert credits_for_cost(0.0133) == 5
    assert credits_for_cost(0.00065) == 1   # minimum 1 for any spend
    assert credits_for_cost(0) == 0
    # plan: 32.002 must round up to 33 (never down)
    assert credits_for_cost(0.091) == 33


def test_call_cost_matches_plan():
    # Normal answer: 3,000 new in + 3,000 cached + 700 out on Sonnet 5.5
    c = call_cost(2, 10, 3000, 700, cached_tokens=3000, price_cached=0.10)
    assert float(c) == pytest.approx(0.0133)


def test_effort_table():
    assert thinking_ceiling(8000, "low") == 1600
    assert thinking_ceiling(8000, "high") == 6400
    assert thinking_ceiling(16000, "max") == 15200
    assert clamp_effort("max", "free") == "low"
    assert clamp_effort("max", "pro") == "max"


def test_formula_safe():
    assert evaluate("1000*(1+5/100)^2") == pytest.approx(1102.5)
    assert evaluate("-2^2") == -4
    assert evaluate("sqrt(16)+max(1,2)") == 6
    for bad in ["__import__('os')", "a.b", "2**3", "open(1)", "1;2", "x[0]"]:
        with pytest.raises(FormulaError):
            evaluate(bad, {"x": 1})
    with pytest.raises(FormulaError):
        evaluate("1/0")
    with pytest.raises(FormulaError):
        evaluate("9^9999")


SAVINGS = {
    "chart": "line", "title": "How savings grow",
    "inputs": [
        {"id": "P", "label": "Start money ($)", "type": "number", "value": 1000},
        {"id": "r", "label": "Interest % per year", "type": "slider", "min": 0, "max": 20, "step": 0.5, "value": 5},
        {"id": "n", "label": "Years", "type": "slider", "min": 1, "max": 40, "value": 10},
    ],
    "x": {"label": "Year", "from": 0, "to": "n"},
    "lines": [{"name": "Money", "formula": "P * (1 + r/100)^x"}],
}


def test_plan_example_recipe_is_valid_and_computes():
    ok = charts.validate(SAVINGS)
    out = charts.compute(ok, {"n": 2})
    assert out["xs"][0] == 0 and out["xs"][-1] == 2
    assert out["series"][0]["values"][-1] == pytest.approx(1102.5)


@pytest.mark.parametrize("patch,msg", [
    ({"lines": [{"name": "a", "formula": "P*zzz"}]}, "unknown name"),
    ({"lines": [{"name": "a", "formula": "1/(r-5)"}]}, "fails"),     # divide by zero at the default value
    ({"chart": "radar"}, "chart must be"),
    ({"x": {"from": 5, "to": 1}}, "x.to must be above"),
    ({"inputs": [{"id": "x", "value": 1}]}, "not allowed"),
])
def test_bad_recipes_are_rejected(patch, msg):
    bad = {**SAVINGS, **patch}
    with pytest.raises(charts.RecipeError, match=msg):
        charts.validate(bad)


def test_bar_recipe():
    r = charts.validate({"chart": "bar", "title": "t", "inputs": [{"id": "a", "type": "slider", "min": 0, "max": 5, "value": 2}],
                         "data": [{"label": "one", "formula": "a"}, {"label": "two", "formula": "a*2"}]})
    assert charts.compute(r)["series"][0]["values"] == [2.0, 4.0]
