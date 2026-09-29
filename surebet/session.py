"""Browser storage_state helpers (session cookies — never commit)."""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from surebet.config import ROOT, Settings

log = logging.getLogger(__name__)

DEFAULT_STORAGE_PATH = ROOT / "storage_state.json"


def storage_state_path_from_env() -> Optional[Path]:
    """
    Resolve Playwright storage_state file.

    Env (first match wins):
    - SUREBET_STORAGE_STATE_PATH → path to JSON file
    - SUREBET_STORAGE_STATE_B64 → base64 of storage_state.json (GitHub Secret)
    - SUREBET_STORAGE_STATE → path OR raw JSON string
    - ./storage_state.json if exists
    """
    path_env = os.getenv("SUREBET_STORAGE_STATE_PATH", "").strip()
    if path_env:
        p = Path(path_env)
        if p.is_file():
            return p
        log.warning("SUREBET_STORAGE_STATE_PATH set but missing: %s", p)

    b64 = os.getenv("SUREBET_STORAGE_STATE_B64", "").strip()
    if b64:
        raw = base64.b64decode(b64)
        # validate json
        json.loads(raw)
        fd, name = tempfile.mkstemp(prefix="surebet_storage_", suffix=".json")
        os.close(fd)
        path = Path(name)
        path.write_bytes(raw)
        log.info("Loaded storage_state from SUREBET_STORAGE_STATE_B64 → %s", path)
        return path

    inline = os.getenv("SUREBET_STORAGE_STATE", "").strip()
    if inline:
        p = Path(inline)
        if p.is_file():
            return p
        # treat as raw JSON
        json.loads(inline)
        fd, name = tempfile.mkstemp(prefix="surebet_storage_", suffix=".json")
        os.close(fd)
        path = Path(name)
        path.write_text(inline, encoding="utf-8")
        log.info("Loaded storage_state from SUREBET_STORAGE_STATE JSON")
        return path

    if DEFAULT_STORAGE_PATH.is_file():
        return DEFAULT_STORAGE_PATH

    return None


def file_to_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def export_storage_interactive(settings: Settings, out: Path = DEFAULT_STORAGE_PATH) -> Path:
    """
    Open headed Chromium. User logs in manually (CAPTCHA if needed).
    When authenticated, save storage_state.json.
    """
    from playwright.sync_api import sync_playwright

    from surebet import selectors as S
    from surebet.auth import is_authenticated

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("EXPORT STORAGE STATE")
    print("1) Vai abrir Chromium headed")
    print("2) Faz LOGIN na SureBet (resolve CAPTCHA manualmente se aparecer)")
    print("3) Quando estiveres autenticado (vê 'Sair'), espera — o script deteta sozinho")
    print(f"4) Grava em: {out}")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(locale="pt-PT", viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(f"{settings.base_url}{S.LOGIN_PATH}", wait_until="domcontentloaded")

        # Wait up to 10 minutes for manual login
        deadline_ms = 600_000
        try:
            page.wait_for_selector(S.AUTH_SIGNOUT, timeout=deadline_ms)
        except Exception:
            # maybe already navigated; check once more
            page.goto(f"{settings.base_url}{S.VALUEBETS_PATH}", wait_until="domcontentloaded")
            page.wait_for_selector(S.AUTH_SIGNOUT, timeout=60_000)

        if not is_authenticated(page):
            browser.close()
            raise RuntimeError("Not authenticated — cannot export storage_state")

        # land on valuebets to ensure product cookies set
        page.goto(f"{settings.base_url}{S.VALUEBETS_PATH}", wait_until="domcontentloaded")
        context.storage_state(path=str(out))
        browser.close()

    b64 = file_to_b64(out)
    print()
    print(f"OK saved {out} ({out.stat().st_size} bytes)")
    print()
    print("GitHub Secret SUREBET_STORAGE_STATE_B64 = (cole o bloco abaixo, uma linha):")
    print(b64)
    print()
    print("Renova este secret quando a sessão expirar (logout / dias sem uso).")
    return out
