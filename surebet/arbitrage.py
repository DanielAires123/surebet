"""Surebet / arbitrage DOM extraction."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from playwright.sync_api import Page

from surebet import selectors as S
from surebet.config import Settings
from surebet.deduplication import arbitrage_identity_hash
from surebet.models import ArbOutcome, Arbitrage, FilterConfig, ParseStats
from surebet.normalization import normalize_bookmaker, normalize_event, parse_market
from surebet.percent import parse_percent
from surebet.validation import attach_bookmakers, calculate_stakes, validate_arbitrage

log = logging.getLogger(__name__)


def _dec_attr(el, name: str) -> Optional[Decimal]:
    raw = el.get_attribute(name)
    if raw is None or raw == "":
        return None
    try:
        return Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return None


def _text(locator) -> Optional[str]:
    if locator.count() == 0:
        return None
    t = locator.first.inner_text().strip()
    return t or None


def _strip_html_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def extract_arbitrages(page: Page, filt: FilterConfig, settings: Settings, *, total_stake: Decimal) -> tuple[list[Arbitrage], ParseStats]:
    records = page.locator(S.SUREBET_RECORD)
    n = records.count()
    stats = ParseStats(raw=n)
    out: list[Arbitrage] = []
    now = datetime.now(timezone.utc)

    for i in range(n):
        el = records.nth(i)
        try:
            data_id = el.get_attribute("data-id")
            profit_raw = _dec_attr(el, "data-profit")
            site_profit = parse_percent(profit_raw) if profit_raw is not None else None
            start_at = el.get_attribute("data-start-at")

            legs = el.locator(S.SUREBET_LEG)
            leg_n = legs.count()
            outcomes: list[ArbOutcome] = []
            events = []
            sports = []

            for j in range(leg_n):
                leg = legs.nth(j)
                bookmaker = _text(leg.locator(S.LEG_BOOKMAKER))
                sport = _text(leg.locator(S.LEG_SPORT))
                event = _text(leg.locator(S.LEG_EVENT))
                # prefer bold tournament matchup if present
                tournament = _text(leg.locator(S.LEG_TOURNAMENT))
                matchup = None
                bold = leg.locator(f"{S.LEG_TOURNAMENT} .fw-bold")
                if bold.count() > 0:
                    matchup = _text(bold)
                market_el = leg.locator(S.LEG_MARKET)
                market_raw = None
                if market_el.count() > 0:
                    market_raw = market_el.first.get_attribute("data-bs-original-title") or _text(market_el)
                    if market_raw:
                        market_raw = _strip_html_text(market_raw)
                odds_t = _text(leg.locator(S.LEG_ODDS))
                odds = Decimal(odds_t.replace(",", ".")) if odds_t else None
                if odds is None:
                    raise ValueError("missing odds")

                parts = parse_market(market_raw or "")
                _, book_display = normalize_bookmaker(bookmaker or "")
                outcomes.append(
                    ArbOutcome(
                        bookmaker=book_display,
                        selection=parts.selection,
                        market_raw=market_raw or "",
                        odds=odds,
                        sport=sport,
                        event=normalize_event(matchup or event or "") or None,
                        tournament=tournament,
                        market_parts=parts,
                    )
                )
                if matchup or event:
                    events.append(normalize_event(matchup or event or ""))
                if sport:
                    sports.append(sport)

            # representative event: prefer fw-bold matchup
            event_name = events[0] if events else None
            sport_name = sports[0] if sports else None

            # common market fields when compatible
            market_type = outcomes[0].market_parts.market_type if outcomes[0].market_parts else "unknown"
            period = outcomes[0].market_parts.period if outcomes[0].market_parts else None
            line = outcomes[0].market_parts.line if outcomes[0].market_parts else None

            arb = Arbitrage(
                filter_id=filt.id,
                filter_name=filt.name,
                event_id=data_id,
                sport=sport_name,
                event=event_name,
                market_type=market_type,
                period=period,
                line=line,
                site_profit=site_profit,
                outcomes=outcomes,
                captured_at=now,
                raw={
                    "signature": el.get_attribute("data-signature"),
                    "formula": el.get_attribute("data-formula"),
                    "data_start_at": start_at,
                },
            )

            if start_at and start_at.isdigit():
                try:
                    arb.event_datetime = datetime.fromtimestamp(int(start_at), tz=timezone.utc)
                except (ValueError, OSError):
                    pass

            vr = validate_arbitrage(outcomes=outcomes, site_profit=site_profit, settings=settings)
            arb.validation_status = vr.status
            arb.validation_reasons = vr.reasons
            arb.calculated_profit = vr.calculated_profit
            arb.inverse_probability_sum = vr.inverse_probability_sum

            if settings and total_stake and len(outcomes) >= 2:
                # always compute stakes for display when configured; attach even if unverified
                plan = calculate_stakes([o.odds for o in outcomes], total_stake)
                arb.stakes = attach_bookmakers(plan, [o.bookmaker for o in outcomes])

            arb.identity_hash = arbitrage_identity_hash(arb)
            stats.parsed += 1  # DOM row extracted OK (threshold filter is separate)

            if filt.min_profit is not None and (arb.site_profit is None or arb.site_profit < filt.min_profit):
                continue

            out.append(arb)
        except Exception as e:
            stats.failed += 1
            log.warning("Failed to parse surebet row %s: %s", i, e)

    return out, stats
