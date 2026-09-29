"""Persistent opportunity state (no secrets)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from surebet.models import Arbitrage, OpportunityState, ValueBet

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

    def load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for item in data.get("opportunities", []):
            st = OpportunityState.model_validate(item)
            self.opportunities[st.identity_hash] = st
        self.error_alerts = dict(data.get("error_alerts", {}))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "opportunities": [o.model_dump(mode="json") for o in self.opportunities.values()],
            "error_alerts": self.error_alerts,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)
        self.path.write_text(text + "\n", encoding="utf-8")

    def get(self, identity_hash: str) -> Optional[OpportunityState]:
        return self.opportunities.get(identity_hash)

    def touch_valuebet(self, vb: ValueBet, *, sent: bool, now: Optional[datetime] = None) -> None:
        assert vb.identity_hash
        now = now or datetime.now(timezone.utc)
        prev = self.opportunities.get(vb.identity_hash)
        st = OpportunityState(
            identity_hash=vb.identity_hash,
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
            last_odds=[o.odds for o in arb.outcomes],
            last_profit=arb.site_profit,
            last_seen_at=now,
            last_sent_at=(now if sent else (prev.last_sent_at if prev else None)),
            validation_status=arb.validation_status.value,
        )
        self.opportunities[arb.identity_hash] = st

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
