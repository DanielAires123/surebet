"""Identity hashing and resend decisions."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

from surebet.models import Arbitrage, OpportunityState, ValueBet
from surebet.normalization import normalize_bookmaker, normalize_event
from surebet.percent import percentage_points_difference


def _sha(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def valuebet_identity_hash(vb: ValueBet) -> str:
    event_key = vb.event_id or normalize_event(vb.event or "")
    book_can, _ = normalize_bookmaker(vb.bookmaker or "")
    line = "" if vb.line is None else str(vb.line)
    team = "" if vb.team is None else str(vb.team)
    participant = vb.participant or team
    return _sha(
        vb.filter_id,
        event_key,
        book_can,
        vb.market_type or "unknown",
        vb.period or "",
        line,
        vb.selection or "",
        participant,
    )


def arbitrage_identity_hash(arb: Arbitrage) -> str:
    event_key = arb.event_id or normalize_event(arb.event or "")
    line = "" if arb.line is None else str(arb.line)
    legs = []
    for o in arb.outcomes:
        book_can, _ = normalize_bookmaker(o.bookmaker)
        mp = o.market_parts
        legs.append(
            "|".join(
                [
                    book_can,
                    (mp.selection if mp and mp.selection else o.selection) or "",
                    (mp.market_type if mp else "") or "",
                    (mp.period if mp and mp.period else "") or "",
                    "" if not mp or mp.line is None else str(mp.line),
                    normalize_event(o.market_raw or ""),
                ]
            )
        )
    legs_sorted = sorted(legs)
    return _sha(
        arb.filter_id,
        event_key,
        arb.market_type or "unknown",
        arb.period or "",
        line,
        *legs_sorted,
    )


def should_resend_valuebet(
    prev: Optional[OpportunityState],
    vb: ValueBet,
    *,
    odds_threshold: Decimal,
    overvalue_pp_threshold: Decimal,
    expiry_minutes: int,
    now: Optional[datetime] = None,
) -> tuple[bool, str]:
    """Returns (should_send, reason) where reason in new|changed|duplicate|expired_reappear."""
    now = now or datetime.now(timezone.utc)
    if prev is None:
        return True, "new"
    if prev.last_seen_at and (now - prev.last_seen_at).total_seconds() > expiry_minutes * 60:
        return True, "expired_reappear"
    if prev.last_sent_at is None:
        return True, "new"
    if vb.odds is not None and prev.last_odds:
        if abs(vb.odds - prev.last_odds[0]) >= odds_threshold:
            return True, "changed"
    if (
        vb.site_overvalue is not None
        and prev.last_overvalue is not None
        and percentage_points_difference(vb.site_overvalue, prev.last_overvalue) >= overvalue_pp_threshold
    ):
        return True, "changed"
    return False, "duplicate"


def should_resend_arbitrage(
    prev: Optional[OpportunityState],
    arb: Arbitrage,
    *,
    odds_threshold: Decimal,
    profit_pp_threshold: Decimal,
    expiry_minutes: int,
    now: Optional[datetime] = None,
) -> tuple[bool, str]:
    now = now or datetime.now(timezone.utc)
    if prev is None:
        return True, "new"
    if prev.last_seen_at and (now - prev.last_seen_at).total_seconds() > expiry_minutes * 60:
        return True, "expired_reappear"
    if prev.last_sent_at is None:
        return True, "new"
    if arb.site_profit is not None and prev.last_profit is not None:
        if percentage_points_difference(arb.site_profit, prev.last_profit) >= profit_pp_threshold:
            return True, "changed"
    curr_odds = [o.odds for o in arb.outcomes]
    if prev.last_odds and len(prev.last_odds) == len(curr_odds):
        for a, b in zip(sorted(curr_odds), sorted(prev.last_odds)):
            if abs(a - b) >= odds_threshold:
                return True, "changed"
    elif prev.last_odds and len(prev.last_odds) != len(curr_odds):
        return True, "changed"
    return False, "duplicate"
