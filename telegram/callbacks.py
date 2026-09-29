"""Process Telegram callback_query for Apostei / Não."""

from __future__ import annotations

import logging
from decimal import Decimal

from surebet.config import Settings
from surebet.state import StateStore
from telegram.bot import TelegramBot
from telegram.formatting import format_bet_registered

log = logging.getLogger(__name__)


def _parse_bet_callback(data: str) -> tuple[str, str] | None:
    # bet:Y:abcdefghijklmnop
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != "bet":
        return None
    action, short_id = parts[1], parts[2]
    if action not in {"Y", "N"} or len(short_id) < 8:
        return None
    return action, short_id


def process_callback_update(
    update: dict,
    *,
    bot: TelegramBot,
    state: StateStore,
    default_stake: Decimal,
) -> bool:
    cq = update.get("callback_query") or {}
    data = cq.get("data") or ""
    parsed = _parse_bet_callback(data)
    if not parsed:
        return False
    action, short_id = parsed
    cq_id = cq.get("id")
    msg = cq.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    message_id = msg.get("message_id")
    original_text = msg.get("text") or ""

    bet = state.confirm_bet(short_id, yes=(action == "Y"), default_stake=default_stake)
    note = format_bet_registered(action)
    if cq_id:
        bot.answer_callback(str(cq_id), note)
    if chat_id is not None and message_id is not None:
        # Keep URL buttons? Strip tracking buttons — leave a status line.
        new_text = original_text
        if note not in original_text:
            new_text = f"{original_text}\n\n{note}"
        # Keep bookie URL buttons if we still have pending (urls only — drop callbacks)
        pending = state.get_pending(short_id)
        markup = None
        if pending:
            # rebuild only url buttons from nothing stored — clear keyboard
            markup = {"inline_keyboard": []}
        bot.edit_message_text(chat_id, int(message_id), new_text, reply_markup=markup or {"inline_keyboard": []})
    if bet:
        log.info("Bet %s status=%s event=%s", bet.id, bet.status, bet.event)
    else:
        log.warning("Callback short_id=%s not in pending_alerts", short_id)
    return True


def poll_callbacks(
    *,
    settings: Settings,
    state: StateStore,
    dry_run: bool = False,
    default_stake: Decimal = Decimal("10"),
) -> int:
    bot = TelegramBot(
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        dry_run=dry_run,
    )
    offset = state.telegram_update_offset or None
    updates = bot.get_updates(offset=offset, timeout=0, allowed_updates=["callback_query"])
    handled = 0
    max_update_id = state.telegram_update_offset
    for upd in updates:
        uid = int(upd.get("update_id") or 0)
        max_update_id = max(max_update_id, uid + 1)
        if process_callback_update(upd, bot=bot, state=state, default_stake=default_stake):
            handled += 1
    if max_update_id:
        state.telegram_update_offset = max_update_id
    if not dry_run:
        state.save()
    log.info("Callbacks processed: %s (offset=%s)", handled, state.telegram_update_offset)
    return 0
