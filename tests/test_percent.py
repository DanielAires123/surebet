from decimal import Decimal

from surebet.percent import format_percent, parse_percent, percentage_points_difference


def test_parse_percent_from_string_with_sign():
    assert parse_percent("41%") == Decimal("0.41")


def test_parse_percent_fraction_unchanged():
    assert parse_percent(Decimal("0.41")) == Decimal("0.41")


def test_parse_percent_points():
    assert parse_percent("10.3") == Decimal("0.103")
    assert parse_percent(12.1) == Decimal("0.121")


def test_format_percent():
    assert format_percent(Decimal("0.229"), places=1, signed=True) == "+22.9%"


def test_pp_difference():
    assert percentage_points_difference(Decimal("0.23"), Decimal("0.229")) == Decimal("0.1")
