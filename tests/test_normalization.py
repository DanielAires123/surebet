from decimal import Decimal

from surebet.filters import load_filters
from surebet.normalization import normalize_event, parse_market
from surebet.config import ROOT


def test_normalize_event_dashes():
    assert normalize_event("A — B") == "A – B"
    assert normalize_event("  Foo   Bar  ") == "Foo Bar"


def test_parse_total_market():
    p = parse_market("Abaixo 3.5 - chutes no alvo 1º o time")
    assert p.selection == "under"
    assert p.line == Decimal("3.5")
    assert p.market_type in {"shots_on_target", "team_total", "shots"}


def test_parse_unknown_asian():
    p = parse_market("H1(+0.25) Asian")
    assert p.market_type in {"unknown", "handicap"}


def test_load_filters_json():
    cfg = load_filters(ROOT / "filters.json")
    assert len(cfg.filters) >= 5
    assert all(f.surebet_filter_id for f in cfg.filters)
    sure = next(f for f in cfg.filters if f.id == "surebet_surebets")
    assert sure.min_profit == Decimal("0.05")
