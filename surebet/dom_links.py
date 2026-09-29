"""Extract absolute bookmaker/event/odds hrefs from SureBet DOM legs."""

from __future__ import annotations

from typing import Optional
from urllib.parse import urljoin


def absolute_url(href: Optional[str], base_url: str) -> Optional[str]:
    if not href or href.startswith("#") or href.lower().startswith("javascript:"):
        return None
    href = href.strip()
    if not href:
        return None
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(base_url.rstrip("/") + "/", href.lstrip("/"))


def first_href(locator, base_url: str) -> Optional[str]:
    """Best-effort: element itself or first descendant <a>."""
    if locator.count() == 0:
        return None
    el = locator.first
    href = el.get_attribute("href")
    if href:
        return absolute_url(href, base_url)
    a = el.locator("a[href]")
    if a.count() == 0:
        return None
    return absolute_url(a.first.get_attribute("href"), base_url)
