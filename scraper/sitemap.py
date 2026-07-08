from __future__ import annotations

import gzip
import io
import xml.etree.ElementTree as ET

import httpx


def _xml_root(content: bytes) -> ET.Element:
    if content[:2] == b"\x1f\x8b":
        content = gzip.GzipFile(fileobj=io.BytesIO(content)).read()
    return ET.fromstring(content)


def fetch_sitemap_urls(
    sitemap_url: str,
    client: httpx.Client,
    limit: int | None = None,
) -> list[str]:
    """Fetch URLs from a sitemap or sitemap index."""
    response = client.get(sitemap_url)
    response.raise_for_status()

    root = _xml_root(response.content)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    urls: list[str] = []

    sitemap_locs = [el.text for el in root.findall(".//sm:sitemap/sm:loc", ns) if el.text]
    if sitemap_locs:
        for child in sitemap_locs:
            if limit is not None and len(urls) >= limit:
                break
            remaining = None if limit is None else limit - len(urls)
            urls.extend(fetch_sitemap_urls(child, client, remaining))
        return urls[:limit] if limit else urls

    for el in root.findall(".//sm:url/sm:loc", ns):
        if el.text:
            urls.append(el.text.strip())
            if limit is not None and len(urls) >= limit:
                break

    return urls
