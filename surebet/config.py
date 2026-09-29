"""Runtime configuration from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    surebet_username: str
    surebet_password: str
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_message_thread_id: str | None = None  # forum topic id (e.g. Arbitrage)
    base_url: str = "https://pt.surebet.com"
    valuebet_validation_tolerance_pp: Decimal = Decimal("0.5")
    arbitrage_epsilon: Decimal = Decimal("0.001")
    arbitrage_profit_tolerance_pp: Decimal = Decimal("0.25")
    resend_odds_change: Decimal = Decimal("0.05")
    resend_overvalue_change_pp: Decimal = Decimal("0.5")
    resend_profit_change_pp: Decimal = Decimal("0.5")
    opportunity_expiry_minutes: int = 60
    error_alert_cooldown_minutes: int = 180
    min_parse_success_rate: Decimal = Decimal("0.70")
    max_pages: int = 1
    display_timezone: str = "Europe/Lisbon"
    state_path: Path = ROOT / "data" / "state.json"
    filters_path: Path = ROOT / "filters.json"
    screenshots_dir: Path = ROOT / "screenshots"
    debug_dir: Path = ROOT / "debug"


def _dec(name: str, default: str) -> Decimal:
    return Decimal(os.getenv(name, default))


def load_settings(*, require_credentials: bool = True) -> Settings:
    user = os.getenv("SUREBET_USERNAME", "")
    password = os.getenv("SUREBET_PASSWORD", "")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    thread = os.getenv("TELEGRAM_MESSAGE_THREAD_ID", "").strip() or None
    has_storage = bool(
        os.getenv("SUREBET_STORAGE_STATE_B64", "").strip()
        or os.getenv("SUREBET_STORAGE_STATE_PATH", "").strip()
        or os.getenv("SUREBET_STORAGE_STATE", "").strip()
        or (ROOT / "storage_state.json").is_file()
    )
    if require_credentials and (not user or not password) and not has_storage:
        raise RuntimeError(
            "Need SUREBET_USERNAME/PASSWORD or a storage_state "
            "(SUREBET_STORAGE_STATE_B64 / storage_state.json)"
        )
    return Settings(
        surebet_username=user,
        surebet_password=password,
        telegram_bot_token=token,
        telegram_chat_id=chat,
        telegram_message_thread_id=thread,
        base_url=os.getenv("SUREBET_BASE_URL", "https://pt.surebet.com").rstrip("/"),
        valuebet_validation_tolerance_pp=_dec("VALUEBET_VALIDATION_TOLERANCE_PP", "0.5"),
        arbitrage_epsilon=_dec("ARBITRAGE_EPSILON", "0.001"),
        arbitrage_profit_tolerance_pp=_dec("ARBITRAGE_PROFIT_TOLERANCE_PP", "0.25"),
        resend_odds_change=_dec("RESEND_ODDS_CHANGE", "0.05"),
        resend_overvalue_change_pp=_dec("RESEND_OVERVALUE_CHANGE_PP", "0.5"),
        resend_profit_change_pp=_dec("RESEND_PROFIT_CHANGE_PP", "0.5"),
        opportunity_expiry_minutes=int(os.getenv("OPPORTUNITY_EXPIRY_MINUTES", "60")),
        error_alert_cooldown_minutes=int(os.getenv("ERROR_ALERT_COOLDOWN_MINUTES", "180")),
        min_parse_success_rate=_dec("MIN_PARSE_SUCCESS_RATE", "0.70"),
        max_pages=int(os.getenv("MAX_PAGES", "1")),
        display_timezone=os.getenv("DISPLAY_TIMEZONE", "Europe/Lisbon"),
    )
