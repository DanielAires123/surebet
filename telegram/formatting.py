"""Telegram message formatting — photo captions + helpers."""

from __future__ import annotations

from typing import Any, Sequence

from surebet.models import Arbitrage, FilterRunStats, ValueBet
from surebet.percent import format_percent

TELEGRAM_CAPTION_MAX = 1024


def bet_callback_data(action: str, short_id: str) -> str:
    return f"bet:{action}:{short_id}"


def short_id_from_hash(identity_hash: str) -> str:
    return (identity_hash or "")[:16]


def build_alert_keyboard(*, short_id: str) -> dict[str, Any]:
    """Kept for legacy pending Apostei/Não messages."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Apostei", "callback_data": bet_callback_data("Y", short_id)},
                {"text": "❌ Não", "callback_data": bet_callback_data("N", short_id)},
            ]
        ]
    }


def _roi_s(item: Arbitrage | ValueBet) -> str:
    if isinstance(item, ValueBet):
        roi = item.calculated_ev if item.calculated_ev is not None else item.site_overvalue
    else:
        roi = item.calculated_profit if item.calculated_profit is not None else item.site_profit
    return format_percent(roi, signed=True) if roi is not None else "n/a"


def format_valuebet_caption_line(vb: ValueBet) -> str:
    odd = f"{vb.odds:.2f}" if vb.odds is not None else "n/a"
    return f"{vb.event or 'n/a'}\n{vb.market_raw or 'n/a'} @ {odd} · {_roi_s(vb)}"


def format_arbitrage_caption_line(arb: Arbitrage) -> str:
    odds_s = " / ".join(f"{o.bookmaker or '?'} {o.odds:.2f}" for o in arb.outcomes) or "n/a"
    return f"{arb.event or 'n/a'}\n{odds_s} · {_roi_s(arb)}"


def _item_block(item: Arbitrage | ValueBet) -> str:
    if isinstance(item, ValueBet):
        return format_valuebet_caption_line(item)
    return format_arbitrage_caption_line(item)


def format_filter_caption(
    filter_name: str,
    items: Sequence[Arbitrage | ValueBet],
    *,
    max_len: int = TELEGRAM_CAPTION_MAX,
) -> str:
    """Photo caption: `{filtro} — N novas` + compact blocks (Telegram 1024 cap)."""
    n = len(items)
    header = f"{filter_name} — {n} nova" if n == 1 else f"{filter_name} — {n} novas"
    if n == 0:
        return header

    blocks = [_item_block(it) for it in items]
    fitted: list[str] = []
    for block in blocks:
        trial = "\n\n".join([header, *fitted, block])
        if len(trial) <= max_len:
            fitted.append(block)
        else:
            break

    omitted = n - len(fitted)
    if omitted == 0:
        return "\n\n".join([header, *fitted])

    # Drop blocks until header + body + marker fit
    marker = f"… +{omitted} mais"
    while fitted:
        text = "\n\n".join([header, *fitted, marker])
        if len(text) <= max_len:
            return text
        fitted.pop()
        omitted = n - len(fitted)
        marker = f"… +{omitted} mais"

    text = f"{header}\n\n{marker}"
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


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
