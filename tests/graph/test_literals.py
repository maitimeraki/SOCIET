import pytest
from src.graph.literals import is_literal_value, coerce_value

@pytest.mark.parametrize("name", ["$2.5 billion", "2018", "40%", "5 km", "12,000"])
def test_measure_strings_are_literals(name):
    assert is_literal_value(name) is True

@pytest.mark.parametrize("name", ["Amazon", "WholeFoods", "F-150", "2024 Paris Olympics", "S&P 500"])
def test_names_are_not_literals(name):
    assert is_literal_value(name) is False

def test_coerce_money():
    assert coerce_value("$2.5 billion") == ("money", {"amount": 2500000000.0, "currency": "USD"})
