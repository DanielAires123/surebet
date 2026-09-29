"""Login — one session per run. No CAPTCHA bypass."""

from __future__ import annotations

import logging
import re

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
    text = _page_text(page).casefold()
    content = ""
    try:
        content = page.content().casefold()
    except Exception:
        pass
    for hint in S.CAPTCHA_TEXT_HINTS:
        if hint.casefold() in text or hint.casefold() in content:
            raise CaptchaDetected(f"Protection hint detected: {hint}")
    for sel in S.ANTI_BOT_SELECTORS:
        if page.locator(sel).count() > 0:
            raise AntiBotDetected(f"Anti-bot selector present: {sel}")


def is_authenticated(page: Page) -> bool:
    # Public pages also have #filter_current_id — do NOT treat that as logged-in.
    if page.locator(S.AUTH_SIGNOUT).count() > 0:
        return True
    text = _page_text(page)
    if S.LOGIN_PAGE_TEXT in text:
        return False
    return False


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

    # Go to explicit sign-in if needed
    if page.locator(S.LOGIN_PASSWORD).count() == 0:
        page.goto(f"{base}{S.LOGIN_PATH}", wait_until="domcontentloaded", timeout=45_000)
        detect_protections(page)

    email = page.locator(S.LOGIN_EMAIL).first
    password = page.locator(S.LOGIN_PASSWORD).first
    if email.count() == 0 or password.count() == 0:
        raise AuthFailed("Login form fields not found")

    email.fill(settings.surebet_username)
    password.fill(settings.surebet_password)
    submit = page.locator(S.LOGIN_SUBMIT).first
    submit.click()

    try:
        page.wait_for_load_state("domcontentloaded", timeout=30_000)
        # wait for session cookie / redirect to settle
        page.wait_for_timeout(1500)
    except PlaywrightTimeout as e:
        raise TimeoutError_("Timeout after login submit") from e

    detect_protections(page)

    page.goto(f"{base}{S.VALUEBETS_PATH}", wait_until="domcontentloaded", timeout=45_000)
    detect_protections(page)

    try:
        page.wait_for_selector(S.AUTH_SIGNOUT, timeout=20_000)
    except PlaywrightTimeout:
        pass

    if not is_authenticated(page):
        body = _page_text(page)
        if re.search(r"inv[aá]lid|incorret|wrong password|authentication", body, re.I):
            raise AuthFailed("Invalid credentials")
        raise AuthFailed("Authentication not confirmed after login (no sign-out link)")

    log.info("Login successful")
