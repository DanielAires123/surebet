"""Load filters.json."""

from __future__ import annotations

import json
from pathlib import Path

from surebet.models import AppConfig, FilterConfig


def load_filters(path: Path | str) -> AppConfig:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    cfg = AppConfig.model_validate(data)
    for f in cfg.filters:
        if not f.surebet_filter_id:
            raise ValueError(f"Filter {f.id} missing surebet_filter_id")
    return cfg


def enabled_filters(cfg: AppConfig, only_id: str | None = None) -> list[FilterConfig]:
    items = [f for f in cfg.filters if f.enabled]
    if only_id:
        items = [f for f in items if f.id == only_id]
    return items
