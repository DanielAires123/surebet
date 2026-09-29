"""Telegram message formatting — compact alerts."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from surebet.models import Arbitrage, ValueBet
from surebet.percent import format_percent


def _hhmmss(dt: datetime | None, tz_name: str) -> str:
    if not dt:
        return "--:--:--"
    try:
        local = dt.astimezone(ZoneInfo(tz_name))
    except Exception:
        local = dt
    return local.strftime("%H:%M:%S")


def format_valuebet_alert(vb: ValueBet, *, tz: str = "Europe/Lisbon") -> str:
    roi = vb.calculated_ev if vb.calculated_ev is not None else vb.site_overvalue
    roi_s = format_percent(roi, signed=True) if roi is not None else "n/a"
    prob = format_percent(vb.fair_probability) if vb.fair_probability is not None else "n/a"
    odd = f"{vb.odds:.2f}" if vb.odds is not None else "n/a"
    return "\n".join(
        [
            "🔥 Value Bet",
            f"🔎 Filtro: {vb.filter_name}",
            f"📈 ROI: {roi_s}",
            f"🏆 Desporto: {vb.sport or 'n/a'}",
            f"🏟️ Liga: {vb.competition or 'n/a'}",
            f"⚔️ Equipas: {vb.event or 'n/a'}",
            f"📊 Linha: {vb.market_raw or 'n/a'}",
            f"🏦 Casa de Apostas: {vb.bookmaker or 'n/a'}",
            f"💰 Odd: {odd}",
            f"🎯 Probabilidade: {prob}",
            f"🕐 Hora da Captura: {_hhmmss(vb.captured_at, tz)}",
        ]
    )


def format_arbitrage_alert(arb: Arbitrage, *, tz: str = "Europe/Lisbon", currency: str = "EUR") -> str:
    del currency  # unused in compact format
    roi = arb.calculated_profit if arb.calculated_profit is not None else arb.site_profit
    roi_s = format_percent(roi, signed=True) if roi is not None else "n/a"
    sport = arb.sport or next((o.sport for o in arb.outcomes if o.sport), None) or "n/a"
    liga = arb.competition or next((o.tournament for o in arb.outcomes if o.tournament), None) or "n/a"
    lines = [
        "💰 SureBet",
        f"🔎 Filtro: {arb.filter_name}",
        f"📈 ROI: {roi_s}",
        f"🏆 Desporto: {sport}",
        f"🏟️ Liga: {liga}",
        f"⚔️ Equipas: {arb.event or 'n/a'}",
    ]
    for o in arb.outcomes:
        odd = f"{o.odds:.2f}"
        lines.extend(
            [
                f"📊 Linha: {o.market_raw or 'n/a'}",
                f"🏦 Casa de Apostas: {o.bookmaker or 'n/a'}",
                f"💰 Odd: {odd}",
            ]
        )
    lines.append(f"🕐 Hora da Captura: {_hhmmss(arb.captured_at, tz)}")
    return "\n".join(lines)


def format_error_alert(reason: str) -> str:
    return f"SureBet Monitor\nErro: {reason}"
