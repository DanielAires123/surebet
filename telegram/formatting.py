"""Telegram message formatting — compact alerts + inline keyboards."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from surebet.models import Arbitrage, ValueBet
from surebet.percent import format_percent
from surebet.text_clean import age_label, clean_competition


def _hhmmss(dt: datetime | None, tz_name: str) -> str:
    if not dt:
        return "--:--:--"
    try:
        local = dt.astimezone(ZoneInfo(tz_name))
    except Exception:
        local = dt
    return local.strftime("%H:%M:%S")


def bet_callback_data(action: str, short_id: str) -> str:
    # Telegram callback_data max 64 bytes. short_id = 16 hex.
    return f"bet:{action}:{short_id}"


def short_id_from_hash(identity_hash: str) -> str:
    return (identity_hash or "")[:16]


def build_alert_keyboard(*, short_id: str) -> dict[str, Any]:
    """Inline keyboard: Apostei / Não only (Surebet hrefs are /nav/ gateways, not direct bookies)."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Apostei", "callback_data": bet_callback_data("Y", short_id)},
                {"text": "❌ Não", "callback_data": bet_callback_data("N", short_id)},
            ]
        ]
    }


def format_valuebet_alert(vb: ValueBet, *, tz: str = "Europe/Lisbon") -> str:
    roi = vb.calculated_ev if vb.calculated_ev is not None else vb.site_overvalue
    roi_s = format_percent(roi, signed=True) if roi is not None else "n/a"
    prob = format_percent(vb.fair_probability) if vb.fair_probability is not None else "n/a"
    odd = f"{vb.odds:.2f}" if vb.odds is not None else "n/a"
    age = age_label(vb.captured_at)
    age_line = f"⏱️ Age: {age}" if age else None
    lines = [
        "🔥 Value Bet",
        f"🔎 Filtro: {vb.filter_name}",
        f"📈 ROI: {roi_s}",
        f"🏆 Desporto: {vb.sport or 'n/a'}",
        f"🏟️ Liga: {clean_competition(vb.competition) or 'n/a'}",
        f"⚔️ Equipas: {vb.event or 'n/a'}",
        f"📊 Linha: {vb.market_raw or 'n/a'}",
        f"🏦 Casa de Apostas: {vb.bookmaker or 'n/a'}",
        f"💰 Odd: {odd}",
        f"🎯 Probabilidade: {prob}",
        f"🕐 Hora da Captura: {_hhmmss(vb.captured_at, tz)}",
    ]
    if age_line:
        lines.append(age_line)
    return "\n".join(lines)


def format_arbitrage_alert(arb: Arbitrage, *, tz: str = "Europe/Lisbon", currency: str = "EUR") -> str:
    roi = arb.calculated_profit if arb.calculated_profit is not None else arb.site_profit
    roi_s = format_percent(roi, signed=True) if roi is not None else "n/a"
    sport = arb.sport or next((o.sport for o in arb.outcomes if o.sport), None) or "n/a"
    liga = clean_competition(
        arb.competition or next((o.tournament for o in arb.outcomes if o.tournament), None)
    ) or "n/a"
    age = age_label(arb.captured_at)
    lines = [
        "💰 SureBet",
        f"🔎 Filtro: {arb.filter_name}",
        f"📈 ROI: {roi_s}",
        f"🏆 Desporto: {sport}",
        f"🏟️ Liga: {liga}",
        f"⚔️ Equipas: {arb.event or 'n/a'}",
    ]
    for i, o in enumerate(arb.outcomes):
        odd = f"{o.odds:.2f}"
        stake_s = ""
        if arb.stakes and i < len(arb.stakes.legs):
            st = arb.stakes.legs[i]
            stake_s = f" | Stake: {st.stake} {currency}"
        lines.extend(
            [
                f"📊 Linha: {o.market_raw or 'n/a'}",
                f"🏦 Casa de Apostas: {o.bookmaker or 'n/a'}",
                f"💰 Odd: {odd}{stake_s}",
            ]
        )
    if arb.stakes:
        lines.append(
            f"💵 Total: {arb.stakes.total} {currency} → "
            f"payout {arb.stakes.guaranteed_payout} {currency} "
            f"(+{arb.stakes.profit} {currency})"
        )
    lines.append(f"🕐 Hora da Captura: {_hhmmss(arb.captured_at, tz)}")
    if age:
        lines.append(f"⏱️ Age: {age}")
    return "\n".join(lines)


def format_error_alert(reason: str) -> str:
    return f"SureBet Monitor\nErro: {reason}"


def format_run_summary(
    *,
    filters_ok: int,
    filters_failed: int,
    raw: int,
    sent: int,
    new: int,
    duration_s: float,
    open_bets: int = 0,
) -> str:
    return (
        "📊 Monitor summary\n"
        f"✅ Filters: {filters_ok} ok / {filters_failed} fail\n"
        f"📥 Raw: {raw} | 🆕 New: {new} | 📤 Sent: {sent}\n"
        f"🎰 Open bets tracked: {open_bets}\n"
        f"⏱️ {duration_s:.0f}s"
    )


def format_bet_registered(action: str) -> str:
    if action == "Y":
        return "✅ Registado: Apostei (entra no tracking)"
    return "❌ Marcado: Não apostei (fora do PnL)"
