"""Product navigation + filter selection + wait_for_results."""

from __future__ import annotations

import logging
import time
from typing import Literal

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from surebet import selectors as S
from surebet.config import Settings
from surebet.exceptions import FilterNotFound
from surebet.models import ResultsState

log = logging.getLogger(__name__)

Source = Literal["valuebet", "surebet"]


def product_path(source: Source) -> str:
    return S.VALUEBETS_PATH if source == "valuebet" else S.SUREBETS_PATH


def product_name(source: Source) -> str:
    return "valuebets" if source == "valuebet" else "surebets"


def product_table(source: Source) -> str:
    return S.VALUEBETS_TABLE if source == "valuebet" else S.SUREBETS_TABLE


def product_record(source: Source) -> str:
    return S.VALUEBET_RECORD if source == "valuebet" else S.SUREBET_RECORD


def open_product(page: Page, settings: Settings, source: Source) -> None:
    url = f"{settings.base_url}{product_path(source)}"
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_selector(product_table(source), timeout=30_000)


def _filter_select(page: Page):
    # Single control: #filter_current_id + data-testid=filter-saved-select
    testid = page.locator(S.FILTER_SELECT_TESTID)
    if testid.count() > 0:
        return testid.first
    return page.locator(S.FILTER_SELECT).first


def select_filter(
    page: Page,
    surebet_filter_id: str,
    expected_name: str,
    *,
    settings: Settings,
    source: Source,
) -> None:
    """
    Real site behaviour (verified via network on authenticated session):

    Changing #filter_current_id fires a 'change' listener in assets/filter-*.js which
    POSTs /filters/{id}/choose?product=...&return_to=... (GET of that URL is 404),
    then the page navigates back to /valuebets|/surebets with the preset applied.

    So we must: open product → select_option (native change) → wait for POST+reload.
    Skip open_product when already on the same product path (saves a full navigation).
    """
    if not surebet_filter_id or surebet_filter_id in {"separator", "-2"}:
        raise FilterNotFound(f"Invalid filter option value for {expected_name}")

    path = product_path(source)
    already = path in (page.url or "")
    if already:
        try:
            page.wait_for_selector(product_table(source), timeout=5_000)
            page.wait_for_selector(S.FILTER_SELECT, state="attached", timeout=5_000)
            log.info("Already on %s — skip goto", path)
        except PlaywrightTimeout:
            already = False
    if not already:
        open_product(page, settings, source)

    try:
        page.wait_for_selector(S.FILTER_SELECT, state="attached", timeout=20_000)
    except PlaywrightTimeout:
        raise FilterNotFound("Filter select #filter_current_id not found") from None

    sel = _filter_select(page)
    option = sel.locator(f'option[value="{surebet_filter_id}"]')
    try:
        # <option> is never "visible" in Playwright — attached only.
        option.first.wait_for(state="attached", timeout=20_000)
    except PlaywrightTimeout:
        available = [
            f"{opt.get_attribute('value')}={opt.inner_text().strip()}"
            for opt in sel.locator("option").all()
        ]
        raise FilterNotFound(
            f"Filter id={surebet_filter_id} name={expected_name} not in select. "
            f"Available: {available[:20]}"
        ) from None

    current = sel.input_value()
    if current == surebet_filter_id:
        log.info("Filter already selected: %s (%s)", expected_name, surebet_filter_id)
        return

    product = product_name(source)
    choose_substr = f"/filters/{surebet_filter_id}/choose"

    log.info(
        "Selecting filter %s (%s) via <select> → POST %s?product=%s",
        expected_name,
        surebet_filter_id,
        choose_substr,
        product,
    )

    try:
        with page.expect_response(
            lambda r: (
                choose_substr in r.url
                and r.request.method == "POST"
                and r.status < 400
            ),
            timeout=30_000,
        ):
            sel.select_option(value=surebet_filter_id)
    except PlaywrightTimeout as e:
        raise FilterNotFound(
            f"No successful POST to {choose_substr} after selecting {expected_name}"
        ) from e

    # Site reloads the product page after choose.
    try:
        page.wait_for_url(f"**{product_path(source)}**", timeout=30_000)
    except PlaywrightTimeout:
        # still ok if already on product path / query variants
        pass
    try:
        page.wait_for_selector(product_table(source), timeout=30_000)
        page.wait_for_selector(S.FILTER_SELECT, state="attached", timeout=20_000)
    except PlaywrightTimeout as e:
        raise FilterNotFound(
            f"Product page did not reload after choosing {expected_name}"
        ) from e

    sel = _filter_select(page)
    deadline = time.time() + 15
    selected = None
    while time.time() < deadline:
        try:
            selected = sel.input_value()
            if selected == surebet_filter_id:
                break
        except Exception:
            sel = _filter_select(page)
        page.wait_for_timeout(200)

    if selected != surebet_filter_id:
        raise FilterNotFound(
            f"Filter did not stick: want {surebet_filter_id}, got {selected}"
        )

    label = sel.locator("option:checked").first.inner_text().strip()
    if expected_name and expected_name not in label and label not in expected_name:
        log.warning("Selected label %r vs expected %r (id matched)", label, expected_name)
    log.info("Filter selected: %s (%s)", label, surebet_filter_id)


def wait_for_results(page: Page, source: Source, timeout_s: float = 45.0) -> ResultsState:
    table = product_table(source)
    record = product_record(source)
    deadline = time.time() + timeout_s

    try:
        page.wait_for_selector(table, timeout=min(15_000, timeout_s * 1000))
    except PlaywrightTimeout:
        return ResultsState.ERROR

    last_count = -1
    stable = 0
    while time.time() < deadline:
        body = ""
        try:
            body = page.locator("body").inner_text(timeout=2_000)
        except Exception:
            pass

        for hint in S.EMPTY_HINTS:
            if hint.casefold() in body.casefold():
                if page.locator(record).count() == 0:
                    return ResultsState.EMPTY

        count = page.locator(record).count()
        if count > 0:
            if count == last_count:
                stable += 1
            else:
                stable = 0
                last_count = count
            if stable >= 2:
                return ResultsState.RESULTS
        else:
            if "encontrado 0" in body.casefold() or "encontradas 0" in body.casefold():
                return ResultsState.EMPTY

        page.wait_for_timeout(500)

    if page.locator(record).count() > 0:
        return ResultsState.RESULTS
    return ResultsState.TIMEOUT


def take_results_screenshot(page: Page, path: str, source: Source) -> None:
    table = page.locator(product_table(source))
    if table.count() > 0:
        table.first.screenshot(path=path)
    else:
        page.screenshot(path=path, full_page=False)
