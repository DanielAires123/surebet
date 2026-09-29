from decimal import Decimal

from surebet.config import Settings
from surebet.models import ArbOutcome, MarketParts, ValidationStatus
from surebet.validation import calculate_stakes, validate_arbitrage


def _settings(**kwargs) -> Settings:
    base = dict(
        surebet_username="u",
        surebet_password="p",
        telegram_bot_token="t",
        telegram_chat_id="c",
    )
    base.update(kwargs)
    return Settings(**base)


def _leg(book, odds, market_raw, parts: MarketParts) -> ArbOutcome:
    return ArbOutcome(
        bookmaker=book,
        selection=parts.selection,
        market_raw=market_raw,
        odds=Decimal(str(odds)),
        event="South Sudan – Egypt",
        market_parts=parts,
    )


def test_two_way_classic():
    a = _leg(
        "Slottica",
        "2.39",
        "Over 1 - 1st period - corners",
        MarketParts(market_raw="x", market_type="corners", period="first_period", line=Decimal("1"), selection="over"),
    )
    b = _leg(
        "Bet7",
        "2.05",
        "Under 1 - 1st period - corners",
        MarketParts(market_raw="y", market_type="corners", period="first_period", line=Decimal("1"), selection="under"),
    )
    r = validate_arbitrage(outcomes=[a, b], site_profit=Decimal("0.103"), settings=_settings())
    assert r.status == ValidationStatus.VALIDATED
    assert r.inverse_probability_sum is not None
    assert abs(r.inverse_probability_sum - Decimal("0.9062")) < Decimal("0.001")
    assert r.calculated_profit is not None
    assert abs(r.calculated_profit - Decimal("0.1035")) < Decimal("0.001")


def test_incompatible_period_unverified():
    a = _leg(
        "A",
        "2.39",
        "Over 2.5 FT",
        MarketParts(market_raw="x", market_type="total", period="full_time", line=Decimal("2.5"), selection="over"),
    )
    b = _leg(
        "B",
        "2.05",
        "Under 2.5 1H",
        MarketParts(market_raw="y", market_type="total", period="first_half", line=Decimal("2.5"), selection="under"),
    )
    r = validate_arbitrage(outcomes=[a, b], site_profit=Decimal("0.10"), settings=_settings())
    assert r.status == ValidationStatus.UNVERIFIED
    assert any("period" in x.lower() or "Incompatible" in x for x in r.reasons)


def test_incompatible_line_unverified():
    a = _leg(
        "A",
        "2.1",
        "Over 2.5",
        MarketParts(market_raw="x", market_type="total", period="full_time", line=Decimal("2.5"), selection="over"),
    )
    b = _leg(
        "B",
        "2.1",
        "Under 3.5",
        MarketParts(market_raw="y", market_type="total", period="full_time", line=Decimal("3.5"), selection="under"),
    )
    r = validate_arbitrage(outcomes=[a, b], site_profit=Decimal("0.05"), settings=_settings())
    assert r.status == ValidationStatus.UNVERIFIED


def test_non_arbitrage():
    a = _leg(
        "A",
        "1.5",
        "Over 2.5",
        MarketParts(market_raw="x", market_type="total", period="full_time", line=Decimal("2.5"), selection="over"),
    )
    b = _leg(
        "B",
        "1.5",
        "Under 2.5",
        MarketParts(market_raw="y", market_type="total", period="full_time", line=Decimal("2.5"), selection="under"),
    )
    r = validate_arbitrage(outcomes=[a, b], site_profit=Decimal("0.01"), settings=_settings())
    assert r.status == ValidationStatus.INVALID


def test_three_way_1x2():
    legs = [
        _leg("A", "3.5", "1", MarketParts(market_raw="1", market_type="1x2", period="full_time", selection="home")),
        _leg("B", "3.5", "X", MarketParts(market_raw="X", market_type="1x2", period="full_time", selection="draw")),
        _leg("C", "3.5", "2", MarketParts(market_raw="2", market_type="1x2", period="full_time", selection="away")),
    ]
    r = validate_arbitrage(outcomes=legs, site_profit=None, settings=_settings())
    # 1/3.5 * 3 ≈ 0.857 < 1
    assert r.status == ValidationStatus.VALIDATED


def test_duplicate_outcome():
    a = _leg(
        "A",
        "2.2",
        "Over 2.5",
        MarketParts(market_raw="x", market_type="total", period="full_time", line=Decimal("2.5"), selection="over"),
    )
    b = _leg(
        "B",
        "2.2",
        "Over 2.5",
        MarketParts(market_raw="y", market_type="total", period="full_time", line=Decimal("2.5"), selection="over"),
    )
    r = validate_arbitrage(outcomes=[a, b], site_profit=Decimal("0.1"), settings=_settings())
    assert r.status == ValidationStatus.UNVERIFIED


def test_unknown_market_unverified():
    a = _leg("A", "2.2", "Weird", MarketParts(market_raw="Weird", market_type="unknown", period="full_time"))
    b = _leg("B", "2.2", "Weird2", MarketParts(market_raw="Weird2", market_type="unknown", period="full_time"))
    r = validate_arbitrage(outcomes=[a, b], site_profit=Decimal("0.1"), settings=_settings())
    assert r.status == ValidationStatus.UNVERIFIED


def test_stakes_rounding():
    plan = calculate_stakes([Decimal("2.39"), Decimal("2.05")], Decimal("100"))
    assert plan.total == Decimal("100")
    assert sum(l.stake for l in plan.legs) == Decimal("100")
    assert plan.guaranteed_payout == min(l.payout for l in plan.legs)
