"""Login — one session per run. No CAPTCHA bypass."""

from __future__ import annotations

import logging
import re
import time

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from surebet import selectors as S
from surebet.config import Settings
from surebet.exceptions import (
    AntiBotDetected,
    AuthFailed,
    CaptchaDetected,
    SiteUnavailable,
    TimeoutError_,
)

log = logging.getLogger(__name__)


def _page_text(page: Page) -> str:
    try:
        return page.locator("body").inner_text(timeout=5_000)
    except Exception:
        return ""


def detect_protections(page: Page) -> None:
    """Stop on real anti-bot walls only — ignore script mentions of captcha."""
    for sel in S.ANTI_BOT_SELECTORS:
        try:
            if page.locator(sel).count() > 0:
                raise AntiBotDetected(f"Anti-bot selector present: {sel}")
        except AntiBotDetected:
            raise
        except Exception:
            continue

    text = _page_text(page).casefold()
    try:
        title = (page.title() or "").casefold()
    except Exception:
        title = ""
    for hint in S.CAPTCHA_VISIBLE_TEXT:
        if hint in text or hint in title:
            raise CaptchaDetected(f"Protection hint detected: {hint}")


def is_authenticated(page: Page) -> bool:
    # Public pages also have #filter_current_id — do NOT treat that as logged-in.
    if page.locator(S.AUTH_SIGNOUT).count() > 0:
        return True
    text = _page_text(page)
    if S.LOGIN_PAGE_TEXT in text:
        return False
    return False


def _wait_for_grecaptcha(page: Page, timeout_s: float = 25.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        ready = page.evaluate(
            """() => !!(window.grecaptcha && typeof window.grecaptcha.execute === 'function')"""
        )
        if ready:
            return
        page.wait_for_timeout(250)
    raise AuthFailed(
        "reCAPTCHA JS (grecaptcha) did not load — login cannot proceed from this environment"
    )


def _ensure_recaptcha_token(page: Page, timeout_s: float = 20.0) -> None:
    """Let the site's own JS fill #recaptcha-token (triggered on password change)."""
    token_el = page.locator(S.LOGIN_RECAPTCHA_TOKEN)
    if token_el.count() == 0:
        raise AuthFailed("reCAPTCHA token field missing on login form")

    existing = token_el.input_value()
    if existing:
        return

    # Site JS: on password change → grecaptcha.execute(sitekey, {action:'sign_in'})
    page.evaluate(
        """() => {
          const key = document.querySelector('#recaptcha-key')?.value;
          const token = document.querySelector('#recaptcha-token');
          if (!window.grecaptcha || !key || !token) return false;
          return window.grecaptcha.execute(key, {action: 'sign_in'}).then((t) => {
            token.value = t;
            return true;
          });
        }"""
    )

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        val = token_el.input_value()
        if val:
            log.info("reCAPTCHA token acquired (len=%s)", len(val))
            return
        page.wait_for_timeout(250)

    raise CaptchaDetected(
        "reCAPTCHA token empty after execute — Google likely blocked this IP/environment. "
        "Do not bypass; run locally or use a saved browser storage_state from a manual login."
    )


def login(page: Page, settings: Settings) -> None:
    base = settings.base_url
    try:
        page.goto(f"{base}{S.VALUEBETS_PATH}", wait_until="domcontentloaded", timeout=45_000)
    except PlaywrightTimeout as e:
        raise TimeoutError_("Timeout loading SureBet") from e
    except Exception as e:
        raise SiteUnavailable(str(e)) from e

    detect_protections(page)

    if is_authenticated(page):
        log.info("Already authenticated")
        return

    page.goto(f"{base}{S.LOGIN_PATH}", wait_until="domcontentloaded", timeout=45_000)
    detect_protections(page)

    try:
        page.wait_for_selector(S.LOGIN_FORM, timeout=20_000)
        page.wait_for_selector(S.LOGIN_EMAIL, timeout=20_000)
    except PlaywrightTimeout as e:
        raise AuthFailed("Login form not found") from e

    # Ensure JS flag (site sets this too)
    js_flag = page.locator(S.LOGIN_USER_JS)
    if js_flag.count() > 0:
        page.evaluate(
            """() => {
              const el = document.querySelector('#user_js');
              if (el) el.value = 'enabled';
            }"""
        )

    _wait_for_grecaptcha(page)

    email = page.locator(S.LOGIN_EMAIL)
    password = page.locator(S.LOGIN_PASSWORD)
    if password.count() == 0:
        # some flows reveal password after email check
        email.fill(settings.surebet_username)
        email.blur()
        page.wait_for_timeout(1500)
        try:
            page.wait_for_selector(S.LOGIN_PASSWORD, timeout=15_000)
        except PlaywrightTimeout as e:
            raise AuthFailed("Password field never appeared after email") from e
        password = page.locator(S.LOGIN_PASSWORD)

    email.fill(settings.surebet_username)
    password.click()
    password.fill(settings.surebet_password)
    # trigger site's change handler that requests recaptcha token
    password.dispatch_event("change")
    page.wait_for_timeout(300)

    _ensure_recaptcha_token(page)

    submit = page.locator(S.LOGIN_SUBMIT)
    if submit.count() == 0:
        raise AuthFailed("Login submit button not found")
    submit.click()

    try:
        page.wait_for_load_state("domcontentloaded", timeout=30_000)
    except PlaywrightTimeout as e:
        raise TimeoutError_("Timeout after login submit") from e

    detect_protections(page)

    # Confirm auth (Sair). If still on sign_in, credentials/recaptcha rejected.
    try:
        page.wait_for_selector(S.AUTH_SIGNOUT, timeout=25_000)
    except PlaywrightTimeout:
        page.goto(f"{base}{S.VALUEBETS_PATH}", wait_until="domcontentloaded", timeout=45_000)
        detect_protections(page)
        try:
            page.wait_for_selector(S.AUTH_SIGNOUT, timeout=15_000)
        except PlaywrightTimeout:
            pass

    if not is_authenticated(page):
        body = _page_text(page)
        if re.search(r"inv[aá]lid|incorret|wrong password|authentication|senha", body, re.I):
            raise AuthFailed("Invalid credentials (or login rejected)")
        if page.locator(S.LOGIN_FORM).count() > 0 or S.LOGIN_PAGE_TEXT in body:
            raise AuthFailed(
                "Still on login page after submit — credentials wrong or reCAPTCHA rejected"
            )
        raise AuthFailed("Authentication not confirmed after login (no sign-out link)")

    log.info("Login successful")
