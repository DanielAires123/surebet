# SureBet Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-ready Python monitor that logs into pt.surebet.com once per run, scrapes configured surebet/valuebet presets via Playwright DOM, validates mathematically, dedupes, and alerts Telegram — runnable on GitHub Actions every ~15 minutes.

**Architecture:** Single Chromium session → login once → for each `filters.json` entry navigate to `/surebets` or `/valuebets`, select `#filter_current_id` by `surebet_filter_id`, scrape `tbody.*_record`, normalize/validate/dedupe, Telegram. State persisted on `bot-state` branch. No API, no bet placement, no CAPTCHA bypass.

**Tech Stack:** Python 3.12, Playwright, httpx, pydantic, Decimal, pytest, GitHub Actions

## Global Constraints

- Base URL default: `https://pt.surebet.com` (env `SUREBET_BASE_URL`)
- Navigate only `/surebets` and `/valuebets`; select filter via `#filter_current_id`
- All selectors in `surebet/selectors.py` (from DOM dump 2026-09-29)
- Percents stored as fractions (`0.05` = 5%); helpers `parse_percent` / `format_percent`
- Financial math uses `Decimal`
- Secrets only via env / GitHub Secrets; never in state/logs/filters
- Conservatism: doubt → `unverified`; CAPTCHA → stop
- Spec: `docs/superpowers/specs/2026-09-29-surebet-monitor-design.md`

## File structure (create all)

```
main.py
requirements.txt
filters.json
.env.example
.gitignore
README.md
surebet/__init__.py
surebet/config.py          # env + tolerances
surebet/exceptions.py
surebet/selectors.py
surebet/models.py
surebet/percent.py
surebet/normalization.py
surebet/validation.py
surebet/deduplication.py
surebet/state.py
surebet/filters.py
surebet/browser.py
surebet/auth.py
surebet/navigation.py
surebet/valuebets.py
surebet/arbitrage.py
surebet/monitor.py         # per-filter orchestration
telegram/__init__.py
telegram/bot.py
telegram/formatting.py
tests/test_valuebet.py
tests/test_arbitrage.py
tests/test_identity.py
tests/test_normalization.py
tests/test_percent.py
data/.gitkeep
.github/workflows/surebet-monitor.yml
```

---

### Task 1: Scaffold + percent + models + exceptions

**Files:**
- Create: `requirements.txt`, `.gitignore`, `.env.example`, `data/.gitkeep`
- Create: `surebet/__init__.py`, `surebet/exceptions.py`, `surebet/percent.py`, `surebet/models.py`, `surebet/config.py`
- Test: `tests/test_percent.py`

**Interfaces:**
- Produces: `parse_percent(str|Decimal) -> Decimal`, `format_percent(Decimal, places=2) -> str`, `percentage_points_difference(a,b) -> Decimal`
- Produces models: `ValidationStatus`, `ValueBet`, `Arbitrage`, `ArbOutcome`, `FilterConfig`, `GlobalConfig`, `AppConfig`, `OpportunityState`, `RunStats`
- Produces exceptions: `AuthFailed`, `CaptchaDetected`, `AntiBotDetected`, `SiteUnavailable`, `FilterNotFound`, `ResultsTimeout`, `ParserHealthWarning`

- [ ] **Step 1:** Write `tests/test_percent.py` covering `41%`→`0.41`, `0.41` stays, `10.3%`→`0.103`, pp diff `|0.23-0.229|*100=0.1`
- [ ] **Step 2:** Implement `surebet/percent.py`, `models.py`, `exceptions.py`, `config.py`, scaffolding files
- [ ] **Step 3:** `pytest tests/test_percent.py -v` → PASS

---

### Task 2: Normalization + identity hashes

**Files:**
- Create: `surebet/normalization.py`, `surebet/deduplication.py`
- Test: `tests/test_normalization.py`, `tests/test_identity.py`

**Interfaces:**
- `normalize_event(str) -> str`, `normalize_bookmaker(str) -> tuple[canonical, display]`, `parse_market(raw: str) -> MarketParts` (market_type, period, line, selection, team, …)
- `valuebet_identity_hash(...) -> str`, `arbitrage_identity_hash(...) -> str` (SHA-256 hex; exclude odds/profit/overvalue; sort arb legs)

- [ ] **Step 1:** Failing tests for market parse (`Acima 26.5 - chutes` → total/over/26.5), event dash normalize, arb hash order-independence
- [ ] **Step 2:** Implement modules
- [ ] **Step 3:** pytest → PASS

---

### Task 3: Validation (valuebet EV + arbitrage + stakes)

**Files:**
- Create: `surebet/validation.py`
- Test: `tests/test_valuebet.py`, `tests/test_arbitrage.py`

**Interfaces:**
- `validate_valuebet(odds, probability, site_overvalue, market_type) -> ValidationResult`
- `validate_arbitrage(outcomes, site_profit, market_parts_per_leg) -> ValidationResult`
- `calculate_stakes(odds: list[Decimal], total: Decimal) -> StakePlan` (cent rounding + real profit)

