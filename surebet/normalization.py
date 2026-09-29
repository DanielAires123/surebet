"""Normalization helpers — conservative, no aggressive fuzzy matching."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Optional

from surebet.models import MarketParts

_DASHES = re.compile(r"[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]+")
_WS = re.compile(r"\s+")


def normalize_event(name: str) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFKC", name)
    text = _DASHES.sub("–", text)
    text = _WS.sub(" ", text).strip()
    return text


def normalize_bookmaker(name: str) -> tuple[str, str]:
    display = _WS.sub(" ", (name or "").strip())
    canonical = display.casefold()
    canonical = re.sub(r"\s*\([^)]*\)\s*", " ", canonical)
    canonical = _WS.sub(" ", canonical).strip()
    return canonical, display


def _num(token: str) -> Optional[Decimal]:
    try:
        return Decimal(token.replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def parse_market(raw: str) -> MarketParts:
    """Best-effort market parse. Unknown → market_type=unknown (never invent settlement)."""
    raw = _WS.sub(" ", (raw or "").strip())
    if not raw:
        return MarketParts(market_raw="", market_type="unknown")

    lower = raw.casefold()
    period = "full_time"
    if any(x in lower for x in ("1ª metade", "1a metade", "1º tempo", "1o tempo", "1st half", "1ª metade")):
        period = "first_half"
    elif any(x in lower for x in ("2ª metade", "2a metade", "2º tempo", "2nd half")):
        period = "second_half"
    elif any(x in lower for x in ("1º período", "1o período", "1st period", "1º periodo")):
        period = "first_period"
    elif any(x in lower for x in ("2º período", "2o período", "2nd period")):
        period = "second_period"
    elif "tempo extra" in lower or "overtime" in lower:
        period = "overtime"
    elif any(x in lower for x in ("1º set", "1o set", "1st set")):
        period = "first_set"

    team: Optional[int] = None
    if re.search(r"1[ºoªa]?\s*o\s*time|1st\s*team|home", lower):
        team = 1
    elif re.search(r"2[ºoªa]?\s*o\s*time|2nd\s*team|away", lower):
        team = 2

    selection: Optional[str] = None
    line: Optional[Decimal] = None
    market_type = "unknown"

    # Asian / complex → keep unknown unless clearly simple total/handicap labels we understand
    if any(x in lower for x in ("asian", "asiático", "dnb", "hnb", "draw no bet", "lay (", "dead heat")):
        return MarketParts(
            market_raw=raw,
            market_type="unknown",
            period=period,
            team=team,
        )

    m = re.search(
        r"(acima|over|abaixo|under|total\s*[≥>=]|total\s*[≤<=])\s*([0-9]+(?:[.,][0-9]+)?)",
        lower,
        re.I,
    )
    if m:
        sel_raw, line_s = m.group(1), m.group(2)
        line = _num(line_s)
        if sel_raw.startswith("abaixo") or sel_raw.startswith("under") or "≤" in sel_raw or "<=" in sel_raw:
            selection = "under"
        else:
            selection = "over"
        if "escanteio" in lower or "corner" in lower:
            market_type = "team_corners" if team else "corners"
        elif "chute" in lower or "shot" in lower:
            market_type = "shots_on_target" if "alvo" in lower or "on target" in lower else "shots"
        elif "cart" in lower or "card" in lower:
            market_type = "cards"
        elif team:
            market_type = "team_total"
        else:
            market_type = "total"
        return MarketParts(
            market_raw=raw,
            market_type=market_type,
            period=period,
            line=line,
            selection=selection,
            team=team,
        )

    hm = re.search(r"h([12])\s*\(\s*([+-]?[0-9]+(?:[.,][0-9]+)?)\s*\)", lower)
    if hm:
        team = int(hm.group(1))
        line = _num(hm.group(2))
        return MarketParts(
            market_raw=raw,
            market_type="handicap",
            period=period,
            line=line,
            selection=f"h{team}",
            team=team,
        )

    if re.fullmatch(r"[12x]|home|away|draw|empate", lower.strip()):
        sel = {"1": "home", "2": "away", "x": "draw", "home": "home", "away": "away", "draw": "draw", "empate": "draw"}[
            lower.strip()
        ]
        return MarketParts(market_raw=raw, market_type="1x2", period=period, selection=sel)

    if "ambos marcam" in lower or "both teams" in lower or "btts" in lower:
        selection = "no" if "não" in lower or " no" in lower or lower.endswith("não") else "yes"
        return MarketParts(market_raw=raw, market_type="both_to_score", period=period, selection=selection)

    return MarketParts(market_raw=raw, market_type="unknown", period=period, team=team)
