"""Percent helpers — internal storage is always a fraction (0.103 = 10.3%)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Union

NumberLike = Union[str, int, float, Decimal]


def _to_decimal(value: NumberLike) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        cleaned = value.strip().replace("\xa0", "").replace(" ", "")
        cleaned = cleaned.replace("%", "").replace(",", ".")
        return Decimal(cleaned)
    return Decimal(str(value))


def parse_percent(value: NumberLike) -> Decimal:
    """
    Parse percent points into a fraction.

    surebet DOM attrs (data-profit, data-overvalue, data-probability) are always
    percent points — including sub-1 values: "0.89" → 0.0089 (0.89%), not 89%.
    """
    return _to_decimal(value) / Decimal(100)


def format_percent(value: Decimal, places: int = 2, signed: bool = False) -> str:
    """Format fraction as percent points string, e.g. 0.229 → '22.90%'."""
    pp = value * Decimal(100)
    q = pp.quantize(Decimal(10) ** -places)
    if signed and q > 0:
        return f"+{q}%"
    return f"{q}%"


def percentage_points_difference(a: Decimal, b: Decimal) -> Decimal:
    """Absolute difference in percentage points between two fractions."""
    return abs((a - b) * Decimal(100))
