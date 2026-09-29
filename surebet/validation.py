"""Mathematical validation — conservative."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional, Sequence

from surebet.config import Settings
from surebet.models import (
    ArbOutcome,
    MarketParts,
    StakeLeg,
    StakePlan,
    ValidationResult,
    ValidationStatus,
)
from surebet.percent import percentage_points_difference

CENT = Decimal("0.01")


def calculate_valuebet_ev(odds: Decimal, probability: Decimal) -> Decimal:
    return odds * probability - Decimal(1)


def validate_valuebet(
    *,
    odds: Optional[Decimal],
    probability: Optional[Decimal],
    site_overvalue: Optional[Decimal],
    market_type: str = "unknown",
    settings: Optional[Settings] = None,
) -> ValidationResult:
    reasons: list[str] = []
    if odds is None or odds <= 1:
        return ValidationResult(status=ValidationStatus.INVALID, reasons=["Invalid or missing odds"])
    if probability is None:
        return ValidationResult(
            status=ValidationStatus.UNVERIFIED,
            reasons=["Independent probability not available"],
        )
    if not (Decimal(0) < probability <= Decimal(1)):
        return ValidationResult(status=ValidationStatus.INVALID, reasons=["Probability out of range (0,1]"])

    ev = calculate_valuebet_ev(odds, probability)
    if ev <= 0:
        return ValidationResult(
            status=ValidationStatus.INVALID,
            reasons=["Calculated EV <= 0"],
            calculated_ev=ev,
        )

    if site_overvalue is None:
        return ValidationResult(
            status=ValidationStatus.UNVERIFIED,
            reasons=["Site overvalue missing; EV positive but not cross-checked"],
            calculated_ev=ev,
        )

    tol = (settings.valuebet_validation_tolerance_pp if settings else Decimal("0.5"))
    diff_pp = percentage_points_difference(ev, site_overvalue)
    if diff_pp > tol:
        return ValidationResult(
            status=ValidationStatus.UNVERIFIED,
            reasons=[f"Site overvalue differs from EV by {diff_pp}pp (tol {tol}pp)"],
            calculated_ev=ev,
        )

    # market_type unknown is OK for valuebet if odds+probability valid
    return ValidationResult(status=ValidationStatus.VALIDATED, reasons=[], calculated_ev=ev)


def _inverse_sum(odds_list: Sequence[Decimal]) -> Decimal:
    total = Decimal(0)
    for o in odds_list:
        if o is None or o <= 0:
            raise ValueError("invalid odds")
        total += Decimal(1) / o
    return total


def markets_compatible(parts: Sequence[MarketParts]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not parts:
        return False, ["No market parts"]
    if any(p.market_type == "unknown" for p in parts):
        return False, ["Market type unknown — cannot prove settlement compatibility"]

    types = {p.market_type for p in parts}
    if len(types) != 1:
        return False, [f"Mixed market types: {sorted(types)}"]

    periods = {p.period for p in parts}
    if len(periods) != 1:
        return False, [f"Incompatible periods: {sorted(x for x in periods if x)}"]

    lines = {p.line for p in parts}
    if None not in lines and len(lines) > 1:
        # over/under same line OK; different lines not
        mt = next(iter(types))
        sels = {p.selection for p in parts}
        if mt in {"total", "team_total", "corners", "team_corners", "shots", "shots_on_target", "cards", "asian_total"}:
            if sels == {"over", "under"} and len(lines) == 1:
                pass
            elif len(lines) > 1:
                return False, [f"Incompatible lines: {sorted(str(x) for x in lines)}"]
        elif len(lines) > 1:
            return False, [f"Incompatible lines: {sorted(str(x) for x in lines)}"]

    mt = next(iter(types))
    sels = [p.selection for p in parts]
    if mt in {"total", "team_total", "corners", "team_corners", "shots", "shots_on_target", "cards"}:
        if set(sels) != {"over", "under"} or len(sels) != 2:
            return False, ["Totals require complementary over/under covering the same line"]
        if parts[0].line != parts[1].line:
            return False, ["Over/under lines differ"]
    elif mt == "1x2":
        if set(sels) != {"home", "draw", "away"} or len(sels) != 3:
            return False, ["1X2 requires home/draw/away coverage"]
    elif mt == "both_to_score":
        if set(sels) != {"yes", "no"} or len(sels) != 2:
            return False, ["BTTS requires yes/no"]
    else:
        # handicap and others: cannot prove without more rules
        return False, [f"No settlement proof rules for market_type={mt}"]

    # duplicate selections
    if len(sels) != len(set(sels)):
        return False, ["Duplicate outcomes"]

    return True, reasons


def validate_arbitrage(
    *,
    outcomes: Sequence[ArbOutcome],
    site_profit: Optional[Decimal],
    settings: Optional[Settings] = None,
) -> ValidationResult:
    if len(outcomes) < 2:
        return ValidationResult(status=ValidationStatus.INVALID, reasons=["Need at least 2 outcomes"])

    odds = [o.odds for o in outcomes]
    if any(o is None or o <= 1 for o in odds):
        return ValidationResult(status=ValidationStatus.INVALID, reasons=["Invalid odds in outcomes"])

    try:
        inv = _inverse_sum(odds)
    except ValueError:
        return ValidationResult(status=ValidationStatus.INVALID, reasons=["Invalid odds"])

    eps = settings.arbitrage_epsilon if settings else Decimal("0.001")
    if inv >= Decimal(1) - eps:
        return ValidationResult(
            status=ValidationStatus.INVALID,
            reasons=[f"inverse_sum={inv} not < 1-eps"],
            inverse_probability_sum=inv,
        )

    roi = (Decimal(1) / inv) - Decimal(1)

    parts = [o.market_parts or MarketParts(market_raw=o.market_raw) for o in outcomes]
    ok, reasons = markets_compatible(parts)
    if not ok:
        return ValidationResult(
            status=ValidationStatus.UNVERIFIED,
            reasons=reasons,
            calculated_profit=roi,
            inverse_probability_sum=inv,
        )

    # same event check when available
    events = {normalize_loose(o.event) for o in outcomes if o.event}
    if len(events) > 1:
        return ValidationResult(
            status=ValidationStatus.UNVERIFIED,
            reasons=[f"Outcomes reference different events: {sorted(events)}"],
            calculated_profit=roi,
            inverse_probability_sum=inv,
        )

    if site_profit is not None:
        tol = settings.arbitrage_profit_tolerance_pp if settings else Decimal("0.25")
        diff = percentage_points_difference(roi, site_profit)
        if diff > tol:
            return ValidationResult(
                status=ValidationStatus.UNVERIFIED,
                reasons=[f"Site profit differs from ROI by {diff}pp (tol {tol}pp)"],
                calculated_profit=roi,
                inverse_probability_sum=inv,
            )

    return ValidationResult(
        status=ValidationStatus.VALIDATED,
        reasons=[],
        calculated_profit=roi,
        inverse_probability_sum=inv,
    )


def normalize_loose(s: Optional[str]) -> str:
    from surebet.normalization import normalize_event

    return normalize_event(s or "").casefold()


def calculate_stakes(odds_list: Sequence[Decimal], total: Decimal) -> StakePlan:
    inv = _inverse_sum(odds_list)
    raw_stakes = [total * ((Decimal(1) / o) / inv) for o in odds_list]
    rounded = [s.quantize(CENT, rounding=ROUND_HALF_UP) for s in raw_stakes]
    # adjust last stake to match total after rounding
    drift = total - sum(rounded)
    rounded[-1] = (rounded[-1] + drift).quantize(CENT, rounding=ROUND_HALF_UP)
    legs = []
    payouts = []
    for o, st in zip(odds_list, rounded):
        pay = (st * o).quantize(CENT, rounding=ROUND_HALF_UP)
        payouts.append(pay)
        legs.append(StakeLeg(bookmaker="", odds=o, stake=st, payout=pay))
    guaranteed = min(payouts)
    profit = guaranteed - total
    roi = profit / total if total else Decimal(0)
    return StakePlan(
        total=total,
        legs=legs,
        guaranteed_payout=guaranteed,
        profit=profit,
        roi=roi,
    )


def attach_bookmakers(plan: StakePlan, bookmakers: Iterable[str]) -> StakePlan:
    books = list(bookmakers)
    new_legs = []
    for i, leg in enumerate(plan.legs):
        new_legs.append(leg.model_copy(update={"bookmaker": books[i] if i < len(books) else ""}))
    return plan.model_copy(update={"legs": new_legs})
