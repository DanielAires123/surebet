#!/usr/bin/env python3
"""SureBet Monitor CLI."""

from __future__ import annotations

import argparse
import logging
import sys
from decimal import Decimal

from surebet.config import load_settings
from surebet.monitor import run_monitor
from surebet.session import DEFAULT_STORAGE_PATH, export_storage_interactive
from surebet.state import StateStore
from telegram.bot import TelegramBot
from telegram.callbacks import poll_callbacks


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SureBet monitor (Playwright DOM)")
    p.add_argument("--dry-run", action="store_true", help="Scrape/validate but do not send Telegram or mark sent")
    p.add_argument("--debug", action="store_true", help="Save debug screenshots under debug/")
    p.add_argument("--filter", dest="filter_id", default=None, help="Process only this filter id")
    p.add_argument("--test-telegram", action="store_true", help="Send Telegram test message and exit")
    p.add_argument("--headed", action="store_true", help="Run Chromium headed (local debug)")
    p.add_argument(
        "--export-storage",
        action="store_true",
        help="Headed login (manual CAPTCHA OK) then save storage_state.json + print base64 for GitHub",
    )
    p.add_argument(
        "--poll-callbacks",
        action="store_true",
        help="Poll Telegram for Apostei/Não button presses and update bet ledger",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="[%(levelname)s] %(message)s",
    )

    if args.test_telegram:
        settings = load_settings(require_credentials=False)
        bot = TelegramBot(settings.telegram_bot_token, settings.telegram_chat_id)
        ok = True
        for label, tid in (
            ("Arbitrage", settings.telegram_arbitrage_thread_id),
            ("Value Bets", settings.telegram_valuebet_thread_id),
        ):
            if not tid:
                logging.warning("No thread id configured for %s — skip", label)
                continue
            logging.info("Testing Telegram → %s (thread %s)", label, tid)
            if not bot.test_connection(message_thread_id=tid):
                ok = False
        return 0 if ok else 1

    if args.poll_callbacks:
        settings = load_settings(require_credentials=False)
        state = StateStore(settings.state_path)
        state.load()
        return poll_callbacks(
            settings=settings,
            state=state,
            dry_run=args.dry_run,
            default_stake=Decimal("10"),
        )

    if args.export_storage:
        settings = load_settings(require_credentials=False)
        export_storage_interactive(settings, DEFAULT_STORAGE_PATH)
        return 0

    settings = load_settings(require_credentials=True)
    return run_monitor(
        settings=settings,
        filter_id=args.filter_id,
        debug=args.debug,
        dry_run=args.dry_run,
        headless=not args.headed,
    )


if __name__ == "__main__":
    sys.exit(main())
