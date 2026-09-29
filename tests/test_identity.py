from decimal import Decimal

from surebet.deduplication import arbitrage_identity_hash, valuebet_identity_hash
from surebet.models import ArbOutcome, Arbitrage, MarketParts, ValueBet


def test_valuebet_hash_stable_ignores_odds():
    a = ValueBet(
        filter_id="f1",
        filter_name="0.5UN",
        event_id="e1",
        bookmaker="22Bet",
        market_type="total",
        period="full_time",
        line=Decimal("2.5"),
        selection="over",
        odds=Decimal("2.0"),
    )
    b = a.model_copy(update={"odds": Decimal("3.0"), "site_overvalue": Decimal("0.2")})
    assert valuebet_identity_hash(a) == valuebet_identity_hash(b)


def test_arbitrage_hash_order_independent():
    p_over = MarketParts(market_raw="o", market_type="total", period="full_time", line=Decimal("2.5"), selection="over")
    p_under = MarketParts(market_raw="u", market_type="total", period="full_time", line=Decimal("2.5"), selection="under")
    o1 = ArbOutcome(bookmaker="A", market_raw="o", odds=Decimal("2.1"), selection="over", market_parts=p_over)
    o2 = ArbOutcome(bookmaker="B", market_raw="u", odds=Decimal("2.2"), selection="under", market_parts=p_under)
    arb1 = Arbitrage(filter_id="f", filter_name="S", event="X – Y", market_type="total", period="full_time", line=Decimal("2.5"), outcomes=[o1, o2])
    arb2 = Arbitrage(filter_id="f", filter_name="S", event="X – Y", market_type="total", period="full_time", line=Decimal("2.5"), outcomes=[o2, o1])
    assert arbitrage_identity_hash(arb1) == arbitrage_identity_hash(arb2)