Acceptance fixtures from spec:
- VB: 3.00, 0.41 → EV 0.23; site 0.229 → validated within 0.5pp
- ARB: 2.39, 2.05 → inv≈0.9062, ROI≈0.1035; incompatible period → unverified

- [ ] **Step 1:** Write tests (positive/negative/zero EV; invalid p; 2-way/3-way; non-arb; period mismatch; duplicate outcome)
- [ ] **Step 2:** Implement `validation.py`
- [ ] **Step 3:** pytest → PASS

---

### Task 4: Selectors + filters.json loader

**Files:**
- Create: `surebet/selectors.py`, `surebet/filters.py`, `filters.json`

**Interfaces:**
- `Selectors` constants: VALUEBETS_TABLE, VALUEBET_RECORD, SUREBETS_TABLE, SUREBET_RECORD, FILTER_SELECT, FILTER_APPLY, LOGIN_*, AUTH_*, CAPTCHA_HINTS, RESULT_EMPTY_HINTS, etc.
- `load_filters(path) -> AppConfig` requiring `surebet_filter_id` on each filter

- [ ] **Step 1:** Ship `filters.json` exactly as design §6
- [ ] **Step 2:** Centralize DOM selectors from dump (no invented CSS beyond captured ids/testids/classes)
- [ ] **Step 3:** Unit-test load + reject missing `surebet_filter_id`

---

### Task 5: Playwright browser / auth / navigation / parsers

**Files:**
- Create: `surebet/browser.py`, `surebet/auth.py`, `surebet/navigation.py`, `surebet/valuebets.py`, `surebet/arbitrage.py`

**Interfaces:**
- `launch_browser(debug: bool) -> tuple[Browser, BrowserContext, Page]`
- `login(page) -> None` raises typed auth errors; confirm via authenticated UI (`#filter_current_id` or no “Fazer login”)
- `open_product(page, source: Literal['valuebet','surebet']) -> None`
- `select_filter(page, surebet_filter_id: str, expected_name: str) -> None`
- `wait_for_results(page, source) -> ResultsState` enum LOADING|RESULTS|EMPTY|TIMEOUT|ERROR
- `extract_valuebets(page, filter) -> tuple[list[ValueBet], ParseStats]`
- `extract_arbitrages(page, filter) -> tuple[list[Arbitrage], ParseStats]`

Parse rules:
- Prefer `data-*` attrs on record tbody; fill display fields from testids
- Probability: if `data-probability` looks like `67.13` treat as percent → `/100` once
- Overvalue/profit site values similarly (`12.1` → `0.121`)
- Never invent missing fields
- If DOM has content but parse_success_rate < `MIN_PARSE_SUCCESS_RATE` → `PARSER_OR_LAYOUT_CHANGED` / warning

- [ ] **Step 1:** Implement modules using selectors
- [ ] **Step 2:** Optional local dry smoke (manual); unit-test parsers against saved HTML fixtures copied from `debug/*_page.html` into `tests/fixtures/` (sanitized snippets)

---

### Task 6: State + Telegram + monitor orchestration + main CLI

**Files:**
- Create: `surebet/state.py`, `surebet/monitor.py`, `telegram/bot.py`, `telegram/formatting.py`, `main.py`

**Interfaces:**
- `StateStore.load/save/path`; decide send via thresholds; dry_run skips sent mutation
- `TelegramBot.send_message`, `send_photo`, `test_connection`; max alerts/run; cooldown for errors
- `format_valuebet_alert`, `format_arbitrage_alert`
- `run_monitor(args) -> int` exit code
- CLI: `--dry-run --debug --filter ID --test-telegram`

- [ ] **Step 1:** Implement formatters + bot retries
- [ ] **Step 2:** `monitor.process_filter` pipeline
- [ ] **Step 3:** `main.py` argparse wiring; one browser session loop

---

### Task 7: GitHub Actions + README + bot-state notes

**Files:**
- Create: `.github/workflows/surebet-monitor.yml`, `README.md`

Workflow must:
- cron `7,22,37,52 * * * *` + workflow_dispatch
- concurrency group `surebet-monitor`, cancel-in-progress false
- timeout 10m, ubuntu-latest
- pytest then monitor
- checkout/push `bot-state` for `state.json` only (`[skip ci]`)
- env from secrets

README: beginner setup (repo, BotFather, secrets, filters, dry-run, schedule, troubleshooting matrix from original §75)

- [ ] **Step 1:** Write workflow YAML
- [ ] **Step 2:** Write README
- [ ] **Step 3:** Full `pytest` green

---

## Spec coverage checklist

| Spec area | Task |
|---|---|
| Login once / one session | 5–6 |
| filters.json presets + thresholds | 4, 6 |
| DOM selectors from dump | 4–5 |
| VB/ARB validation + stakes | 3 |
| Dedup / state / bot-state | 2, 6, 7 |
| Telegram + screenshots | 6 |
| GHA + README | 7 |
| Offline tests | 1–3 |
| No choose-URL navigation | 5 |
| CAPTCHA stop | 5–6 |

---

## Execution

After plan save: prefer **inline execution** in this session (user said “continua”) unless they request subagent-driven.
