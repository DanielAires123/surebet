"""Domain models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ValidationStatus(str, Enum):
    VALIDATED = "validated"
    UNVERIFIED = "unverified"
    INVALID = "invalid"


class ResultsState(str, Enum):
    LOADING = "LOADING"
    RESULTS = "RESULTS"
    EMPTY = "EMPTY"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


class ScreenshotMode(str, Enum):
    NEVER = "never"
    ON_NEW = "on_new"
    ON_CHANGE = "on_change"
    ALWAYS = "always"
    ON_ERROR = "on_error"


class MarketParts(BaseModel):
    market_raw: str
    market_type: str = "unknown"
    period: Optional[str] = None
    line: Optional[Decimal] = None
    selection: Optional[str] = None
    team: Optional[int] = None
    participant: Optional[str] = None


class ValidationResult(BaseModel):
    status: ValidationStatus
    reasons: list[str] = Field(default_factory=list)
    calculated_ev: Optional[Decimal] = None
    calculated_profit: Optional[Decimal] = None
    inverse_probability_sum: Optional[Decimal] = None


class ArbOutcome(BaseModel):
    bookmaker: str
    selection: Optional[str] = None
    market_raw: str
    odds: Decimal
    sport: Optional[str] = None
    event: Optional[str] = None
    tournament: Optional[str] = None
    market_parts: Optional[MarketParts] = None
    bookmaker_url: Optional[str] = None
    event_url: Optional[str] = None
    odds_url: Optional[str] = None


class StakeLeg(BaseModel):
    bookmaker: str
    odds: Decimal
    stake: Decimal
    payout: Decimal


class StakePlan(BaseModel):
    total: Decimal
    legs: list[StakeLeg]
    guaranteed_payout: Decimal
    profit: Decimal
    roi: Decimal


class ValueBet(BaseModel):
    source: Literal["valuebet"] = "valuebet"
    classification: list[str] = Field(default_factory=lambda: ["valuebet"])
    validation_status: ValidationStatus = ValidationStatus.UNVERIFIED
    validation_reasons: list[str] = Field(default_factory=list)

    filter_id: str
    filter_name: str

    event_id: Optional[str] = None
    sport: Optional[str] = None
    event: Optional[str] = None
    competition: Optional[str] = None
    event_datetime: Optional[datetime] = None

    bookmaker: Optional[str] = None
    market_raw: Optional[str] = None
    market_type: str = "unknown"
    period: Optional[str] = None
    line: Optional[Decimal] = None
    selection: Optional[str] = None
    participant: Optional[str] = None
    team: Optional[int] = None

    odds: Optional[Decimal] = None
    fair_probability: Optional[Decimal] = None
    site_overvalue: Optional[Decimal] = None
    calculated_ev: Optional[Decimal] = None

    bookmaker_url: Optional[str] = None
    event_url: Optional[str] = None
    odds_url: Optional[str] = None

    identity_hash: Optional[str] = None
    content_hash: Optional[str] = None  # cross-filter dedupe (no filter_id)
    captured_at: Optional[datetime] = None
    raw: dict[str, Any] = Field(default_factory=dict)


class Arbitrage(BaseModel):
    source: Literal["surebet"] = "surebet"
    classification: list[str] = Field(default_factory=lambda: ["arbitrage"])
    validation_status: ValidationStatus = ValidationStatus.UNVERIFIED
    validation_reasons: list[str] = Field(default_factory=list)

    filter_id: str
    filter_name: str

    event_id: Optional[str] = None
    sport: Optional[str] = None
    event: Optional[str] = None
    competition: Optional[str] = None
    event_datetime: Optional[datetime] = None

    market_type: str = "unknown"
    period: Optional[str] = None
    line: Optional[Decimal] = None

    site_profit: Optional[Decimal] = None
    calculated_profit: Optional[Decimal] = None
    inverse_probability_sum: Optional[Decimal] = None

    outcomes: list[ArbOutcome] = Field(default_factory=list)
    stakes: Optional[StakePlan] = None

    identity_hash: Optional[str] = None
    content_hash: Optional[str] = None
    captured_at: Optional[datetime] = None
    raw: dict[str, Any] = Field(default_factory=dict)


class FilterConfig(BaseModel):
    id: str
    name: str
    surebet_filter_id: str
    source: Literal["valuebet", "surebet"]
    enabled: bool = True
    send_results: bool = True
    screenshot_mode: ScreenshotMode = ScreenshotMode.ON_NEW
    min_overvalue: Optional[Decimal] = None
    min_profit: Optional[Decimal] = None
    min_odds: Optional[Decimal] = None
    max_odds: Optional[Decimal] = None
    sports: list[str] = Field(default_factory=list)
    bookmakers: list[str] = Field(default_factory=list)


class GlobalConfig(BaseModel):
    send_only_validated: bool = True
    calculate_stakes: bool = True
    default_total_stake: Decimal = Decimal("100")
    currency: str = "EUR"
    display_timezone: str = "Europe/Lisbon"
    allow_live_events: bool = False
    revalidate_before_send: bool = True
    telegram_max_alerts_per_run: int = 30


class AppConfig(BaseModel):
    global_: GlobalConfig = Field(alias="global")
    filters: list[FilterConfig]

    model_config = {"populate_by_name": True}


class OpportunityState(BaseModel):
    identity_hash: str
    content_hash: Optional[str] = None
    last_odds: Optional[list[Decimal]] = None
    last_profit: Optional[Decimal] = None
    last_overvalue: Optional[Decimal] = None
    last_probability: Optional[Decimal] = None
    last_seen_at: Optional[datetime] = None
    last_sent_at: Optional[datetime] = None
    validation_status: Optional[str] = None


class PendingAlert(BaseModel):
    """Maps Telegram message → opportunity for Apostei/Não callbacks."""

    short_id: str  # first 16 of identity_hash (callback_data budget)
    identity_hash: str
    source: Literal["valuebet", "surebet"]
    filter_id: str
    filter_name: str
    event: Optional[str] = None
    sport: Optional[str] = None
    market_raw: Optional[str] = None
    bookmaker: Optional[str] = None
    odds: Optional[list[Decimal]] = None
    roi: Optional[Decimal] = None
    chat_id: str
    message_id: int
    thread_id: Optional[str] = None
    created_at: Optional[datetime] = None


class TrackedBet(BaseModel):
    """User-confirmed bet — Bzzoiro settle comes later."""

    id: str
    identity_hash: str
    source: Literal["valuebet", "surebet"]
    status: Literal["open", "skipped", "settled"] = "open"
    filter_id: str = ""
    filter_name: str = ""
    event: Optional[str] = None
    sport: Optional[str] = None
    market_raw: Optional[str] = None
    bookmaker: Optional[str] = None
    odds: Optional[list[Decimal]] = None
    roi: Optional[Decimal] = None
    stake: Optional[Decimal] = None
    currency: str = "EUR"
    telegram_message_id: Optional[int] = None
    confirmed_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None
    outcome: Optional[Literal["won", "lost", "void", "push"]] = None
    profit: Optional[Decimal] = None


class ParseStats(BaseModel):
    raw: int = 0
    parsed: int = 0
    failed: int = 0

    @property
    def success_rate(self) -> Decimal:
        if self.raw == 0:
            return Decimal("1")
        return Decimal(self.parsed) / Decimal(self.raw)


class FilterRunStats(BaseModel):
    filter_id: str
    filter_name: str
    ok: bool = True
    error: Optional[str] = None
    raw: int = 0
    parsed: int = 0
    validated: int = 0
    unverified: int = 0
    invalid: int = 0
    new: int = 0
    changed: int = 0
    duplicate: int = 0
    sent: int = 0
    screenshots: int = 0


class RunStats(BaseModel):
    filters_configured: int = 0
    filters_processed: int = 0
    successful: int = 0
    failed: int = 0
    raw: int = 0
    parsed: int = 0
    validated: int = 0
    unverified: int = 0
    invalid: int = 0
    new: int = 0
    changed: int = 0
    duplicate: int = 0
    sent: int = 0
    screenshots: int = 0
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    per_filter: list[FilterRunStats] = Field(default_factory=list)
