"""Telegram message formatting — compact alerts + inline keyboards."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from surebet.models import Arbitrage, FilterRunStats, ValueBet
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


def _money(amount: Decimal, currency: str) -> str:
    return f"{amount} {currency}"


def _signed_money(amount: Decimal, currency: str) -> str:
    if amount > 0:
        return f"+{_money(amount, currency)}"
    if amount < 0:
        return f"-{_money(abs(amount), currency)}"
    return _money(amount, currency)


def _meta_line(captured_at: datetime | None, tz: str) -> str:
    age = age_label(captured_at)
    base = _hhmmss(captured_at, tz)
    return f"{base} · {age}" if age else base


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
    odd = f"{vb.odds:.2f}" if vb.odds is not None else "n/a"
    prob = format_percent(vb.fair_probability) if vb.fair_probability is not None else None
    liga = clean_competition(vb.competition)

    lines = [
        f"🔥 {roi_s} · {vb.filter_name}",
        vb.event or "n/a",
    ]
    if liga or vb.sport:
        lines.append(" · ".join(x for x in (vb.sport, liga) if x))
    lines.append(vb.market_raw or "n/a")
    book_line = f"{vb.bookmaker or 'n/a'} @ {odd}"
    if prob:
        book_line += f" · p {prob}"
    lines.append(book_line)
    lines.append(_meta_line(vb.captured_at, tz))
    return "\n".join(lines)


def format_arbitrage_alert(arb: Arbitrage, *, tz: str = "Europe/Lisbon", currency: str = "EUR") -> str:
    roi = arb.calculated_profit if arb.calculated_profit is not None else arb.site_profit
    roi_s = format_percent(roi, signed=True) if roi is not None else "n/a"
    sport = arb.sport or next((o.sport for o in arb.outcomes if o.sport), None)
    liga = clean_competition(
        arb.competition or next((o.tournament for o in arb.outcomes if o.tournament), None)
    )

    lines = [
        f"💰 {roi_s} · {arb.filter_name}",
        arb.event or "n/a",
    ]
    if liga or sport:
        lines.append(" · ".join(x for x in (sport, liga) if x))

    show_stakes = bool(arb.stakes and arb.stakes.profit >= 0)
    for i, o in enumerate(arb.outcomes):
        odd = f"{o.odds:.2f}"
        market = o.market_raw or "n/a"
        book = o.bookmaker or "n/a"
        if show_stakes and arb.stakes and i < len(arb.stakes.legs):
            st = arb.stakes.legs[i].stake
            lines.append(f"{book} · {market}")
            lines.append(f"  {odd} → {_money(st, currency)}")
        else:
            lines.append(f"{book} · {market} @ {odd}")

    if show_stakes and arb.stakes:
        lines.append(
            f"{_money(arb.stakes.total, currency)} → "
            f"{_money(arb.stakes.guaranteed_payout, currency)} "
            f"({_signed_money(arb.stakes.profit, currency)})"
        )

    lines.append(_meta_line(arb.captured_at, tz))
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
    per_filter: list[FilterRunStats] | None = None,
    alert_cap_hit: bool = False,
) -> str:
    lines = [
        "📊 Monitor summary",
        f"✅ Filters: {filters_ok} ok / {filters_failed} fail",
        f"📥 Raw: {raw} | 🆕 New: {new} | 📤 Sent: {sent}",
        f"🎰 Open bets tracked: {open_bets}",
        f"⏱️ {duration_s:.0f}s",
    ]
    if alert_cap_hit:
        lines.append("⚠️ Alert cap hit — later filters may have scraped without sending")
    if per_filter:
        lines.append("")
        for fr in per_filter:
            status = "ok" if fr.ok else "FAIL"
            err = f" ({fr.error})" if fr.error else ""
            lines.append(
                f"· {fr.filter_name}: {status} raw={fr.raw} new={fr.new} sent={fr.sent}{err}"
            )
    return "\n".join(lines)


def format_bet_registered(action: str) -> str:
    if action == "Y":
        return "✅ Registado: Apostei (entra no tracking)"
    return "❌ Marcado: Não apostei (fora do PnL)"
