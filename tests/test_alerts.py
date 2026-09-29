from decimal import Decimal

from surebet.deduplication import valuebet_content_hash, valuebet_identity_hash
from surebet.models import ValueBet
from surebet.text_clean import age_label, clean_competition
from telegram.formatting import bet_callback_data, build_alert_keyboard, short_id_from_hash


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
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    past = now - timedelta(seconds=45)
    assert age_label(past, now=now) == "45s"
