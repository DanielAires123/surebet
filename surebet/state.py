"""Persistent opportunity state + bet ledger (no secrets)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from surebet.models import (
    Arbitrage,
    OpportunityState,
    PendingAlert,
    TrackedBet,
    ValueBet,
)

log = logging.getLogger(__name__)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(type(obj))


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.opportunities: dict[str, OpportunityState] = {}
        self.error_alerts: dict[str, str] = {}  # hash -> last_sent_at iso
        self.pending_alerts: dict[str, PendingAlert] = {}  # short_id -> alert
        self.bets: dict[str, TrackedBet] = {}  # bet id -> bet
        self.telegram_update_offset: int = 0

    def load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for item in data.get("opportunities", []):
            st = OpportunityState.model_validate(item)
            self.opportunities[st.identity_hash] = st
        self.error_alerts = dict(data.get("error_alerts", {}))
        self.pending_alerts = {
            k: PendingAlert.model_validate(v) for k, v in (data.get("pending_alerts") or {}).items()
        }
        self.bets = {k: TrackedBet.model_validate(v) for k, v in (data.get("bets") or {}).items()}
        self.telegram_update_offset = int(data.get("telegram_update_offset") or 0)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # prune stale pending (>7d)
        cutoff = datetime.now(timezone.utc).timestamp() - 7 * 86400
        pruned = {}
        for k, p in self.pending_alerts.items():
            if p.created_at and p.created_at.timestamp() < cutoff:
                continue
            pruned[k] = p
        self.pending_alerts = pruned

        payload = {
            "opportunities": [o.model_dump(mode="json") for o in self.opportunities.values()],
            "error_alerts": self.error_alerts,
            "pending_alerts": {k: v.model_dump(mode="json") for k, v in self.pending_alerts.items()},
            "bets": {k: v.model_dump(mode="json") for k, v in self.bets.items()},
            "telegram_update_offset": self.telegram_update_offset,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)
        self.path.write_text(text + "\n", encoding="utf-8")

    def get(self, identity_hash: str) -> Optional[OpportunityState]:
        return self.opportunities.get(identity_hash)

    def content_sent_recently(self, content_hash: str | None, *, within_minutes: int = 60) -> bool:
        if not content_hash:
            return False
        now = datetime.now(timezone.utc)
        for st in self.opportunities.values():
            if st.content_hash != content_hash or not st.last_sent_at:
                continue
            if (now - st.last_sent_at).total_seconds() <= within_minutes * 60:
                return True
        return False

    def touch_valuebet(self, vb: ValueBet, *, sent: bool, now: Optional[datetime] = None) -> None:
        assert vb.identity_hash
        now = now or datetime.now(timezone.utc)
        prev = self.opportunities.get(vb.identity_hash)
        st = OpportunityState(
            identity_hash=vb.identity_hash,
            content_hash=vb.content_hash,
            last_odds=[vb.odds] if vb.odds is not None else None,
            last_overvalue=vb.site_overvalue,
            last_probability=vb.fair_probability,
            last_seen_at=now,
            last_sent_at=(now if sent else (prev.last_sent_at if prev else None)),
            validation_status=vb.validation_status.value,
        )
        self.opportunities[vb.identity_hash] = st

    def touch_arbitrage(self, arb: Arbitrage, *, sent: bool, now: Optional[datetime] = None) -> None:
        assert arb.identity_hash
        now = now or datetime.now(timezone.utc)
        prev = self.opportunities.get(arb.identity_hash)
        st = OpportunityState(
            identity_hash=arb.identity_hash,
            content_hash=arb.content_hash,
            last_odds=[o.odds for o in arb.outcomes],
            last_profit=arb.site_profit,
            last_seen_at=now,
            last_sent_at=(now if sent else (prev.last_sent_at if prev else None)),
            validation_status=arb.validation_status.value,
        )
        self.opportunities[arb.identity_hash] = st

    def register_pending(self, alert: PendingAlert) -> None:
        self.pending_alerts[alert.short_id] = alert

    def get_pending(self, short_id: str) -> Optional[PendingAlert]:
        return self.pending_alerts.get(short_id)

    def confirm_bet(self, short_id: str, *, yes: bool, default_stake: Decimal) -> Optional[TrackedBet]:
        pending = self.pending_alerts.get(short_id)
        if not pending:
            return None
        now = datetime.now(timezone.utc)
        bet_id = f"{short_id}:{int(now.timestamp())}"
        if not yes:
            bet = TrackedBet(
                id=bet_id,
                identity_hash=pending.identity_hash,
                source=pending.source,
                status="skipped",
                filter_id=pending.filter_id,
                filter_name=pending.filter_name,
                event=pending.event,
                sport=pending.sport,
                market_raw=pending.market_raw,
                bookmaker=pending.bookmaker,
                odds=pending.odds,
                roi=pending.roi,
                telegram_message_id=pending.message_id,
                confirmed_at=now,
            )
            self.bets[bet_id] = bet
            return bet
        bet = TrackedBet(
            id=bet_id,
            identity_hash=pending.identity_hash,
            source=pending.source,
            status="open",
            filter_id=pending.filter_id,
            filter_name=pending.filter_name,
            event=pending.event,
            sport=pending.sport,
            market_raw=pending.market_raw,
            bookmaker=pending.bookmaker,
            odds=pending.odds,
            roi=pending.roi,
            stake=default_stake,
            currency="EUR",
            telegram_message_id=pending.message_id,
            confirmed_at=now,
        )
        self.bets[bet_id] = bet
        return bet

    def open_bets_count(self) -> int:
        return sum(1 for b in self.bets.values() if b.status == "open")

    def should_send_error(self, error_hash: str, cooldown_minutes: int) -> bool:
        last = self.error_alerts.get(error_hash)
        if not last:
            return True
        try:
            ts = datetime.fromisoformat(last)
        except ValueError:
            return True
        return (datetime.now(timezone.utc) - ts).total_seconds() >= cooldown_minutes * 60

    def mark_error_sent(self, error_hash: str) -> None:
        self.error_alerts[error_hash] = datetime.now(timezone.utc).isoformat()
