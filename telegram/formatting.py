"""Telegram message formatting."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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
    ov = format_percent(vb.site_overvalue, signed=True) if vb.site_overvalue is not None else "n/a"
    ev = format_percent(vb.calculated_ev, signed=True) if vb.calculated_ev is not None else "n/a"
    prob = format_percent(vb.fair_probability) if vb.fair_probability is not None else "n/a"
    odd = f"{vb.odds:.2f}" if vb.odds is not None else "n/a"
    status = "✅ Validação matemática OK" if vb.validation_status.value == "validated" else f"⚠️ {vb.validation_status.value.upper()}"
    lines = [
        "🔥 VALUE BET VALIDADA" if vb.validation_status.value == "validated" else f"🔥 VALUE BET ({vb.validation_status.value})",
        "",
        f"🔎 Filtro: {vb.filter_name}",
        "",
        f"📈 Overvalue: {ov}",
        f"🧮 EV calculado: {ev}",
        "",
        f"🏆 {vb.sport or ''}".strip(),
        vb.event or "",
        "",
        f"📊 {vb.market_raw or ''}",
        "",
        f"🏦 {vb.bookmaker or ''}",
        f"💰 Odd: {odd}",
        f"🎯 Probabilidade: {prob}",
        "",
        f"🕐 Capturada: {_hhmmss(vb.captured_at, tz)}",
        "",
        "Odds capturadas às " + _hhmmss(vb.captured_at, tz) + " — podem já não estar disponíveis.",
        "",
        status,
    ]
    if vb.validation_reasons:
        lines.append("Motivos: " + "; ".join(vb.validation_reasons))
    return "\n".join(lines)


def format_arbitrage_alert(arb: Arbitrage, *, tz: str = "Europe/Lisbon", currency: str = "EUR") -> str:
    site = format_percent(arb.site_profit) if arb.site_profit is not None else "n/a"
    roi = format_percent(arb.calculated_profit) if arb.calculated_profit is not None else "n/a"
    inv = format_percent(arb.inverse_probability_sum) if arb.inverse_probability_sum is not None else "n/a"
    title = "💰 ARBITRAGE VALIDADA" if arb.validation_status.value == "validated" else f"💰 ARBITRAGE ({arb.validation_status.value})"
    lines = [
        title,
        "",
        f"🔎 Filtro: {arb.filter_name}",
        "",
        f"📈 Profit SureBet: {site}",
        f"🧮 ROI calculado: {roi}",
        f"📊 Soma implícita: {inv}",
        "",
        f"⚽ {arb.event or ''}",
        "",
    ]
    for idx, o in enumerate(arb.outcomes, start=1):
        lines.extend(
            [
                f"{idx}️⃣ {o.bookmaker}",
                o.market_raw,
                f"Odd: {o.odds:.2f}",
                "",
            ]
        )
    if arb.stakes:
        lines.append(f"💵 Exemplo para {arb.stakes.total} {currency}:")
        lines.append("")
        for leg in arb.stakes.legs:
            lines.append(f"{leg.bookmaker}: {leg.stake} {currency}")
        lines.extend(
            [
                "",
                f"Retorno mínimo: {arb.stakes.guaranteed_payout} {currency}",
                f"Lucro estimado: {arb.stakes.profit} {currency}",
                "",
            ]
        )
    lines.extend(
        [
            f"🕐 Odds capturadas: {_hhmmss(arb.captured_at, tz)}",
            "",
            "Odds capturadas neste instante — podem já não estar disponíveis.",
            "",
            "✅ Arbitragem matematicamente validada"
            if arb.validation_status.value == "validated"
            else f"⚠️ {arb.validation_status.value.upper()}",
        ]
    )
    if arb.validation_reasons:
        lines.append("Motivos: " + "; ".join(arb.validation_reasons))
    return "\n".join(lines)


def format_error_alert(reason: str) -> str:
    return (
        "⚠️ SureBet Monitor\n\n"
        "Automação interrompida.\n"
        f"Motivo: {reason}"
    )
