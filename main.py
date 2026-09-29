#!/usr/bin/env python3
"""SureBet Monitor CLI."""

from __future__ import annotations

import argparse
import logging
import sys

from surebet.config import load_settings
from surebet.monitor import run_monitor
from surebet.session import DEFAULT_STORAGE_PATH, export_storage_interactive
from telegram.bot import TelegramBot


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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="[%(levelname)s] %(message)s",
    )

    if args.test_telegram:
        settings = load_settings(require_credentials=False)
        bot = TelegramBot(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            message_thread_id=settings.telegram_message_thread_id,
        )
        ok = bot.test_connection()
        return 0 if ok else 1

    if args.export_storage:
        # credentials optional — user logs in manually in the browser
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
