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
    Parse a percent-ish value into a fraction.

    - "41%" / "41" / 41 / "41,0" when clearly a percent-points amount → 0.41
    - Values already in (0, 1] stay as-is (0.41 → 0.41)
    - Values > 1 are treated as percent points (12.1 → 0.121)
    """
    if isinstance(value, str) and "%" in value:
        return _to_decimal(value) / Decimal(100)

    d = _to_decimal(value)
    if d == 0:
        return Decimal("0")
    # already a fraction
    if Decimal("0") < abs(d) <= Decimal("1"):
        return d
    # percent points (e.g. 12.1, 67.13, 10.3)
    return d / Decimal(100)


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
