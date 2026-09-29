"""Per-run monitor orchestration."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
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
    Arbitrage,
    FilterConfig,
    FilterRunStats,
    PendingAlert,
    ResultsState,
    RunStats,
    ScreenshotMode,
    ValidationStatus,
    ValueBet,
)
from surebet.navigation import (
    select_filter,
    take_results_screenshot,
    wait_for_results,
)
from surebet.state import StateStore
from surebet.valuebets import extract_valuebets
from telegram.bot import TelegramBot
from telegram.callbacks import poll_callbacks
from telegram.formatting import (
    build_alert_keyboard,
    format_arbitrage_alert,
    format_error_alert,
    format_run_summary,
    format_valuebet_alert,
    short_id_from_hash,
)

log = logging.getLogger(__name__)


def _want_overview_shot(mode: ScreenshotMode, reasons: list[str]) -> bool:
    """One table screenshot per filter when there is something to send."""
    if mode == ScreenshotMode.NEVER or mode == ScreenshotMode.ON_ERROR:
        return False
    if mode == ScreenshotMode.ALWAYS:
        return True
    if mode == ScreenshotMode.ON_NEW:
        return any(r == "new" for r in reasons)
    if mode == ScreenshotMode.ON_CHANGE:
        return any(r in {"new", "changed", "expired_reappear"} for r in reasons)
    return False


def _item_roi(item: Arbitrage | ValueBet) -> Decimal:
    if isinstance(item, ValueBet):
        v = item.calculated_ev if item.calculated_ev is not None else item.site_overvalue
    else:
        v = item.calculated_profit if item.calculated_profit is not None else item.site_profit
    return v if v is not None else Decimal("-999")


def _thread_for(settings: Settings, source: str) -> str | None:
    if source == "valuebet":
        return settings.telegram_valuebet_thread_id or settings.telegram_arbitrage_thread_id
    return settings.telegram_arbitrage_thread_id or settings.telegram_valuebet_thread_id


def _pending_from_valuebet(
    vb: ValueBet,
    *,
    chat_id: str,
    message_id: int,
    thread_id: str | None,
) -> PendingAlert:
    assert vb.identity_hash
    return PendingAlert(
        short_id=short_id_from_hash(vb.identity_hash),
        identity_hash=vb.identity_hash,
        source="valuebet",
        filter_id=vb.filter_id,
        filter_name=vb.filter_name,
        event=vb.event,
        sport=vb.sport,
        market_raw=vb.market_raw,
        bookmaker=vb.bookmaker,
        odds=[vb.odds] if vb.odds is not None else None,
        roi=_item_roi(vb) if _item_roi(vb) > Decimal("-900") else None,
        chat_id=chat_id,
        message_id=message_id,
        thread_id=str(thread_id) if thread_id else None,
        created_at=datetime.now(timezone.utc),
    )


def _pending_from_arb(
    arb: Arbitrage,
    *,
    chat_id: str,
    message_id: int,
    thread_id: str | None,
) -> PendingAlert:
    assert arb.identity_hash
    books = " / ".join(o.bookmaker for o in arb.outcomes)
    markets = " | ".join(o.market_raw for o in arb.outcomes)
    return PendingAlert(
        short_id=short_id_from_hash(arb.identity_hash),
        identity_hash=arb.identity_hash,
        source="surebet",
        filter_id=arb.filter_id,
        filter_name=arb.filter_name,
        event=arb.event,
        sport=arb.sport,
        market_raw=markets,
        bookmaker=books,
        odds=[o.odds for o in arb.outcomes],
        roi=_item_roi(arb) if _item_roi(arb) > Decimal("-900") else None,
        chat_id=chat_id,
        message_id=message_id,
        thread_id=str(thread_id) if thread_id else None,
        created_at=datetime.now(timezone.utc),
    )


def process_filter(
    page: Page,
    filt: FilterConfig,
    *,
    settings: Settings,
    app: AppConfig,
    state: StateStore,
    bot: TelegramBot,
    dry_run: bool,
    content_sent_this_run: set[str],
) -> FilterRunStats:
    stats = FilterRunStats(filter_id=filt.id, filter_name=filt.name)
    log.info("Filter: %s", filt.name)
    thread_id = _thread_for(settings, filt.source)

    select_filter(
        page,
        filt.surebet_filter_id,
        filt.name,
        settings=settings,
        source=filt.source,
    )
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
        raise ParserOrLayoutChanged(
            f"parse_success_rate={parse_stats.success_rate} < {settings.min_parse_success_rate} "
            f"(raw={parse_stats.raw} parsed={parse_stats.parsed} failed={parse_stats.failed})"
        )

    log.info("Above threshold: %s", len(items))
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)

    pending: list[tuple[object, str]] = []

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

        if not g.allow_live_events and item.event_datetime and item.event_datetime <= datetime.now(timezone.utc):
            continue

        # cross-filter dedupe (same bet in 0.5UN + 1UN)
        ch = getattr(item, "content_hash", None)
        if ch and (ch in content_sent_this_run or state.content_sent_recently(ch)):
            stats.duplicate += 1
            if filt.source == "valuebet":
                state.touch_valuebet(item, sent=False)
            else:
                state.touch_arbitrage(item, sent=False)
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

        if g.revalidate_before_send and item.event_id:
            still = page.locator(f'tbody[data-id="{item.event_id}"]')
            if still.count() == 0:
                log.info("Skip send (gone from DOM): %s", item.event_id)
                continue

        pending.append((item, reason))

    # Highest ROI first — cap hits the weak ones
    pending.sort(key=lambda pair: _item_roi(pair[0]), reverse=True)

    if pending and _want_overview_shot(filt.screenshot_mode, [r for _, r in pending]):
        shot_path = settings.screenshots_dir / f"overview_{filt.id}.png"
        if dry_run:
            log.info("[dry-run] would send overview screenshot for %s", filt.name)
            stats.screenshots += 1
        else:
            take_results_screenshot(page, str(shot_path), filt.source)
            mid = bot.send_photo(shot_path, caption=filt.name, message_thread_id=thread_id)
            if mid is not None:
                stats.screenshots += 1
            else:
                log.error("Telegram overview photo failed for %s", filt.name)
            try:
                shot_path.unlink(missing_ok=True)
            except OSError:
                pass

    for item, _reason in pending:
        if dry_run:
            log.info("[dry-run] would send %s", item.identity_hash)
            stats.sent += 1
            if getattr(item, "content_hash", None):
                content_sent_this_run.add(item.content_hash)
            continue

        if filt.source == "valuebet":
            text = format_valuebet_alert(item, tz=g.display_timezone)
        else:
            text = format_arbitrage_alert(item, tz=g.display_timezone, currency=g.currency)

        sid = short_id_from_hash(item.identity_hash or "")
        keyboard = build_alert_keyboard(short_id=sid)
        mid = bot.send_message(text, message_thread_id=thread_id, reply_markup=keyboard)
        if mid is None:
            log.error("Telegram send_message failed for %s", item.event_id)
            if filt.source == "valuebet":
                state.touch_valuebet(item, sent=False)
            else:
                state.touch_arbitrage(item, sent=False)
            continue

        stats.sent += 1
        if getattr(item, "content_hash", None):
            content_sent_this_run.add(item.content_hash)
        if filt.source == "valuebet":
            state.touch_valuebet(item, sent=True)
            state.register_pending(
                _pending_from_valuebet(
                    item, chat_id=bot.chat_id, message_id=mid, thread_id=thread_id
                )
            )
        else:
            state.touch_arbitrage(item, sent=True)
            state.register_pending(
                _pending_from_arb(item, chat_id=bot.chat_id, message_id=mid, thread_id=thread_id)
            )

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
    # surebets first (faster odds death), then valuebets
    filters = sorted(filters, key=lambda f: 0 if f.source == "surebet" else 1)
    state = StateStore(settings.state_path)
    state.load()

    bot = TelegramBot(
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        max_alerts_per_run=app.global_.telegram_max_alerts_per_run,
        dry_run=dry_run,
    )

    run = RunStats(filters_configured=len(app.filters), filters_processed=0)
    content_sent_this_run: set[str] = set()
    log.info("Starting monitor")

    try:
        with BrowserSession(settings, debug=debug, headless=headless) as session:
            assert session.page is not None
            page = session.page
            if debug:
                session.screenshot("before_login.png")

            if session.storage_state_path:
                log.info("Using storage_state: %s", session.storage_state_path)
                page.goto(f"{settings.base_url}/valuebets", wait_until="domcontentloaded", timeout=45_000)
                detect_protections(page)
                from surebet.auth import is_authenticated

                if is_authenticated(page):
                    log.info("Session restored (skip login)")
                elif settings.surebet_username and settings.surebet_password:
                    log.warning("storage_state expired — falling back to login")
                    login(page, settings)
                else:
                    raise AuthFailed(
                        "storage_state present but session expired; re-export with "
                        "`python main.py --export-storage` and update the GitHub secret"
                    )
            else:
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
                        content_sent_this_run=content_sent_this_run,
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

    run.duration_seconds = time.time() - started
    _log_summary(run)

    # Summary + drain any pending Apostei/Não clicks
    if not dry_run:
        summary = format_run_summary(
            filters_ok=run.successful,
            filters_failed=run.failed,
            raw=run.raw,
            sent=run.sent,
            new=run.new,
            duration_s=run.duration_seconds,
            open_bets=state.open_bets_count(),
        )
        bot.send_message(
            summary,
            message_thread_id=settings.telegram_arbitrage_thread_id,
            count_toward_cap=False,
        )
        state.save()
        try:
            poll_callbacks(
                settings=settings,
                state=state,
                dry_run=False,
                default_stake=Decimal("10"),
            )
        except Exception:
            log.exception("poll_callbacks after monitor failed")

    if filters and run.failed == len(filters):
        return 1
    return 0


def _alert_error(bot: TelegramBot, state: StateStore, settings: Settings, reason: str) -> None:
    h = hashlib.sha256(reason.encode()).hexdigest()
    if state.should_send_error(h, settings.error_alert_cooldown_minutes):
        mid = bot.send_message(
            format_error_alert(reason),
            message_thread_id=settings.telegram_arbitrage_thread_id,
            count_toward_cap=False,
        )
        if mid is not None:
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
