# SureBet Monitor — Design Spec

**Date:** 2026-09-29  
**Status:** Approved; implementation delivered 2026-09-29  
**Base URL:** `https://pt.surebet.com`  
**Stack:** Python 3.12, Playwright + Chromium, httpx, Decimal, pytest, GitHub Actions

---

## 1. Goal

Run on GitHub Actions ~every 15 minutes. One Chromium, one login, one session. For each configured filter: open product page, select saved preset, scrape DOM, normalize, validate mathematically, dedupe against persistent state, alert Telegram (optional screenshot). Never place bets. Never bypass CAPTCHA/anti-bot. No SureBet API / invented private endpoints.

---

## 2. Decisions locked

| Topic | Decision |
|---|---|
| Repo layout | Files at repository root (not nested `surebet-monitor/`) |
| Approach | Playwright DOM scrape only; math validation offline |
| Locale / base | `https://pt.surebet.com` (`SUREBET_BASE_URL` overridable) |
| Page navigation | Only `/surebets` and `/valuebets` |
| Filter apply | Select `#filter_current_id` by `surebet_filter_id` (option value). Do **not** `goto /filters/{id}/choose` as primary navigation (cold navigation returned 404). The choose URL may appear in Network as a side-effect of the UI select; we do not depend on parsing its body. |
| Filter IDs | From authenticated DOM dump (2026-09-29) |
| Conservatism | Doubt → `unverified`; CAPTCHA → stop; missing data → `None` |

---

## 3. Authenticated DOM (captured)

### 3.1 Valuebets (`/valuebets`)

- Table: `#valuebets-table`
- Row: `tbody.valuebet_record` with attrs: `data-id`, `data-overvalue`, `data-value` (odds), `data-probability`, `data-start-at`, `data-signature`
- Legs/fields via `data-testid`: `record-card-leg-bookmaker`, `-sport`, `-event`, `-tournament`, `-market`, `-odds`
- Filter select: `#filter_current_id` / `data-testid=filter-saved-select`
- Min overvalue input: `#selector_min_overvalue` / `data-testid=filter-overvalue-min-input`

**Preset IDs:**

| Name | surebet_filter_id |
|---|---|
| 0.5UN | `34237614` |
| 0.7UN | `34129105` |
| 1UN | `34200097` |
| MAX | `34129135` |

### 3.2 Surebets (`/surebets`)

- Table: `#surebets-table`
- Opportunity: `tbody.surebet_record` (`data-testid=record-card`) with attrs: `data-id`, `data-profit`, `data-roi`, `data-start-at`, `data-signature`, `data-formula`, `data-created-at`
- Legs (2..N): `[data-testid=record-card-leg]` + bookmaker/sport/event/tournament/market/odds testids
- Filter select: same `#filter_current_id`
- Min profit input: `data-testid=filter-profit-min-input`

**Preset IDs:**

| Name | surebet_filter_id |
|---|---|
| Surebets | `33897265` |
| (also present, unused by default) Betano, One Book, Portugal | … |

Debug dumps live under `debug/` (gitignored): `valuebets_page.html`, `surebets_page.html`, summaries JSON. Not shipped as runtime dependency.

---

## 4. Architecture

```
main.py (CLI)
 └─ sync_playwright → 1 browser → 1 context → login(page) once
      └─ for each enabled filter in filters.json:
           goto /{product}
           select preset by surebet_filter_id
           confirm selected text/value
           wait_for_results → LOADING|RESULTS|EMPTY|TIMEOUT|ERROR
           extract DOM → normalize → validate → identity_hash
           dedupe vs state → Telegram (± screenshot) → update state
      └─ browser.close()
 └─ persist state.json → branch bot-state [skip ci]
```

Isolated filter failures continue the loop. Login failure aborts. All filters failing → exit ≠ 0.

---

## 5. Module map

