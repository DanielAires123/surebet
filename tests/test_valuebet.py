from decimal import Decimal

from surebet.config import Settings
from surebet.models import ValidationStatus
from surebet.validation import calculate_valuebet_ev, validate_valuebet


def _settings(**kwargs) -> Settings:
    base = dict(
        surebet_username="u",
        surebet_password="p",
        telegram_bot_token="t",
        telegram_chat_id="c",
    )
    base.update(kwargs)
    return Settings(**base)


def test_ev_classic():
    ev = calculate_valuebet_ev(Decimal("3.00"), Decimal("0.41"))
    assert ev == Decimal("0.23")


def test_validate_positive_within_tolerance():
    r = validate_valuebet(
        odds=Decimal("3.00"),
        probability=Decimal("0.41"),
        site_overvalue=Decimal("0.229"),
        settings=_settings(),
    )
    assert r.status == ValidationStatus.VALIDATED
    assert r.calculated_ev == Decimal("0.23")


def test_ev_negative():
    r = validate_valuebet(
        odds=Decimal("2.00"),
        probability=Decimal("0.40"),
        site_overvalue=Decimal("0.10"),
        settings=_settings(),
    )
    assert r.status == ValidationStatus.INVALID
    assert r.calculated_ev == Decimal("-0.20")


def test_ev_zero():
    r = validate_valuebet(
        odds=Decimal("2.00"),
        probability=Decimal("0.50"),
        site_overvalue=Decimal("0"),
        settings=_settings(),
    )
    assert r.status == ValidationStatus.INVALID


def test_missing_probability():
    r = validate_valuebet(odds=Decimal("3"), probability=None, site_overvalue=Decimal("0.2"))
    assert r.status == ValidationStatus.UNVERIFIED


def test_invalid_probability():
    r = validate_valuebet(odds=Decimal("3"), probability=Decimal("1.5"), site_overvalue=Decimal("0.2"))
    assert r.status == ValidationStatus.INVALID


def test_invalid_odds():
    r = validate_valuebet(odds=Decimal("1"), probability=Decimal("0.5"), site_overvalue=Decimal("0.2"))
    assert r.status == ValidationStatus.INVALID


def test_tolerance_exceeded():
    r = validate_valuebet(
        odds=Decimal("3.00"),
        probability=Decimal("0.41"),
        site_overvalue=Decimal("0.10"),
        settings=_settings(valuebet_validation_tolerance_pp=Decimal("0.5")),
    )
    assert r.status == ValidationStatus.UNVERIFIED
