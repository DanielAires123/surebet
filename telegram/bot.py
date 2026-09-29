"""Telegram Bot API client (httpx)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

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

    def _resolve_thread(self, message_thread_id: str | int | None) -> str | None:
        if message_thread_id is not None:
            return str(message_thread_id) if message_thread_id != "" else None
        return self.message_thread_id

    def _with_thread(
        self,
        data: dict,
        *,
        as_form: bool = False,
        message_thread_id: str | int | None = None,
    ) -> dict:
        tid = self._resolve_thread(message_thread_id)
        if tid:
            data = {**data, "message_thread_id": tid if as_form else int(tid)}
        return data

    def _request_json(
        self, method: str, data: dict, files: Optional[dict] = None
    ) -> Optional[dict[str, Any]]:
        if self.dry_run:
            log.info("[dry-run] telegram %s skipped (thread=%s)", method, data.get("message_thread_id"))
            return {"ok": True, "result": {"message_id": 0}}
        if not self.token or not self.chat_id:
            log.warning("Telegram not configured")
            return None
        url = f"{self.base}/{method}"
        delay = 1.0
        for _attempt in range(4):
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
                    return None
                body = r.json()
                if not body.get("ok"):
                    log.error("Telegram API not ok: %s", str(body)[:300])
                    return None
                return body
            except httpx.HTTPError as e:
                log.warning("Telegram network error: %s", e)
                time.sleep(delay)
                delay *= 2
        return None

    def _request(self, method: str, data: dict, files: Optional[dict] = None) -> bool:
        return self._request_json(method, data, files) is not None

    def send_message(
        self,
        text: str,
        *,
        message_thread_id: str | int | None = None,
        reply_markup: dict | None = None,
        count_toward_cap: bool = True,
    ) -> Optional[int]:
        """Send text; returns message_id or None."""
        if count_toward_cap and not self._allowed():
            log.warning("Telegram alert cap reached (%s)", self.max_alerts_per_run)
            return None
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        body = self._request_json(
            "sendMessage",
            self._with_thread(payload, message_thread_id=message_thread_id),
        )
        if not body:
            return None
        if count_toward_cap:
            self.sent_count += 1
        result = body.get("result") or {}
        mid = result.get("message_id")
        return int(mid) if mid is not None else 0

    def send_photo(
        self,
        path: Path,
        caption: str = "",
        *,
        message_thread_id: str | int | None = None,
    ) -> Optional[int]:
        if not self._allowed():
            return None
        if self.dry_run:
            log.info("[dry-run] telegram photo skipped: %s", path)
            self.sent_count += 1
            return 0
        if not path.exists():
            return None
        with path.open("rb") as f:
            # reply_markup must be JSON string in multipart form
            form = self._with_thread(
                {"chat_id": self.chat_id, "caption": caption[:1024]},
                as_form=True,
                message_thread_id=message_thread_id,
            )
            body = self._request_json("sendPhoto", form, files={"photo": f})
        if not body:
            return None
        self.sent_count += 1
        result = body.get("result") or {}
        mid = result.get("message_id")
        return int(mid) if mid is not None else 0

    def answer_callback(self, callback_query_id: str, text: str) -> bool:
        return self._request(
            "answerCallbackQuery",
            {"callback_query_id": callback_query_id, "text": text[:200]},
        )

    def edit_reply_markup(
        self,
        chat_id: str | int,
        message_id: int,
        reply_markup: dict | None = None,
    ) -> bool:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        else:
            payload["reply_markup"] = {"inline_keyboard": []}
        return self._request("editMessageReplyMarkup", payload)

    def edit_message_text(
        self,
        chat_id: str | int,
        message_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> bool:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self._request("editMessageText", payload)

    def get_updates(
        self,
        *,
        offset: int | None = None,
        timeout: int = 0,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if self.dry_run:
            return []
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": allowed_updates or ["callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        url = f"{self.base}/getUpdates"
        try:
            with httpx.Client(timeout=max(35.0, timeout + 5)) as client:
                r = client.post(url, json=payload)
            if r.status_code >= 400:
                log.error("getUpdates error %s: %s", r.status_code, r.text[:300])
                return []
            body = r.json()
            if not body.get("ok"):
                return []
            return list(body.get("result") or [])
        except httpx.HTTPError as e:
            log.warning("getUpdates network error: %s", e)
            return []

    def test_connection(self, *, message_thread_id: str | int | None = None) -> bool:
        mid = self.send_message(
            "✅ SureBet Monitor\nCabrão quem está a ver. Mas isto está a funcionar. Bom dia a todos.",
            message_thread_id=message_thread_id,
            count_toward_cap=False,
        )
        return mid is not None
