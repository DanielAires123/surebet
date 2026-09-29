"""
Headed DOM capture helper.
1) Opens Chromium (visible)
2) Goes to valuebets
3) Waits until you create debug/READY.txt after login + filter applied
4) Dumps HTML + structural hints (no credentials saved)
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
READY = ROOT / "READY.txt"
OUT_HTML = ROOT / "valuebets_page.html"
OUT_META = ROOT / "valuebets_meta.json"
BASE = "https://pt.surebet.com"


def _sanitize(html: str) -> str:
    # strip obvious secrets if any appear in forms
    html = re.sub(
        r'(type=["\']password["\'][^>]*value=["\'])[^"\']*',
        r'\1***',
        html,
        flags=re.I,
    )
    return html


def wait_for_ready(timeout_s: int = 900) -> None:
    READY.unlink(missing_ok=True)
    print("=" * 60)
    print("1) Faz LOGIN no browser que abriu")
    print("2) Vai a Valuebets e aplica o filtro (ex: 0.7UN)")
    print("3) Quando a tabela estiver visivel, cria o ficheiro:")
    print(f"   {READY}")
    print("   (ou diz 'pronto' no chat e eu crio o ficheiro)")
    print("=" * 60)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if READY.exists():
            print("READY detetado — a capturar DOM...")
            return
        time.sleep(1)
    raise TimeoutError("Timeout a espera de READY.txt")


def dump_structure(page) -> dict:
    return page.evaluate(
        """() => {
        const pick = (el) => {
          if (!el) return null;
          const attrs = {};
          for (const a of el.attributes || []) {
            if (['id','class','name','role','data-testid','href','type','aria-label'].includes(a.name)
                || a.name.startsWith('data-')) {
              attrs[a.name] = a.value.slice(0, 200);
            }
          }
          return {
            tag: el.tagName.toLowerCase(),
            attrs,
            text: (el.innerText || '').trim().slice(0, 160),
          };
        };

        const tables = [...document.querySelectorAll('table')].map((t, i) => ({
          index: i,
          id: t.id || null,
          className: t.className || null,
          rows: t.querySelectorAll('tr').length,
          headers: [...t.querySelectorAll('th')].map(th => th.innerText.trim()).slice(0, 20),
          first_row_cells: [...(t.querySelector('tbody tr') || t.querySelector('tr:nth-child(2)') || {children:[]}).children]
            .map(td => ({
              tag: td.tagName.toLowerCase(),
              className: td.className || null,
              text: (td.innerText || '').trim().slice(0, 120),
              html: td.innerHTML.slice(0, 400),
              links: [...td.querySelectorAll('a')].map(a => ({
                href: a.getAttribute('href'),
                text: (a.innerText || '').trim().slice(0, 80),
                className: a.className || null,
              })),
            })),
        }));

        const selects = [...document.querySelectorAll('select')].map(s => ({
          id: s.id || null,
          name: s.name || null,
          className: s.className || null,
          selected: (s.selectedOptions[0] && s.selectedOptions[0].text) || null,
          options: [...s.options].slice(0, 30).map(o => o.text.trim()),
        }));

        const filterLabels = [...document.querySelectorAll('label, [class*="filter"], [id*="filter"]')]
          .slice(0, 40)
          .map(pick);

        const loginHints = {
          has_fazer_login: !!document.body.innerText.includes('Fazer login'),
          has_logout_or_profile: !!(
            document.body.innerText.match(/Sair|Logout|Perfil|Account/i)
          ),
        };

        const sampleLinks = [...document.querySelectorAll('a[href*="valuebet"], a[href*="prong"], a[href*="bookie"], a[href*="filters"]')]
          .slice(0, 30)
          .map(a => ({ href: a.getAttribute('href'), text: (a.innerText||'').trim().slice(0,80), className: a.className||null }));

        return {
          url: location.href,
          title: document.title,
          loginHints,
          tables,
          selects,
          filterLabels,
          sampleLinks,
          bodyClasses: document.body.className || null,
        };
      }"""
    )


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(locale="pt-PT", viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(f"{BASE}/valuebets", wait_until="domcontentloaded")
        wait_for_ready()

        # optional: if still on login, wait a bit more for redirect
        page.wait_for_timeout(1500)

        meta = dump_structure(page)
        OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        OUT_HTML.write_text(_sanitize(page.content()), encoding="utf-8")

        # first result row outerHTML if table exists
        row_html = page.evaluate(
            """() => {
              const tr = document.querySelector('table tbody tr') || document.querySelector('table tr');
              return tr ? tr.outerHTML.slice(0, 8000) : null;
            }"""
        )
        if row_html:
            (ROOT / "sample_row.html").write_text(row_html, encoding="utf-8")

        print(f"OK url={meta.get('url')}")
        print(f"tables={len(meta.get('tables') or [])} selects={len(meta.get('selects') or [])}")
        print(f"wrote {OUT_META.name}, {OUT_HTML.name}")
        browser.close()


if __name__ == "__main__":
    main()
