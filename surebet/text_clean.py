"""Display-string cleanup."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional


_BRACKET_ID = re.compile(r"^\[\d+\]\s*")


def clean_competition(name: Optional[str]) -> Optional[str]:
    if not name:
        return name
    return _BRACKET_ID.sub("", name.strip()) or name


def age_label(captured_at: Optional[datetime], *, now: Optional[datetime] = None) -> str:
    if not captured_at:
        return ""
    now = now or datetime.now(timezone.utc)
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    secs = max(0, int((now - captured_at).total_seconds()))
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m"
    return f"{mins // 60}h{mins % 60:02d}m"