| Path | Responsibility |
|---|---|
| `main.py` | argparse CLI, orchestration, summary, exit codes |
| `filters.json` | global + filters config (no secrets) |
| `surebet/browser.py` | launch Chromium, context, debug screenshots |
| `surebet/auth.py` | login + auth confirmation; CAPTCHA/anti-bot detect |
| `surebet/navigation.py` | goto product, select filter, wait_for_results |
| `surebet/filters.py` | load/validate filters.json |
| `surebet/selectors.py` | **all** SureBet locators (from DOM dump) |
| `surebet/models.py` | Pydantic/dataclass models |
| `surebet/normalization.py` | event/bookie/market/period/line/selection |
| `surebet/validation.py` | EV, arb math, market compatibility, stakes |
| `surebet/valuebets.py` | DOM extract → ValueBet |
| `surebet/arbitrage.py` | DOM extract → Arbitrage (multi-leg) |
| `surebet/deduplication.py` | SHA-256 identity + resend thresholds |
| `surebet/state.py` | state.json load/save; bot-state sync helpers |
| `surebet/exceptions.py` | typed errors |
| `telegram/bot.py` | httpx send, retries, rate limit, cooldown |
| `telegram/formatting.py` | alert text (PT/structured as approved) |
| `tests/` | math, identity, normalization (no live site) |
| `.github/workflows/surebet-monitor.yml` | schedule + dispatch |

---

## 6. filters.json (runtime config)

```json
{
  "global": {
    "send_only_validated": true,
    "calculate_stakes": true,
    "default_total_stake": 100,
    "currency": "EUR",
    "display_timezone": "Europe/Lisbon",
    "allow_live_events": false,
    "revalidate_before_send": true,
    "telegram_max_alerts_per_run": 30
  },
  "filters": [
    {
      "id": "surebet_surebets",
      "name": "Surebets",
      "surebet_filter_id": "33897265",
      "source": "surebet",
      "enabled": true,
      "send_results": true,
      "screenshot_mode": "on_new",
      "min_profit": 0.01,
      "sports": [],
      "bookmakers": []
    },
    {
      "id": "valuebet_05un",
      "name": "0.5UN",
      "surebet_filter_id": "34237614",
      "source": "valuebet",
      "enabled": true,
      "send_results": true,
      "screenshot_mode": "on_new",
      "min_overvalue": 0.05,
      "sports": [],
      "bookmakers": []
    },
    {
      "id": "valuebet_07un",
      "name": "0.7UN",
      "surebet_filter_id": "34129105",
      "source": "valuebet",
      "enabled": true,
      "send_results": true,
      "screenshot_mode": "on_new",
      "min_overvalue": 0.05,
      "sports": [],
      "bookmakers": []
    },
    {
      "id": "valuebet_1un",
      "name": "1UN",
      "surebet_filter_id": "34200097",
      "source": "valuebet",
      "enabled": true,
      "send_results": true,
      "screenshot_mode": "on_new",
      "min_overvalue": 0.05,
      "sports": [],
      "bookmakers": []
    },
    {
      "id": "valuebet_max",
      "name": "MAX",
      "surebet_filter_id": "34129135",
      "source": "valuebet",
      "enabled": true,
      "send_results": true,
      "screenshot_mode": "on_new",
      "min_overvalue": 0.05,
      "sports": [],
      "bookmakers": []
    }
  ]
}
```

Adding a filter = edit JSON only (plus ensure preset exists in the SureBet account).

`min_overvalue` / `min_profit` are **post-scrape safety nets** in code (fractions: `0.05` = 5%, `0.01` = 1%), even if the site preset already filters.

---

## 7. Validation rules

### Valuebet

- Require independent probability `0 < p ≤ 1` (DOM `%` → fraction once).
- `EV = odds × p − 1`
- Validate if `EV > 0` and `|EV − site_overvalue|` within `VALUEBET_VALIDATION_TOLERANCE_PP` (default 0.5 pp).
- No independent probability → `unverified`.
- Site overvalue positive but calculated EV ≤ 0 → `invalid`/`unverified` with reason.

### Arbitrage

- `inverse_sum = Σ(1/odds_i)`; arb only if `inverse_sum < 1 − ARBITRAGE_EPSILON` (default 0.001).
- `ROI = 1/inverse_sum − 1`; compare to `site_profit` within `ARBITRAGE_PROFIT_TOLERANCE_PP` (0.25 pp).
- **Math alone insufficient:** same event, period, market type, line, complementary selections, full coverage. Else `unverified`.
- Complex markets (Asian, DNB, push, player props, etc.) → `unverified` if settlement not proven.
- Support N-way (2, 3, …) from multiple `record-card-leg` nodes in one `surebet_record`.
- `market_type == unknown` → `unverified` by default for arb.

### Stakes (when enabled)

