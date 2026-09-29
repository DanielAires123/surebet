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
    # Network: /filters/{id}/choose?product=valuebets|surebets
    return "valuebets" if source == "valuebet" else "surebets"


def product_table(source: Source) -> str:
    return S.VALUEBETS_TABLE if source == "valuebet" else S.SUREBETS_TABLE


def product_record(source: Source) -> str:
    return S.VALUEBET_RECORD if source == "valuebet" else S.SUREBET_RECORD


def choose_filter_url(settings: Settings, source: Source, surebet_filter_id: str) -> str:
    product = product_name(source)
    ret = product_path(source)
    return (
        f"{settings.base_url}/filters/{surebet_filter_id}/choose"
        f"?product={product}&return_to={ret}"
    )


def open_product(page: Page, settings: Settings, source: Source) -> None:
    url = f"{settings.base_url}{product_path(source)}"
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_selector(product_table(source), timeout=30_000)


def _filter_select(page: Page):
    testid = page.locator(S.FILTER_SELECT_TESTID)
    if testid.count() > 0:
        return testid.first
    loc = page.locator(S.FILTER_SELECT)
    for i in range(loc.count()):
        cand = loc.nth(i)
        try:
            if cand.is_visible():
                return cand
        except Exception:
            continue
    return loc.first


def _read_selected_filter_id(page: Page) -> str | None:
    try:
        sel = _filter_select(page)
        return sel.input_value()
    except Exception:
        return None


def select_filter(
    page: Page,
    surebet_filter_id: str,
    expected_name: str,
    *,
    settings: Settings,
    source: Source,
) -> None:
    """
    Apply saved preset the same way the UI does:
    GET /filters/{id}/choose?product=...&return_to=...
    (session-bound; cold unauthenticated goto can 404).
    """
    if not surebet_filter_id or surebet_filter_id in {"separator", "-2"}:
        raise FilterNotFound(f"Invalid filter option value for {expected_name}")

    current = _read_selected_filter_id(page)
    if current == surebet_filter_id:
        log.info("Filter already selected: %s (%s)", expected_name, surebet_filter_id)
        return

    url = choose_filter_url(settings, source, surebet_filter_id)
    log.info("Choosing filter via %s", url)
    resp = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    status = resp.status if resp else None
    if status and status >= 400:
        # Fallback: land on product page and try native select (last resort).
        log.warning("choose URL returned %s — falling back to <select>", status)
        open_product(page, settings, source)
        _select_via_dom(page, surebet_filter_id, expected_name)
        return

    try:
        page.wait_for_selector(product_table(source), timeout=30_000)
    except PlaywrightTimeout as e:
        raise FilterNotFound(
            f"After choose, product table missing for {expected_name} (HTTP {status})"
        ) from e

    # Wait for select to reflect the chosen preset (redirect may remount DOM).
    deadline = time.time() + 15
    selected = None
    while time.time() < deadline:
        selected = _read_selected_filter_id(page)
        if selected == surebet_filter_id:
            break
        page.wait_for_timeout(250)

    if selected != surebet_filter_id:
        # choose may have applied server-side even if select lags — try DOM once.
        log.warning(
            "choose done but select shows %r (want %s) — DOM fallback",
            selected,
            surebet_filter_id,
        )
        _select_via_dom(page, surebet_filter_id, expected_name)
        return

    label = ""
    try:
        label = _filter_select(page).locator("option:checked").first.inner_text().strip()
    except Exception:
        label = expected_name
    if expected_name and label and expected_name not in label and label not in expected_name:
        log.warning("Selected label %r vs expected %r (id matched)", label, expected_name)
    log.info("Filter selected: %s (%s)", label or expected_name, surebet_filter_id)


def _select_via_dom(page: Page, surebet_filter_id: str, expected_name: str) -> None:
    try:
        page.wait_for_selector(S.FILTER_SELECT, state="attached", timeout=20_000)
    except PlaywrightTimeout:
        raise FilterNotFound("Filter select #filter_current_id not found") from None

    sel = _filter_select(page)
    option = sel.locator(f'option[value="{surebet_filter_id}"]')
    if option.count() == 0:
        available = []
        for opt in sel.locator("option").all():
            available.append(f"{opt.get_attribute('value')}={opt.inner_text().strip()}")
        raise FilterNotFound(
            f"Filter id={surebet_filter_id} name={expected_name} not in select. "
            f"Available: {available[:20]}"
        )

    # Use data-product / data-return-to like the site's own change handler.
    sel.evaluate(
        """(el, v) => {
            el.value = v;
            const product = el.getAttribute('data-product') || 'valuebets';
            const ret = el.getAttribute('data-return-to') || ('/' + product);
            const url = '/filters/' + encodeURIComponent(v)
                + '/choose?product=' + encodeURIComponent(product)
                + '&return_to=' + encodeURIComponent(ret);
            window.location.assign(url);
        }""",
        surebet_filter_id,
    )
    try:
        page.wait_for_load_state("domcontentloaded", timeout=30_000)
    except PlaywrightTimeout:
        pass
    page.wait_for_timeout(500)

    selected = _read_selected_filter_id(page)
    if selected != surebet_filter_id:
        raise FilterNotFound(
            f"Filter did not stick: want {surebet_filter_id}, got {selected}"
        )
    log.info("Filter selected via DOM navigate: %s (%s)", expected_name, surebet_filter_id)


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
