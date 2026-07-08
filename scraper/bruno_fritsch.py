from __future__ import annotations

import json
import re
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from .normalize import clean_price, clean_text, clean_year, infer_from_title, normalize_brand, pick_first
from .sitemap import fetch_sitemap_urls


DEFAULT_BASE_URL = "https://www.brunofritsch.cl"
DEFAULT_UA = "AutoPriceRadarBot/0.2 (+contact: owner)"

CAR_KEYWORDS = [
    "auto", "autos", "vehiculo", "vehículos", "vehiculos", "nuevo", "nuevos",
    "usado", "usados", "seminuevo", "seminuevos", "stock", "modelo", "modelos",
    "version", "versión", "catalogo", "catálogo", "marca", "marcas",
]

NEGATIVE_KEYWORDS = [
    "blog", "noticia", "noticias", "postventa", "servicio", "mantencion", "mantención",
    "repuesto", "repuestos", "trabaja", "contacto", "sucursal", "politica", "política",
    "privacidad", "terminos", "términos", "financiamiento", "credito", "crédito",
]


def same_domain(url: str, base_url: str) -> bool:
    return urlparse(url).netloc.replace("www.", "") == urlparse(base_url).netloc.replace("www.", "")


def clean_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="", query=parsed.query).geturl()


def looks_like_vehicle_url(url: str, text: str = "") -> bool:
    haystack = f"{url} {text}".lower()
    if any(x in haystack for x in NEGATIVE_KEYWORDS):
        return False
    return any(x in haystack for x in CAR_KEYWORDS)