- Decimal: `stake_i = TOTAL × (1/odds_i) / inverse_sum`; round to cents; recompute real payout/profit.

### Send policy

- Default `SEND_ONLY_VALIDATED=true`.

---

## 8. Identity & state

- Valuebet hash: `filter_id`, event_id or normalized event, bookmaker, market_type, period, line, selection, participant/team. **Exclude** odds/overvalue/probability.
- Arbitrage hash: `filter_id`, event_id or normalized event, market_type, period, line, sorted normalized selections. **Exclude** odds/profit.
- State fields: identity_hash, last_odds, last_profit, last_overvalue, last_probability, last_seen_at, last_sent_at, validation_status.
- Never store cookies, storage_state, passwords, tokens.
- Resend thresholds: odds Δ, overvalue/profit Δ (pp). Expiry: `OPPORTUNITY_EXPIRY_MINUTES=60`.
- Persist via dedicated git branch `bot-state` containing only `state.json`; commit message includes `[skip ci]`.

---

## 9. Auth & protections

- Confirm login via real authenticated UI (e.g. filter select present / absence of “Fazer login”), not merely submit click.
- Errors: `AUTH_FAILED`, `CAPTCHA_DETECTED`, `ANTI_BOT_DETECTED`, `TIMEOUT`, `SITE_UNAVAILABLE`.
- On CAPTCHA/anti-bot: stop; Telegram alert when possible; no solving/bypass/stealth/fingerprint spoofing/proxy rotation for evasion.

---

## 10. Telegram & screenshots

- Formats as specified in original requirements (valuebet / arbitrage), with “odds captured at HH:MM:SS” disclaimer.
- Rate limit: `TELEGRAM_MAX_ALERTS_PER_RUN=30`; retry 429/5xx with backoff.
- Error alert cooldown: 180 minutes keyed by error hash.
- Screenshot modes: `never|on_new|on_change|always|on_error` (default `on_new`); results container preferred; delete local file after send.
- `--test-telegram` sends config OK and exits.
- `--dry-run`: full pipeline except Telegram send and “sent” state mutation.

---

## 11. GitHub Actions

- Cron: `7,22,37,52 * * * *` + `workflow_dispatch` inputs: `filter_id`, `debug`, `dry_run`.
- `concurrency.group: surebet-monitor`, `cancel-in-progress: false`.
- `timeout-minutes: 10`, `ubuntu-latest`.
- Install deps + `playwright install --with-deps chromium`.
- Run pytest before monitor.
- Secrets: `SUREBET_USERNAME`, `SUREBET_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

---

## 12. CLI

```
python main.py
python main.py --dry-run
python main.py --debug
python main.py --filter valuebet_05un
python main.py --test-telegram
```

---

## 13. Testing (mandatory offline)

- Valuebet EV: odds 3.00, p 0.41 → EV 0.23; negative/zero/invalid p/odds; tolerance.
- Arbitrage: 2.39 + 2.05 → inverse ≈ 0.906, ROI ≈ 10.35%; 2-way/3-way; non-arb; incompatible period/line; duplicate outcome.
- Identity hash stability (order-independent for arb).
- Normalization helpers / percent helpers.

---

## 14. Out of scope

- Auto-betting, bookmaker clicks for placing stakes.
- OCR from screenshots.
- SureBet XML/API or undocumented internal APIs as primary data source.
- Stealth / CAPTCHA solving / Cloudflare bypass.
- Persisting browser session secrets on `bot-state`.

---

## 15. Acceptance criteria (summary)

- Valuebet 3.00 / 41% / site 22.9% → validated (~23% EV).
- Arb 2.39 / 2.05 / site 10.3% → validated iff markets compatible.
- FT vs 1H incompatible → unverified despite math.
- Same opportunity across runs → one Telegram message until thresholds/expiry.
- 0 results → success for that filter.
- CAPTCHA → stop without bypass.
- New filters via `filters.json` only.

---

## Spec self-review

- [x] No TBD left on navigation strategy (pages + select; choose URL not primary).
- [x] Filter IDs filled from live DOM.
- [x] Percent conventions explicit (internal fractions).
- [x] Scope = single implementable project.
- [x] Ambiguity resolved: min thresholds enforced in code + config; base URL pt.

**Note:** Repository was not a git repo at spec write time; commit of this file deferred until `git init` / remote exists.
