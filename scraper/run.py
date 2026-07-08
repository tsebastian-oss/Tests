from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from .bruno_fritsch import scrape_bruno_fritsch
from .chileautos import scrape_chileautos
from .db import DB_PATH, init_db, insert_many


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "sources.yaml"
EXPORTS_DIR = ROOT / "exports"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def export_latest(source: str, db_path: Path = DB_PATH) -> None:
    EXPORTS_DIR.mkdir(exist_ok=True)
    import sqlite3

    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        """
        SELECT source, url, brand, model, version, year, sale_price, currency, captured_at
        FROM listings
        ORDER BY captured_at DESC, brand, model, year
        """,
        conn,
    )
    conn.close()

    if df.empty:
        print("[export] no rows")
        return

    safe_source = source.replace("-", "_")
    csv_path = EXPORTS_DIR / f"{safe_source}_listings_latest.csv"
    xlsx_path = EXPORTS_DIR / f"{safe_source}_listings_latest.xlsx"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_path, index=False)
    print(f"[export] {csv_path}")
    print(f"[export] {xlsx_path}")


def main() -> None:
    all_cfg = load_config()
    default_source = all_cfg.get("default_source", "bruno_fritsch")

    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=default_source, choices=["bruno_fritsch", "chileautos"])
    parser.add_argument("--max-listings", type=int, default=None)
    parser.add_argument("--delay", type=float, default=None)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--user-agent", default=None)
    parser.add_argument("--no-robots-check", action="store_true")
    args = parser.parse_args()

    cfg = all_cfg[args.source]
    max_listings = args.max_listings or int(cfg.get("max_listings_per_run", 5000))
    delay_seconds = args.delay if args.delay is not None else float(cfg.get("delay_seconds", 0.5))
    timeout_seconds = args.timeout if args.timeout is not None else float(cfg.get("timeout_seconds", 10))
    user_agent = args.user_agent or cfg.get("user_agent", "AutoPriceRadarBot/0.2")
    respect_robots = not args.no_robots_check and bool(cfg.get("respect_robots_txt", True))

    init_db()

    if args.source == "bruno_fritsch":
        items = scrape_bruno_fritsch(
            base_url=cfg.get("base_url", "https://www.brunofritsch.cl"),
            seed_urls=cfg.get("seed_urls", []),
            sitemap_urls=cfg.get("sitemap_urls", []),
            max_listings=max_listings,
            max_pages=int(cfg.get("max_pages_per_run", max_listings)),
            delay_seconds=delay_seconds,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
            respect_robots_txt=respect_robots,
        )
    else:
        items = scrape_chileautos(
            sitemap_url=cfg.get("sitemap_url"),
            max_listings=max_listings,
            delay_seconds=delay_seconds,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
            respect_robots_txt=respect_robots,
        )

    inserted = insert_many(items)
    print(f"[done] source={args.source} scraped={len(items)} inserted={inserted}")
    export_latest(args.source)


if __name__ == "__main__":
    main()
