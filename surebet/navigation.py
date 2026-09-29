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


def _set_select_value(sel, value: str) -> None:
    """Set <select> value in a way Rails/jQuery UIs actually notice."""
    try:
        sel.select_option(value=value, timeout=5_000)
    except Exception as e:
        log.warning("select_option failed (%s)", e)
    # Always fire native + jQuery change (SureBet sidebar is jQuery-driven).
    sel.evaluate(
        """(el, v) => {
            el.value = v;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            if (window.jQuery) {
                window.jQuery(el).val(v).trigger('change');
            }
        }""",
        value,
    )


def _apply_filter_ui(page: Page) -> None:
    apply_btn = page.locator(S.FILTER_APPLY)
    if apply_btn.count() > 0 and apply_btn.first.is_visible():
        apply_btn.first.click()
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except PlaywrightTimeout:
            pass
    else:
        page.wait_for_timeout(800)


def _filter_select(page: Page):
    """Prefer the interactive saved-filter control (testid / visible)."""
    testid = page.locator(S.FILTER_SELECT_TESTID)
    if testid.count() > 0:
        return testid.first
    loc = page.locator(S.FILTER_SELECT)
    n = loc.count()
    for i in range(n):
        cand = loc.nth(i)
        try:
            if cand.is_visible():
                return cand
        except Exception:
            continue
    return loc.first


def select_filter(page: Page, surebet_filter_id: str, expected_name: str) -> None:
    try:
        page.wait_for_selector(S.FILTER_SELECT, state="attached", timeout=20_000)
    except PlaywrightTimeout:
        raise FilterNotFound("Filter select #filter_current_id not found") from None

    # Collect candidates: testid first, then every #filter_current_id (duplicates exist).
    candidates = []
    testid = page.locator(S.FILTER_SELECT_TESTID)
    for i in range(testid.count()):
        candidates.append(testid.nth(i))
    loc = page.locator(S.FILTER_SELECT)
    for i in range(loc.count()):
        candidates.append(loc.nth(i))
    if not candidates:
        raise FilterNotFound("Filter select #filter_current_id not found")

    # Probe first candidate for option presence / availability list.
    probe = _filter_select(page)
    option = probe.locator(f'option[value="{surebet_filter_id}"]')
    try:
        option.first.wait_for(state="attached", timeout=20_000)
    except PlaywrightTimeout:
        available = []
        for opt in probe.locator("option").all():
            available.append(f"{opt.get_attribute('value')}={opt.inner_text().strip()}")
        raise FilterNotFound(
            f"Filter id={surebet_filter_id} name={expected_name} not in select. "
            f"Available: {available[:20]}"
        ) from None

    value = option.first.get_attribute("value")
    if not value or value in {"separator", "-2"}:
        raise FilterNotFound(f"Invalid filter option value for {expected_name}")

    if probe.input_value() == value:
        selected_label = probe.locator("option:checked").first.inner_text().strip()
        log.info("Filter already selected: %s (%s)", selected_label, value)
        return

    last_got = probe.input_value()
    for sel in candidates:
        try:
            if sel.locator(f'option[value="{value}"]').count() == 0:
                continue
            _set_select_value(sel, value)
            _apply_filter_ui(page)
            # DOM may remount after choose/apply — re-resolve.
            page.wait_for_timeout(500)
            check = _filter_select(page)
            deadline = time.time() + 8
            while time.time() < deadline:
                try:
                    last_got = check.input_value()
                    if last_got == value:
                        selected_label = check.locator("option:checked").first.inner_text().strip()
                        if expected_name and expected_name not in selected_label and selected_label not in expected_name:
                            log.warning(
                                "Selected label %r vs expected %r (id matched)",
                                selected_label,
                                expected_name,
                            )
                        log.info("Filter selected: %s (%s)", selected_label, value)
                        return
                except Exception:
                    check = _filter_select(page)
                page.wait_for_timeout(250)
        except Exception as e:
            log.warning("filter select candidate failed: %s", e)
            continue

    raise FilterNotFound(f"Filter did not stick: want {value}, got {last_got}")


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
