from datetime import datetime, timedelta, timezone
from decimal import Decimal

from surebet.deduplication import valuebet_content_hash, valuebet_identity_hash
from surebet.models import ArbOutcome, Arbitrage, StakeLeg, StakePlan, ValueBet
from surebet.text_clean import age_label, clean_competition
from telegram.formatting import (
    bet_callback_data,
    build_alert_keyboard,
    format_arbitrage_alert,
    format_valuebet_alert,
    short_id_from_hash,
)


def test_valuebet_content_hash_cross_filter():
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
    b = a.model_copy(update={"filter_id": "f2", "filter_name": "1UN"})
    assert valuebet_identity_hash(a) != valuebet_identity_hash(b)
    assert valuebet_content_hash(a) == valuebet_content_hash(b)


def test_clean_competition_strips_bracket_id():
    assert clean_competition("[224176] IHF Club World Championship") == "IHF Club World Championship"
    assert clean_competition("Premier League") == "Premier League"


def test_keyboard_apostei_nao_only():
    sid = short_id_from_hash("abcdef0123456789ffff")
    kb = build_alert_keyboard(short_id=sid)
    rows = kb["inline_keyboard"]
    assert len(rows) == 1
    assert rows[0][0]["callback_data"] == bet_callback_data("Y", sid)
    assert rows[0][1]["callback_data"] == bet_callback_data("N", sid)
    assert "url" not in rows[0][0]
    assert len(rows[0][0]["callback_data"]) <= 64


def test_age_label():
    now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    past = now - timedelta(seconds=45)
    assert age_label(past, now=now) == "45s"


def test_format_valuebet_compact():
    vb = ValueBet(
        filter_id="f1",
        filter_name="0.5UN",
        sport="League of Legends",
        competition="League of Legends - EMEA Masters",
        event="eSuba – White Dragons",
        market_raw="Total acima 31.5 1º mapa - abates",
        bookmaker="Slottica",
        odds=Decimal("1.85"),
        fair_probability=Decimal("0.658"),
        site_overvalue=Decimal("0.2173"),
        captured_at=datetime(2026, 9, 29, 11, 44, 41, tzinfo=timezone.utc),
    )
    text = format_valuebet_alert(vb, tz="UTC")
    assert text.startswith("🔥 +21.73% · 0.5UN")
    assert "eSuba – White Dragons" in text
    assert "🔎" not in text
    assert "🏆 Desporto:" not in text
    assert "Slottica @ 1.85 · p 65.80%" in text
    assert text.count("\n") <= 6


def test_format_arbitrage_compact_hides_losing_stakes():
    arb = Arbitrage(
        filter_id="surebet_surebets",
        filter_name="Surebets",
        sport="Futebol",
        competition="Denmark - A Liga, Women",
        event="Odense Q – AGF W",
        site_profit=Decimal("0.012"),
        outcomes=[
            ArbOutcome(bookmaker="Bet7", market_raw="AGF W vence / Draw No Bet", odds=Decimal("1.84")),
            ArbOutcome(bookmaker="22Bet", market_raw="Empate", odds=Decimal("3.73")),
            ArbOutcome(bookmaker="22Bet", market_raw="Odense (Women) vence", odds=Decimal("3.11")),
        ],
        stakes=StakePlan(
            total=Decimal("100"),
            legs=[
                StakeLeg(bookmaker="Bet7", odds=Decimal("1.84"), stake=Decimal("47.96"), payout=Decimal("88.25")),
                StakeLeg(bookmaker="22Bet", odds=Decimal("3.73"), stake=Decimal("23.66"), payout=Decimal("88.25")),
                StakeLeg(bookmaker="22Bet", odds=Decimal("3.11"), stake=Decimal("28.38"), payout=Decimal("88.26")),
            ],
            guaranteed_payout=Decimal("88.25"),
            profit=Decimal("-11.75"),
            roi=Decimal("-0.1175"),
        ),
        captured_at=datetime(2026, 9, 29, 11, 43, 28, tzinfo=timezone.utc),
    )
    text = format_arbitrage_alert(arb, tz="UTC")
    assert text.startswith("💰 +1.20% · Surebets")
    assert "Bet7 · AGF W vence / Draw No Bet @ 1.84" in text
    assert "Stake:" not in text
    assert "+-11.75" not in text
    assert "payout" not in text
    assert "🔎 Filtro:" not in text


def test_format_arbitrage_shows_stakes_when_profitable():
    arb = Arbitrage(
        filter_id="surebet_surebets",
        filter_name="Surebets",
        event="A – B",
        site_profit=Decimal("0.05"),
        outcomes=[
            ArbOutcome(bookmaker="X", market_raw="Over 2.5", odds=Decimal("2.10")),
            ArbOutcome(bookmaker="Y", market_raw="Under 2.5", odds=Decimal("2.10")),
        ],
        stakes=StakePlan(
            total=Decimal("100"),
            legs=[
                StakeLeg(bookmaker="X", odds=Decimal("2.10"), stake=Decimal("50"), payout=Decimal("105")),
                StakeLeg(bookmaker="Y", odds=Decimal("2.10"), stake=Decimal("50"), payout=Decimal("105")),
            ],
            guaranteed_payout=Decimal("105"),
            profit=Decimal("5"),
            roi=Decimal("0.05"),
        ),
        captured_at=datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc),
    )
    text = format_arbitrage_alert(arb, tz="UTC")
    assert "X · Over 2.5" in text
    assert "2.10 → 50 EUR" in text
    assert "100 EUR → 105 EUR (+5 EUR)" in text
