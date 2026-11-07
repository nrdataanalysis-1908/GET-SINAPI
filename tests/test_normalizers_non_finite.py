from decimal import Decimal

import pytest

from getsinapi.normalizers import parse_decimal


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_parse_decimal_rejects_non_finite_float_and_decimal_values(value):
    with pytest.raises(ValueError, match="não finito"):
        parse_decimal(value)
