from decimal import Decimal

import pytest

from getsinapi.domain import PriceStatus
from getsinapi.normalizers import classify_price, parse_decimal


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, Decimal(0)),
        (0.0, Decimal("0.0")),
        ("1.234,56", Decimal("1234.56")),
        ("R$ 12,50", Decimal("12.50")),
        ("123.45", Decimal("123.45")),
    ],
)
def test_parse_decimal_preserves_numeric_value(value, expected):
    assert parse_decimal(value) == expected


@pytest.mark.parametrize("value", [None, "", "   "])
def test_empty_price_remains_missing(value):
    price, status = classify_price(value)
    assert price is None
    assert status == PriceStatus.MISSING


def test_reported_zero_is_not_missing():
    price, status = classify_price(0)
    assert price == Decimal(0)
    assert status == PriceStatus.REPORTED_ZERO


def test_explicit_not_researched_is_distinct_from_blank():
    price, status = classify_price(None, "Insumo não pesquisado")
    assert price is None
    assert status == PriceStatus.NOT_RESEARCHED


def test_nonzero_price_is_reported():
    price, status = classify_price("18,75")
    assert price == Decimal("18.75")
    assert status == PriceStatus.REPORTED


def test_invalid_numeric_value_is_rejected():
    with pytest.raises(ValueError, match="Valor numérico inválido"):
        parse_decimal("sem preço")
