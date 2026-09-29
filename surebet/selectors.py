"""
Centralized SureBet DOM selectors.

Captured from authenticated pt.surebet.com session (2026-09-29).
Do not invent CSS/XPath outside this module.
"""

# --- Auth / session ---
# Login form: Devise + reCAPTCHA v3 (token filled by site JS on password change).
LOGIN_PATH = "/users/sign_in"
LOGIN_FORM = "#sign-in-form"
LOGIN_EMAIL = "#user_email"
LOGIN_PASSWORD = "#user_password"
LOGIN_SUBMIT = "#sign-in-form-submit-button"
LOGIN_USER_JS = "#user_js"
LOGIN_RECAPTCHA_TOKEN = "#recaptcha-token"
LOGIN_RECAPTCHA_KEY = "#recaptcha-key"
AUTH_SIGNOUT = 'a[href="/users/sign_out"]'
AUTH_FILTER_SELECT = "#filter_current_id"
LOGIN_PAGE_TEXT = "Fazer login"

# Anti-bot / CAPTCHA — only strong visible signals (never solve).
# Do NOT match bare "captcha"/"recaptcha" in full HTML (scripts cause false positives).
CAPTCHA_VISIBLE_TEXT = (
    "just a moment",
    "verify you are human",
    "checking your browser",
    "attention required",
    "access denied",
    "enable javascript and cookies",
    "cf-browser-verification",
)
ANTI_BOT_SELECTORS = (
    "#challenge-form",
    "#challenge-running",
    ".cf-browser-verification",
    "iframe[src*='challenges.cloudflare.com']",
    "iframe[src*='hcaptcha.com']",
    "iframe[src*='google.com/recaptcha']",
    "iframe[title*='captcha' i]",
)

# --- Shared filter sidebar ---
FILTER_SELECT = "#filter_current_id"
FILTER_SELECT_TESTID = '[data-testid="filter-saved-select"]'
FILTER_APPLY = '[data-testid="filter-apply-button"]'
FILTER_PROFIT_MIN = '[data-testid="filter-profit-min-input"]'
FILTER_OVERVALUE_MIN = '[data-testid="filter-overvalue-min-input"], #selector_min_overvalue'

# --- Valuebets ---
VALUEBETS_PATH = "/valuebets"
VALUEBETS_TABLE = "#valuebets-table"
VALUEBET_RECORD = "tbody.valuebet_record"
VALUEBET_OVERVALUE = ".overvalue"
LEG_BOOKMAKER = '[data-testid="record-card-leg-bookmaker"]'
LEG_SPORT = '[data-testid="record-card-leg-sport"]'
LEG_EVENT = '[data-testid="record-card-leg-event"]'
LEG_TOURNAMENT = '[data-testid="record-card-leg-tournament"]'
LEG_MARKET = '[data-testid="record-card-leg-market"]'
LEG_ODDS = '[data-testid="record-card-leg-odds"]'

# --- Surebets ---
SUREBETS_PATH = "/surebets"
SUREBETS_TABLE = "#surebets-table"
SUREBET_RECORD = "tbody.surebet_record"
SUREBET_LEG = '[data-testid="record-card-leg"]'
SUREBET_PROFIT = '[data-testid="record-card-profit"]'

# --- Results waiting ---
RESULTS_FOUND_HINT = "Encontrado"
EMPTY_HINTS = (
    "Nenhuma aposta",
    "nenhum resultado",
    "No surebets",
    "No valuebets",
    "0 apostas",
)
LOADING_HINTS = (
    "fa-spinner",
    "loading",
)
