"""Telegram Bot API client (httpx)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import httpx

log = logging.getLogger(__name__)


class TelegramBot:
    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        message_thread_id: str | int | None = None,
        max_alerts_per_run: int = 30,
        dry_run: bool = False,
    ):
        self.token = token
        self.chat_id = chat_id
        self.message_thread_id = str(message_thread_id) if message_thread_id not in (None, "") else None
        self.max_alerts_per_run = max_alerts_per_run
        self.dry_run = dry_run
        self.sent_count = 0
        self.base = f"https://api.telegram.org/bot{token}"

    def _allowed(self) -> bool:
        return self.sent_count < self.max_alerts_per_run

    def _with_thread(self, data: dict, *, as_form: bool = False) -> dict:
        if self.message_thread_id:
            tid: str | int = self.message_thread_id if as_form else int(self.message_thread_id)
            data = {**data, "message_thread_id": tid}
        return data

    def _request(self, method: str, data: dict, files: Optional[dict] = None) -> bool:
        if self.dry_run:
            log.info("[dry-run] telegram %s skipped (thread=%s)", method, self.message_thread_id)
            return True
        if not self.token or not self.chat_id:
            log.warning("Telegram not configured")
            return False
        url = f"{self.base}/{method}"
        delay = 1.0
        for attempt in range(4):
            try:
                with httpx.Client(timeout=30.0) as client:
                    if files:
                        r = client.post(url, data=data, files=files)
                    else:
                        r = client.post(url, json=data)
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(delay)
                    delay *= 2
                    continue
                if r.status_code >= 400:
                    log.error("Telegram error %s: %s", r.status_code, r.text[:300])
                    return False
                return True
            except httpx.HTTPError as e:
                log.warning("Telegram network error: %s", e)
                time.sleep(delay)
                delay *= 2
        return False

    def send_message(self, text: str) -> bool:
        if not self._allowed():
            log.warning("Telegram alert cap reached (%s)", self.max_alerts_per_run)
            return False
        ok = self._request(
            "sendMessage",
            self._with_thread(
                {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}
            ),
        )
        if ok:
            self.sent_count += 1
        return ok

    def send_photo(self, path: Path, caption: str = "") -> bool:
        if not self._allowed():
            return False
        if self.dry_run:
            log.info("[dry-run] telegram photo skipped: %s", path)
            return True
        if not path.exists():
            return False
        with path.open("rb") as f:
            ok = self._request(
                "sendPhoto",
                self._with_thread({"chat_id": self.chat_id, "caption": caption[:1024]}, as_form=True),
                files={"photo": f},
            )
        if ok:
            self.sent_count += 1
        return ok

    def test_connection(self) -> bool:
        return self.send_message("✅ SureBet Monitor\nTelegram configuration OK.")