def _iter_json_objects(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _iter_json_objects(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _iter_json_objects(value)


def _json_blocks(soup: BeautifulSoup) -> list[Any]:
    blocks: list[Any] = []

    for tag in soup.find_all("script", type=lambda x: x and "json" in x.lower()):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            continue

    next_tag = soup.find("script", id="__NEXT_DATA__")
    if next_tag:
        try:
            blocks.append(json.loads(next_tag.string or next_tag.get_text() or "{}"))
        except json.JSONDecodeError:
            pass

    return blocks


def _deep_find_candidates(obj: Any, keys: list[str]) -> list[Any]:
    wanted = {k.lower() for k in keys}
    values: list[Any] = []
    for node in _iter_json_objects(obj):
        for key, value in node.items():
            if str(key).lower() in wanted and value not in (None, "", []):
                values.append(value)
    return values


def _first_json_value(blocks: list[Any], keys: list[str]) -> Any:
    for block in blocks:
        for value in _deep_find_candidates(block, keys):
            if isinstance(value, dict):
                if value.get("name"):
                    return value.get("name")
                if value.get("value"):
                    return value.get("value")
            elif isinstance(value, list):
                continue
            else:
                return value
    return None


def parse_price_from_text(text: str | None) -> int | None:
    if not text:
        return None
    patterns = [
        r"\$\s?[\d\.]{6,}",
        r"CLP\s?[\d\.]{6,}",
        r"Precio\s*(?:lista|desde|final)?\s*[:\-]?\s*\$?\s?[\d\.]{6,}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            price = clean_price(match.group(0))
            if price:
                return price
    return None


def page_title(soup: BeautifulSoup) -> str | None:
    candidates = []
    for selector in [
        ("meta", {"property": "og:title"}),
        ("meta", {"name": "title"}),
        ("h1", {}),
        ("title", {}),
    ]:
        tag = soup.find(*selector)
        if not tag:
            continue
        value = tag.get("content") if tag.name == "meta" else tag.get_text(" ", strip=True)
        if value:
            candidates.append(value)
    return clean_text(candidates[0]) if candidates else None


def parse_vehicle_page(html: str, url: str, captured_at: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    blocks = _json_blocks(soup)
    title = page_title(soup)
    visible_text = clean_text(soup.get_text(" ", strip=True)) or ""
    inferred = infer_from_title(title)

    brand = _first_json_value(blocks, ["brand", "make", "marca", "manufacturer", "vehiclemake"])
    model = _first_json_value(blocks, ["model", "modelo", "vehiclemodel"])
    version = _first_json_value(blocks, ["version", "versión", "variant", "trim", "badge", "subtitle", "name"])
    year = _first_json_value(blocks, ["year", "anio", "año", "modelyear", "vehiclemodeldate"])
    price = _first_json_value(blocks, ["price", "precio", "saleprice", "listprice", "amount", "priceamount"])

    final_brand = normalize_brand(pick_first(brand, inferred.get("brand")))
    final_model = clean_text(pick_first(model, inferred.get("model")))
    final_version = clean_text(pick_first(version, inferred.get("version")))
    final_year = clean_year(year) or inferred.get("year") or clean_year(visible_text)
    final_price = clean_price(price) or parse_price_from_text(visible_text)

    if not any([final_brand, final_model, final_version, final_year, final_price]):
        return None

    # Avoid saving generic pages that do not expose a vehicle or a price.
    if not final_price and not final_model:
        return None

    return {
        "source": "bruno_fritsch",
        "url": url,
        "brand": final_brand,
        "model": final_model,
        "version": final_version,
        "year": final_year,
        "sale_price": final_price,
        "currency": "CLP",
        "captured_at": captured_at,
    }


def discover_links(html: str, page_url: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for tag in soup.find_all("a", href=True):
        href = tag.get("href")
        text = tag.get_text(" ", strip=True)
        absolute = clean_url(urljoin(page_url, href))
        if not same_domain(absolute, base_url):
            continue
        if looks_like_vehicle_url(absolute, text):
            links.append(absolute)
    return list(dict.fromkeys(links))


def build_robots_parser(base_url: str, robots_url: str | None = None) -> RobotFileParser | None:
    robots_url = robots_url or urljoin(base_url, "/robots.txt")
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
        return parser
    except Exception as exc:
        print(f"[robots] could not read robots.txt: {exc}")
        return None


def robots_allowed(url: str, parser: RobotFileParser | None, user_agent: str) -> bool:
    if parser is None:
        return True
    return parser.can_fetch(user_agent, url)


def candidate_sitemaps(base_url: str, configured: list[str] | None = None) -> list[str]:
    candidates = configured or []
    candidates.extend([
        urljoin(base_url, "/sitemap.xml"),
        urljoin(base_url, "/sitemap_index.xml"),
        urljoin(base_url, "/sitemap-index.xml"),
        urljoin(base_url, "/sitemap/sitemap.xml"),
    ])
    return list(dict.fromkeys(candidates))


def seed_candidates(base_url: str, configured: list[str] | None = None) -> list[str]:
    seeds = configured or []
    paths = [
        "/", "/autos", "/autos-nuevos", "/autos-usados", "/vehiculos", "/vehiculos-nuevos",
        "/vehiculos-usados", "/nuevos", "/usados", "/seminuevos", "/stock", "/catalogo",
        "/modelos", "/marcas",
    ]
    seeds.extend(urljoin(base_url, p) for p in paths)
    return list(dict.fromkeys(seeds))


def discover_urls_from_sitemaps(
    client: httpx.Client,
    base_url: str,
    sitemaps: list[str] | None,
    max_urls: int,
) -> list[str]:
    discovered: list[str] = []
    for sitemap_url in candidate_sitemaps(base_url, sitemaps):
        try:
            urls = fetch_sitemap_urls(sitemap_url, client, limit=max_urls)
            vehicle_urls = [u for u in urls if same_domain(u, base_url) and looks_like_vehicle_url(u)]
            if vehicle_urls:
                print(f"[sitemap] {sitemap_url} urls={len(vehicle_urls)}")
                discovered.extend(vehicle_urls)
        except Exception as exc:
            print(f"[sitemap skip] {sitemap_url}: {exc}")
        if len(discovered) >= max_urls:
            break
    return list(dict.fromkeys(discovered))[:max_urls]


def scrape_bruno_fritsch(
    base_url: str = DEFAULT_BASE_URL,
    seed_urls: list[str] | None = None,
    sitemap_urls: list[str] | None = None,
    max_listings: int = 5000,
    max_pages: int | None = None,
    delay_seconds: float = 0.5,
    timeout_seconds: float = 10,
    user_agent: str = DEFAULT_UA,
    respect_robots_txt: bool = True,
) -> list[dict]:
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    max_pages = max_pages or max_listings
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.7",
    }

    items: list[dict] = []
    seen: set[str] = set()
    queue: deque[str] = deque()
    robots_parser = build_robots_parser(base_url) if respect_robots_txt else None
    started = time.perf_counter()

    with httpx.Client(headers=headers, timeout=timeout_seconds, follow_redirects=True) as client:
        sitemap_urls_found = discover_urls_from_sitemaps(client, base_url, sitemap_urls, max_urls=max_pages)
        for url in sitemap_urls_found:
            queue.append(url)
        for url in seed_candidates(base_url, seed_urls):
            queue.append(url)

        total_processed = 0
        print(
            f"[start] source=bruno_fritsch queued={len(queue)} max_listings={max_listings} "
            f"max_pages={max_pages} delay={delay_seconds}s timeout={timeout_seconds}s"
        )

        while queue and total_processed < max_pages and len(items) < max_listings:
            url = queue.popleft()
            if url in seen:
                continue
            seen.add(url)

            if not same_domain(url, base_url):
                continue
            if respect_robots_txt and not robots_allowed(url, robots_parser, user_agent):
                print(f"[skip robots] {url}")
                continue

            t0 = time.perf_counter()
            try:
                response = client.get(url)
                elapsed = time.perf_counter() - t0
                total_processed += 1

                if response.status_code in (403, 429):
                    backoff = min(max(delay_seconds * 4, 5), 15)
                    print(f"[blocked] status={response.status_code} elapsed={elapsed:.2f}s backoff={backoff:.1f}s {url}")
                    time.sleep(backoff)
                    continue
                if response.status_code >= 400:
                    print(f"[skip http] status={response.status_code} {url}")
                    continue

                html = response.text
                item = parse_vehicle_page(html, url, captured_at)
                if item:
                    items.append(item)
                    if len(items) == 1 or len(items) % 25 == 0:
                        avg = (time.perf_counter() - started) / max(total_processed, 1)
                        print(
                            f"[captured] items={len(items)} pages={total_processed} avg={avg:.2f}s/page "
                            f"{item.get('brand')} {item.get('model')} {item.get('version')} {item.get('sale_price')}"
                        )

                for link in discover_links(html, url, base_url):
                    if link not in seen and len(queue) < max_pages * 3:
                        queue.append(link)

            except Exception as exc:
                total_processed += 1
                print(f"[error] {url}: {exc}")

            if delay_seconds > 0:
                time.sleep(delay_seconds)

    elapsed_min = (time.perf_counter() - started) / 60
    print(f"[summary] source=bruno_fritsch captured={len(items)} pages={total_processed} elapsed={elapsed_min:.1f}m")
    return items
