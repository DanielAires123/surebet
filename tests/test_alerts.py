from datetime import datetime, timedelta, timezone
from decimal import Decimal

from surebet.deduplication import valuebet_content_hash, valuebet_identity_hash
from surebet.models import ArbOutcome, Arbitrage, ValueBet
from surebet.text_clean import age_label, clean_competition
from telegram.formatting import (
    TELEGRAM_CAPTION_MAX,
    bet_callback_data,
    build_alert_keyboard,
    format_arbitrage_caption_line,
    format_filter_caption,
    format_valuebet_caption_line,
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


def test_format_valuebet_caption_line():
    vb = ValueBet(
        filter_id="f1",
        filter_name="0.5UN",
        event="eSuba – White Dragons",
        bookmaker="22Bet",
        market_raw="Total acima 31.5 1º mapa - abates",
        odds=Decimal("1.85"),
        site_overvalue=Decimal("0.2173"),
    )
    line = format_valuebet_caption_line(vb)
    assert line == "eSuba – White Dragons (22Bet)\nTotal acima 31.5 1º mapa - abates @ 1.85 · +21.73%"


def test_format_arbitrage_caption_line():
    arb = Arbitrage(
        filter_id="surebet_surebets",
        filter_name="Surebets",
        event="Odense Q – AGF W",
        site_profit=Decimal("0.052"),
        outcomes=[
            ArbOutcome(bookmaker="Bet7", market_raw="Home", odds=Decimal("1.84")),
            ArbOutcome(bookmaker="22Bet", market_raw="Draw", odds=Decimal("3.73")),
            ArbOutcome(bookmaker="22Bet", market_raw="Away", odds=Decimal("3.11")),
        ],
    )
    line = format_arbitrage_caption_line(arb)
    assert line == "Odense Q – AGF W\nBet7 1.84 / 22Bet 3.73 / 22Bet 3.11 · +5.20%"


def test_format_filter_caption_valuebets():
    items = [
        ValueBet(
            filter_id="f",
            filter_name="Tugas",
            event="Joaquim – Miguel",
            market_raw="Over 2.5",
            odds=Decimal("2.50"),
            site_overvalue=Decimal("0.12"),
        ),
        ValueBet(
            filter_id="f",
            filter_name="Tugas",
            event="A – B",
            market_raw="Under 1.5",
            odds=Decimal("1.90"),
            site_overvalue=Decimal("0.08"),
        ),
    ]
    text = format_filter_caption("Tugas", items)
    assert text.startswith("Tugas — 2 novas")
    assert "Joaquim – Miguel" in text
    assert "Over 2.5 @ 2.50 · +12.00%" in text
    assert len(text) <= TELEGRAM_CAPTION_MAX


def test_format_filter_caption_top_three_only():
    """Detail lines are top-N; header can show full novas count."""
    items = [
        ValueBet(
            filter_id="f",
            filter_name="MAX",
            event=f"Team{i} – Opponent{i}",
            market_raw="Over 2.5",
            odds=Decimal("1.85"),
            site_overvalue=Decimal(str(0.30 - i * 0.01)),
        )
        for i in range(10)
    ]
    top = items[:3]
    text = format_filter_caption("MAX", top, total_novas=10)
    assert text.startswith("MAX — 10 novas")
    assert "Team0" in text and "Team1" in text and "Team2" in text
    assert "Team3" not in text
    assert "… +" not in text
    assert len(text) <= TELEGRAM_CAPTION_MAX


def test_format_filter_caption_header_without_details():
    text = format_filter_caption("MAX", [], total_novas=20)
    assert text == "MAX — 20 novas"


def test_format_filter_caption_truncates():
    items = [
        ValueBet(
            filter_id="f",
            filter_name="MAX",
            event=f"Team{i} – Opponent{i}",
            market_raw="Total acima 99.5 mapa longo com texto extra para encher",
            odds=Decimal("1.85"),
            site_overvalue=Decimal("0.20"),
        )
        for i in range(40)
    ]
    text = format_filter_caption("MAX", items, max_len=400)
    assert text.startswith("MAX — 40 novas")
    assert "… +" in text
    assert "mais" in text
    assert len(text) <= 400
