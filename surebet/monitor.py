"""Per-run monitor orchestration."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page

from surebet.arbitrage import extract_arbitrages
from surebet.auth import detect_protections, login
from surebet.browser import BrowserSession
from surebet.config import Settings
from surebet.deduplication import should_resend_arbitrage, should_resend_valuebet
from surebet.exceptions import (
    AntiBotDetected,
    AuthFailed,
    CaptchaDetected,
    ParserOrLayoutChanged,
    SurebetMonitorError,
)
from surebet.filters import enabled_filters, load_filters
from surebet.models import (
    AppConfig,
    FilterConfig,
    FilterRunStats,
    ResultsState,
    RunStats,
    ScreenshotMode,
    ValidationStatus,
)
from surebet.navigation import (
    open_product,
    select_filter,
    take_results_screenshot,
    wait_for_results,
)
from surebet.state import StateStore
from surebet.valuebets import extract_valuebets
from telegram.bot import TelegramBot
from telegram.formatting import format_arbitrage_alert, format_error_alert, format_valuebet_alert

log = logging.getLogger(__name__)


def _maybe_screenshot(
    page: Page,
    filt: FilterConfig,
    path: Path,
    *,
    is_new: bool,
    is_changed: bool,
    is_error: bool,
) -> bool:
    mode = filt.screenshot_mode
    if mode == ScreenshotMode.NEVER:
        return False
    if mode == ScreenshotMode.ALWAYS:
        take_results_screenshot(page, str(path), filt.source)
        return True
    if mode == ScreenshotMode.ON_ERROR and is_error:
        take_results_screenshot(page, str(path), filt.source)
        return True
    if mode == ScreenshotMode.ON_NEW and is_new:
        take_results_screenshot(page, str(path), filt.source)
        return True
    if mode == ScreenshotMode.ON_CHANGE and (is_new or is_changed):
        take_results_screenshot(page, str(path), filt.source)
        return True
    return False


def process_filter(
    page: Page,
    filt: FilterConfig,
    *,
    settings: Settings,
    app: AppConfig,
    state: StateStore,
    bot: TelegramBot,
    dry_run: bool,
) -> FilterRunStats:
    stats = FilterRunStats(filter_id=filt.id, filter_name=filt.name)
    log.info("Filter: %s", filt.name)

    open_product(page, settings, filt.source)
    select_filter(page, filt.surebet_filter_id, filt.name)
    result_state = wait_for_results(page, filt.source)

    if result_state == ResultsState.TIMEOUT:
        raise TimeoutError(f"Results timeout for {filt.name}")
    if result_state == ResultsState.ERROR:
        raise RuntimeError(f"Results error for {filt.name}")
    if result_state == ResultsState.EMPTY:
        log.info("Raw: 0 (empty)")
        return stats

    g = app.global_
    if filt.source == "valuebet":
        items, parse_stats = extract_valuebets(page, filt, settings)
    else:
        items, parse_stats = extract_arbitrages(
            page, filt, settings, total_stake=g.default_total_stake if g.calculate_stakes else Decimal("0")
        )

    stats.raw = parse_stats.raw
    stats.parsed = parse_stats.parsed
    log.info("Raw: %s", parse_stats.raw)
    log.info("Parsed: %s", parse_stats.parsed)

    if parse_stats.raw > 0 and parse_stats.success_rate < settings.min_parse_success_rate:
        # DOM has rows but almost nothing parsed
        raise ParserOrLayoutChanged(
            f"parse_success_rate={parse_stats.success_rate} < {settings.min_parse_success_rate}"
        )

    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)

    for item in items:
        if item.validation_status == ValidationStatus.VALIDATED:
            stats.validated += 1
        elif item.validation_status == ValidationStatus.UNVERIFIED:
            stats.unverified += 1
        else:
            stats.invalid += 1

        if g.send_only_validated and item.validation_status != ValidationStatus.VALIDATED:
            continue
        if not filt.send_results:
            continue

        # live filter
        if not g.allow_live_events and item.event_datetime and item.event_datetime <= datetime.now(timezone.utc):
            continue

        prev = state.get(item.identity_hash or "")
        if filt.source == "valuebet":
            send, reason = should_resend_valuebet(
                prev,
                item,
                odds_threshold=settings.resend_odds_change,
                overvalue_pp_threshold=settings.resend_overvalue_change_pp,
                expiry_minutes=settings.opportunity_expiry_minutes,
            )
        else:
            send, reason = should_resend_arbitrage(
                prev,
                item,
                odds_threshold=settings.resend_odds_change,
                profit_pp_threshold=settings.resend_profit_change_pp,
                expiry_minutes=settings.opportunity_expiry_minutes,
            )

        if reason == "new":
            stats.new += 1
        elif reason == "changed" or reason == "expired_reappear":
            stats.changed += 1
        else:
            stats.duplicate += 1

        if not send:
            if filt.source == "valuebet":
                state.touch_valuebet(item, sent=False)
            else:
                state.touch_arbitrage(item, sent=False)
            continue

        # ponytail: soft revalidate — skip if record vanished from DOM
        if g.revalidate_before_send and item.event_id:
            still = page.locator(f'tbody[data-id="{item.event_id}"]')
            if still.count() == 0:
                continue

        if filt.source == "valuebet":
            text = format_valuebet_alert(item, tz=g.display_timezone)
        else:
            text = format_arbitrage_alert(item, tz=g.display_timezone, currency=g.currency)

        shot_path = settings.screenshots_dir / f"{item.identity_hash[:16]}.png"
        took = _maybe_screenshot(
            page,
            filt,
            shot_path,
            is_new=reason == "new",
            is_changed=reason in {"changed", "expired_reappear"},
            is_error=False,
        )

        ok = bot.send_message(text)
        if ok and took and shot_path.exists():
            bot.send_photo(shot_path, caption=filt.name)
            stats.screenshots += 1
            try:
                shot_path.unlink(missing_ok=True)
            except OSError:
                pass

        if ok:
            stats.sent += 1
            if filt.source == "valuebet":
                state.touch_valuebet(item, sent=not dry_run)
            else:
                state.touch_arbitrage(item, sent=not dry_run)
        else:
            if filt.source == "valuebet":
                state.touch_valuebet(item, sent=False)
            else:
                state.touch_arbitrage(item, sent=False)

    log.info("Validated: %s", stats.validated)
    log.info("Unverified: %s", stats.unverified)
    log.info("New: %s", stats.new)
    log.info("Sent: %s", stats.sent)
    return stats


def run_monitor(
    *,
    settings: Settings,
    filter_id: Optional[str] = None,
    debug: bool = False,
    dry_run: bool = False,
    headless: bool = True,
) -> int:
    started = time.time()
    app = load_filters(settings.filters_path)
    filters = enabled_filters(app, filter_id)
    state = StateStore(settings.state_path)
    state.load()

    bot = TelegramBot(
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        message_thread_id=settings.telegram_message_thread_id,
        max_alerts_per_run=app.global_.telegram_max_alerts_per_run,
        dry_run=dry_run,
    )

    run = RunStats(filters_configured=len(app.filters), filters_processed=0)
    log.info("Starting monitor")

    try:
        with BrowserSession(settings, debug=debug, headless=headless) as session:
            assert session.page is not None
            page = session.page
            if debug:
                session.screenshot("before_login.png")
            login(page, settings)
            if debug:
                session.screenshot("after_login.png")
            log.info("Login successful")

            for filt in filters:
                run.filters_processed += 1
                try:
                    detect_protections(page)
                    fr = process_filter(
                        page,
                        filt,
                        settings=settings,
                        app=app,
                        state=state,
                        bot=bot,
                        dry_run=dry_run,
                    )
                    fr.ok = True
                    run.successful += 1
                except (CaptchaDetected, AntiBotDetected) as e:
                    run.failed += 1
                    run.errors.append(str(e))
                    _alert_error(bot, state, settings, str(e))
                    run.duration_seconds = time.time() - started
                    _log_summary(run)
                    if not dry_run:
                        state.save()
                    return 2
                except Exception as e:
                    log.exception("Filter %s failed: %s", filt.name, e)
                    fr = FilterRunStats(filter_id=filt.id, filter_name=filt.name, ok=False, error=str(e))
                    run.failed += 1
                    run.errors.append(f"{filt.id}: {e}")
                    continue

                run.per_filter.append(fr)
                run.raw += fr.raw
                run.parsed += fr.parsed
                run.validated += fr.validated
                run.unverified += fr.unverified
                run.invalid += fr.invalid
                run.new += fr.new
                run.changed += fr.changed
                run.duplicate += fr.duplicate
                run.sent += fr.sent
                run.screenshots += fr.screenshots

    except AuthFailed as e:
        log.error("AUTH_FAILED: %s", e)
        _alert_error(bot, state, settings, f"AUTH_FAILED: {e}")
        return 1
    except (CaptchaDetected, AntiBotDetected) as e:
        log.error("%s", e)
        _alert_error(bot, state, settings, str(e))
        return 2
    except SurebetMonitorError as e:
        log.error("%s", e)
        _alert_error(bot, state, settings, str(e))
        return 1

    if not dry_run:
        state.save()

    run.duration_seconds = time.time() - started
    _log_summary(run)

    if filters and run.failed == len(filters):
        return 1
    return 0


def _alert_error(bot: TelegramBot, state: StateStore, settings: Settings, reason: str) -> None:
    h = hashlib.sha256(reason.encode()).hexdigest()
    if state.should_send_error(h, settings.error_alert_cooldown_minutes):
        if bot.send_message(format_error_alert(reason)):
            state.mark_error_sent(h)
            state.save()


def _log_summary(run: RunStats) -> None:
    log.info("===== SUMMARY =====")
    log.info("Filters configured: %s", run.filters_configured)
    log.info("Filters processed: %s", run.filters_processed)
    log.info("Successful: %s", run.successful)
    log.info("Failed: %s", run.failed)
    log.info("Raw: %s", run.raw)
    log.info("Parsed: %s", run.parsed)
    log.info("Validated: %s", run.validated)
    log.info("Unverified: %s", run.unverified)
    log.info("Invalid: %s", run.invalid)
    log.info("New: %s", run.new)
    log.info("Changed: %s", run.changed)
    log.info("Duplicate: %s", run.duplicate)
    log.info("Sent: %s", run.sent)
    log.info("Screenshots: %s", run.screenshots)
    log.info("Errors: %s", len(run.errors))
    log.info("Duration: %.1fs", run.duration_seconds)
