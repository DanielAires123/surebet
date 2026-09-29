"""
Headed DOM capture for surebets.
Create debug/READY.txt when authenticated + Surebets filter + table visible.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
READY = ROOT / "READY.txt"
OUT_HTML = ROOT / "surebets_page.html"
OUT_META = ROOT / "surebets_meta.json"
BASE = "https://pt.surebet.com"
START = f"{BASE}/surebets"


def _sanitize(html: str) -> str:
    return re.sub(
        r'(type=["\']password["\'][^>]*value=["\'])[^"\']*',
        r"\1***",
        html,
        flags=re.I,
    )


def wait_for_ready(timeout_s: int = 900) -> None:
    READY.unlink(missing_ok=True)
    print("=" * 60, flush=True)
    print("1) Faz LOGIN se pedido", flush=True)
    print("2) Confirma filtro Surebets + tabela com resultados", flush=True)
    print(f"3) Cria {READY} ou diz 'pronto' no chat", flush=True)
    print("=" * 60, flush=True)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if READY.exists():
            print("READY — a capturar DOM...", flush=True)
            return
        time.sleep(1)
    raise TimeoutError("Timeout a espera de READY.txt")


def dump_structure(page) -> dict:
    return page.evaluate(
        """() => {
        const tables = [...document.querySelectorAll('table')].map((t, i) => ({
          index: i,
          id: t.id || null,
          className: t.className || null,
          rows: t.querySelectorAll('tr').length,
          headers: [...t.querySelectorAll('th')].map(th => th.innerText.trim()).slice(0, 20),
          dataAttrs: Object.fromEntries([...t.attributes].filter(a => a.name.startsWith('data-')).map(a => [a.name, a.value.slice(0,120)])),
        }));
        const selects = [...document.querySelectorAll('select')].map(s => ({
          id: s.id || null,
          name: s.name || null,
          selected: (s.selectedOptions[0] && s.selectedOptions[0].text) || null,
          selectedValue: s.value || null,
          options: [...s.options].slice(0, 40).map(o => ({value: o.value, text: o.text.trim()})),
        }));
        const records = [...document.querySelectorAll('tbody[class*="record"], tbody[data-id], tr[data-id], [class*="surebet_record"], [class*="arb"]')]
          .slice(0, 5)
          .map(el => ({
            tag: el.tagName.toLowerCase(),
            id: el.id || null,
            className: el.className || null,
            attrs: Object.fromEntries([...el.attributes].map(a => [a.name, a.value.slice(0, 200)])),
          }));
        const testids = [...document.querySelectorAll('[data-testid]')].slice(0, 80).map(el => el.getAttribute('data-testid'));
        return {
          url: location.href,
          title: document.title,
          has_fazer_login: document.body.innerText.includes('Fazer login'),
          tables,
          selects,
          records,
          testids: [...new Set(testids)],
        };
      }"""
    )


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(locale="pt-PT", viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(START, wait_until="domcontentloaded")
        wait_for_ready()
        page.wait_for_timeout(1500)

        meta = dump_structure(page)
        OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        OUT_HTML.write_text(_sanitize(page.content()), encoding="utf-8")

        row_html = page.evaluate(
            """() => {
              const el = document.querySelector('tbody[class*="record"]')
                || document.querySelector('table tbody tr');
              return el ? el.outerHTML.slice(0, 12000) : null;
            }"""
        )
        if row_html:
            (ROOT / "surebet_sample_record.html").write_text(row_html, encoding="utf-8")

        print(f"OK url={meta.get('url')}", flush=True)
        print(f"tables={len(meta.get('tables') or [])} records={len(meta.get('records') or [])}", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
