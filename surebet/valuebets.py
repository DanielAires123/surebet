"""Valuebet DOM extraction."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from playwright.sync_api import Page

from surebet import selectors as S
from surebet.config import Settings
from surebet.deduplication import valuebet_identity_hash
from surebet.models import FilterConfig, ParseStats, ValueBet, ValidationStatus
from surebet.normalization import normalize_bookmaker, normalize_event, parse_market
from surebet.percent import parse_percent
from surebet.validation import validate_valuebet

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


def extract_valuebets(page: Page, filt: FilterConfig, settings: Settings) -> tuple[list[ValueBet], ParseStats]:
    records = page.locator(S.VALUEBET_RECORD)
    n = records.count()
    stats = ParseStats(raw=n)
    out: list[ValueBet] = []
    now = datetime.now(timezone.utc)

    for i in range(n):
        el = records.nth(i)
        try:
            data_id = el.get_attribute("data-id")
            odds = _dec_attr(el, "data-value")
            # data-probability is percent points (67.13)
            prob_raw = _dec_attr(el, "data-probability")
            probability = parse_percent(prob_raw) if prob_raw is not None else None
            ov_raw = _dec_attr(el, "data-overvalue")
            site_ov = parse_percent(ov_raw) if ov_raw is not None else None
            start_at = el.get_attribute("data-start-at")

            bookmaker = _text(el.locator(S.LEG_BOOKMAKER))
            sport = _text(el.locator(S.LEG_SPORT))
            event = _text(el.locator(S.LEG_EVENT))
            tournament = _text(el.locator(S.LEG_TOURNAMENT))
            market_el = el.locator(S.LEG_MARKET)
            market_raw = None
            if market_el.count() > 0:
                market_raw = market_el.first.get_attribute("data-bs-original-title") or _text(market_el)
                if market_raw:
                    market_raw = _strip_html_text(market_raw)

            # data-id is the valuebet record id (e.g. 1taGhg). Do NOT replace with
            # td.event's event-XXX — revalidate looks up tbody[data-id=...] and that
            # would miss every row (Sent: 0 with New: N).
            event_id = data_id
            event_cls_id = None
            event_td = el.locator("td.event")
            if event_td.count() > 0:
                cls = event_td.first.get_attribute("class") or ""
                m = re.search(r"event-([A-Za-z0-9_\-]+)", cls)
                if m:
                    event_cls_id = m.group(1)

            parts = parse_market(market_raw or "")
            _, book_display = normalize_bookmaker(bookmaker or "")

            vb = ValueBet(
                filter_id=filt.id,
                filter_name=filt.name,
                event_id=event_id,
                sport=sport,
                event=normalize_event(event or "") or None,
                competition=tournament,
                bookmaker=book_display or None,
                market_raw=market_raw,
                market_type=parts.market_type,
                period=parts.period,
                line=parts.line,
                selection=parts.selection,
                team=parts.team,
                odds=odds,
                fair_probability=probability,
                site_overvalue=site_ov,
                captured_at=now,
                raw={
                    "data_start_at": start_at,
                    "signature": el.get_attribute("data-signature"),
                    "event_class_id": event_cls_id,
                },
            )

            if start_at and start_at.isdigit():
                try:
                    vb.event_datetime = datetime.fromtimestamp(int(start_at), tz=timezone.utc)
                except (ValueError, OSError):
                    pass

            vr = validate_valuebet(
                odds=vb.odds,
                probability=vb.fair_probability,
                site_overvalue=vb.site_overvalue,
                market_type=vb.market_type,
                settings=settings,
            )
            vb.validation_status = vr.status
            vb.validation_reasons = vr.reasons
            vb.calculated_ev = vr.calculated_ev
            vb.identity_hash = valuebet_identity_hash(vb)
            stats.parsed += 1  # DOM row extracted OK (threshold filter is separate)

            # threshold filters (post-scrape safety net — not parse failures)
            if filt.min_overvalue is not None and (vb.site_overvalue is None or vb.site_overvalue < filt.min_overvalue):
                continue
            if filt.min_odds is not None and (vb.odds is None or vb.odds < filt.min_odds):
                continue
            if filt.max_odds is not None and (vb.odds is None or vb.odds > filt.max_odds):
                continue

            out.append(vb)
        except Exception as e:
            stats.failed += 1
            log.warning("Failed to parse valuebet row %s: %s", i, e)

    return out, stats
