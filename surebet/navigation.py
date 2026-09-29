"""Product navigation + filter selection + wait_for_results."""

from __future__ import annotations

import logging
import time
from typing import Literal

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from surebet import selectors as S
from surebet.config import Settings
from surebet.exceptions import FilterNotFound, ResultsTimeout
from surebet.models import ResultsState

log = logging.getLogger(__name__)

Source = Literal["valuebet", "surebet"]


def product_path(source: Source) -> str:
    return S.VALUEBETS_PATH if source == "valuebet" else S.SUREBETS_PATH


def product_table(source: Source) -> str:
    return S.VALUEBETS_TABLE if source == "valuebet" else S.SUREBETS_TABLE


def product_record(source: Source) -> str:
    return S.VALUEBET_RECORD if source == "valuebet" else S.SUREBET_RECORD


def open_product(page: Page, settings: Settings, source: Source) -> None:
    url = f"{settings.base_url}{product_path(source)}"
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_selector(product_table(source), timeout=30_000)


def select_filter(page: Page, surebet_filter_id: str, expected_name: str) -> None:
    # Site can render multiple #filter_current_id; drive the first visible select.
    sel = page.locator(S.FILTER_SELECT).first
    try:
        sel.wait_for(state="attached", timeout=20_000)
    except PlaywrightTimeout:
        raise FilterNotFound("Filter select #filter_current_id not found") from None

    # <option> nodes are "hidden" in Playwright — wait attached, never visible.
    option = sel.locator(f'option[value="{surebet_filter_id}"]')
    try:
        option.first.wait_for(state="attached", timeout=20_000)
    except PlaywrightTimeout:
        available = []
        for opt in sel.locator("option").all():
            available.append(f"{opt.get_attribute('value')}={opt.inner_text().strip()}")
        raise FilterNotFound(
            f"Filter id={surebet_filter_id} name={expected_name} not in select. "
            f"Available: {available[:20]}"
        ) from None

    value = option.first.get_attribute("value")
    if not value or value in {"separator", "-2"}:
        raise FilterNotFound(f"Invalid filter option value for {expected_name}")

    current = sel.input_value()
    if current != value:
        sel.select_option(value=value)
        apply_btn = page.locator(S.FILTER_APPLY)
        if apply_btn.count() > 0:
            apply_btn.first.click()
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeout:
                pass
        else:
            page.wait_for_timeout(1500)

    selected = sel.input_value()
    if selected != value:
        raise FilterNotFound(f"Filter did not stick: want {value}, got {selected}")

    selected_label = sel.locator("option:checked").first.inner_text().strip()
    if expected_name and expected_name not in selected_label and selected_label not in expected_name:
        log.warning("Selected label %r vs expected %r (id matched)", selected_label, expected_name)
    log.info("Filter selected: %s (%s)", selected_label, value)


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
            # "Encontrado 0" style
            if "encontrado 0" in body.casefold() or "encontradas 0" in body.casefold():
                return ResultsState.EMPTY

        page.wait_for_timeout(500)

    # final check
    if page.locator(record).count() > 0:
        return ResultsState.RESULTS
    return ResultsState.TIMEOUT


def take_results_screenshot(page: Page, path: str, source: Source) -> None:
    table = page.locator(product_table(source))
    if table.count() > 0:
        table.first.screenshot(path=path)
    else:
        page.screenshot(path=path, full_page=False)
