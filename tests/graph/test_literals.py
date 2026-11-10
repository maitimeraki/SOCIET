import pytest

from src.graph.literals import coerce_value, is_literal_value


@pytest.mark.parametrize("name", ["$2.5 billion", "2018", "40%", "5 km", "12,000"])
def test_measure_strings_are_literals(name):
    assert is_literal_value(name) is True


@pytest.mark.parametrize(
    "name", ["Amazon", "WholeFoods", "F-150", "2024 Paris Olympics", "S&P 500"]
)
def test_names_are_not_literals(name):
    assert is_literal_value(name) is False


def test_coerce_money():
    assert coerce_value("$2.5 billion") == (
        "money",
        {"amount": 2500000000.0, "currency": "USD"},
    )


def test_coerce_bare_year_is_date():
    assert coerce_value("2018") == ("date", "2018")


def test_coerce_percentage():
    value_type, value = coerce_value("40%")
    assert value_type == "percentage"
    assert value == 40.0


def test_coerce_percentage_with_thousands_separator():
    assert coerce_value("1,000%") == ("percentage", 1000.0)


def test_coerce_quantity():
    value_type, value = coerce_value("5 km")
    assert value_type == "quantity"
    assert value == {"value": "5 km", "unit": "km"}
