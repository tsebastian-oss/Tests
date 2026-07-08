from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from .normalize import clean_price, clean_text, clean_year, infer_from_title, normalize_brand, pick_first
from .sitemap import fetch_sitemap_urls


DEFAULT_SITEMAP = "https://chileautos.cl/sitemaps/chileautos/stock-listings.xml"
DEFAULT_ROBOTS = "https://www.chileautos.cl/robots.txt"
DEFAULT_UA = "AutoPriceRadarBot/0.1"


def _iter_json_objects(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _iter_json_objects(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _iter_json_objects(value)


def _deep_find(obj: Any, candidate_keys: list[str]) -> Any:
    keys = {k.lower() for k in candidate_keys}
    for node in _iter_json_objects(obj):
        for key, value in node.items():
            if str(key).lower() in keys and value not in (None, "", []):
                return value
    return None


def _json_ld_blocks(soup: BeautifulSoup) -> list[dict]:
    blocks: list[dict] = []
    for tag in soup.find_all("script", type=lambda x: x and "ld+json" in x):
        try:
            data = json.loads(tag.string or tag.get_text() or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            blocks.extend(x for x in data if isinstance(x, dict))
        elif isinstance(data, dict):
            blocks.append(data)
    return blocks


def _next_data(soup: BeautifulSoup) -> dict | None:
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag:
        return None
    try:
        return json.loads(tag.string or tag.get_text() or "{}")
    except json.JSONDecodeError:
        return None


def _parse_from_json(soup: BeautifulSoup) -> dict:
    data_sources: list[Any] = []
    data_sources.extend(_json_ld_blocks(soup))
    nd = _next_data(soup)
    if nd:
        data_sources.append(nd)

    merged = {"title": None, "brand": None, "model": None, "version": None, "year": None, "sale_price": None}

    for data in data_sources:
        title = _deep_find(data, ["name", "title", "heading"])
        brand = _deep_find(data, ["brand", "make", "manufacturer", "vehiclemake"])
        model = _deep_find(data, ["model", "vehiclemodel"])
        version = _deep_find(data, ["version", "variant", "trim", "badge", "subtitle"])
        year = _deep_find(data, ["year", "vehiclemodeldate", "modelyear"])
        price = _deep_find(data, ["price", "saleprice", "amount", "priceamount"])

        if isinstance(brand, dict):
            brand = brand.get("name")
        if isinstance(price, dict):
            price = price.get("price") or price.get("amount") or price.get("value")

        merged["title"] = pick_first(merged["title"], title)
        merged["brand"] = pick_first(merged["brand"], brand)
        merged["model"] = pick_first(merged["model"], model)
        merged["version"] = pick_first(merged["version"], version)
        merged["year"] = merged["year"] or clean_year(year)
        merged["sale_price"] = merged["sale_price"] or clean_price(price)

    return merged


def _parse_meta(soup: BeautifulSoup) -> dict:
    title = None
    for selector in [("meta", {"property": "og:title"}), ("meta", {"name": "title"}), ("title", {})]:
        tag = soup.find(*selector)
        if not tag:
            continue
        title = tag.get("content") if tag.name == "meta" else tag.get_text()
        if title:
            break

    description = None
    tag = soup.find("meta", {"name": "description"})
    if tag:
        description = tag.get("content")

    text = " ".join(x for x in [title, description] if x)
    price = None
    for pattern in [r"\$\s?[\d\.\,]{6,}", r"CLP\s?[\d\.\,]{6,}"]:
        m = re.search(pattern, text, flags=re.I)
        if m:
            price = clean_price(m.group(0))
            break

    inferred = infer_from_title(title)
    return {
        "title": clean_text(title),
        "brand": inferred.get("brand"),
        "model": inferred.get("model"),
        "version": inferred.get("version"),
        "year": inferred.get("year"),
        "sale_price": price,
    }


def parse_listing(html: str, url: str, captured_at: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    by_json = _parse_from_json(soup)
    by_meta = _parse_meta(soup)
    title = pick_first(by_json.get("title"), by_meta.get("title"))
    inferred = infer_from_title(title)

    return {
        "source": "chileautos",
        "url": url,
        "brand": normalize_brand(pick_first(by_json.get("brand"), by_meta.get("brand"), inferred.get("brand"))),
        "model": clean_text(pick_first(by_json.get("model"), by_meta.get("model"), inferred.get("model"))),
        "version": clean_text(pick_first(by_json.get("version"), by_meta.get("version"), inferred.get("version"))),
        "year": by_json.get("year") or by_meta.get("year") or inferred.get("year"),
        "sale_price": by_json.get("sale_price") or by_meta.get("sale_price"),
        "currency": "CLP",
        "captured_at": captured_at,
    }


def robots_allowed(url: str, user_agent: str = DEFAULT_UA, robots_url: str = DEFAULT_ROBOTS) -> bool:
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception:
        return False
    return parser.can_fetch(user_agent, url)


def scrape_chileautos(
    sitemap_url: str = DEFAULT_SITEMAP,
    max_listings: int = 100,
    delay_seconds: float = 2.0,
    timeout_seconds: float = 25,
    user_agent: str = DEFAULT_UA,
    respect_robots_txt: bool = True,
) -> list[dict]:
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.7",
    }

    items: list[dict] = []
    with httpx.Client(headers=headers, timeout=timeout_seconds, follow_redirects=True) as client:
        urls = fetch_sitemap_urls(sitemap_url, client, limit=max_listings)

        for i, url in enumerate(urls, start=1):
            if respect_robots_txt and not robots_allowed(url, user_agent=user_agent):
                print(f"[skip robots] {url}")
                continue

            try:
                response = client.get(url)
                if response.status_code in (403, 429):
                    print(f"[blocked/rate-limited] {response.status_code} {url}")
                    time.sleep(max(delay_seconds * 4, 10))
                    continue
                response.raise_for_status()
                item = parse_listing(response.text, url=url, captured_at=captured_at)

                if item.get("brand") or item.get("model") or item.get("sale_price"):
                    items.append(item)
                    print(f"[ok {i}/{len(urls)}] {item.get('brand')} {item.get('model')} {item.get('year')} {item.get('sale_price')}")
                else:
                    print(f"[no data] {url}")
            except Exception as exc:
                print(f"[error] {url}: {exc}")

            time.sleep(delay_seconds)

    return items
