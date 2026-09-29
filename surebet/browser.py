"""Playwright browser lifecycle."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from surebet.config import Settings
from surebet.session import storage_state_path_from_env


class BrowserSession:
    def __init__(self, settings: Settings, *, debug: bool = False, headless: bool = True):
        self.settings = settings
        self.debug = debug
        self.headless = headless
        self._pw = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.storage_state_path: Optional[Path] = None

    def __enter__(self) -> "BrowserSession":
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=self.headless)
        kwargs = {
            "locale": "pt-PT",
            "viewport": {"width": 1440, "height": 900},
        }
        try:
            self.storage_state_path = storage_state_path_from_env()
        except Exception as e:
            raise RuntimeError(f"Invalid storage_state: {e}") from e
        if self.storage_state_path:
            kwargs["storage_state"] = str(self.storage_state_path)
        self.context = self.browser.new_context(**kwargs)
        self.page = self.context.new_page()
        self.page.set_default_timeout(30_000)
        return self

    def __exit__(self, *exc) -> None:
        if self.browser:
            self.browser.close()
        if self._pw:
            self._pw.stop()

    def screenshot(self, name: str, target: Optional[Path] = None) -> Path:
        assert self.page is not None
        directory = target or (self.settings.debug_dir if self.debug else self.settings.screenshots_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        self.page.screenshot(path=str(path), full_page=False)
        return path
