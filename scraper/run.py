from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from .chileautos import scrape_chileautos
from .db import DB_PATH, init_db, insert_many


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "sources.yaml"
EXPORTS_DIR = ROOT / "exports"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def export_latest(db_path: Path = DB_PATH) -> None:
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

    csv_path = EXPORTS_DIR / "chileautos_listings_latest.csv"
    xlsx_path = EXPORTS_DIR / "chileautos_listings_latest.xlsx"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_path, index=False)
    print(f"[export] {csv_path}")
    print(f"[export] {xlsx_path}")


def main() -> None:
    cfg = load_config()["chileautos"]

    parser = argparse.ArgumentParser()
    parser.add_argument("--sitemap", default=cfg["sitemap_url"])
    parser.add_argument("--max-listings", type=int, default=int(cfg.get("max_listings_per_run", 100)))
    parser.add_argument("--delay", type=float, default=float(cfg.get("delay_seconds", 2.0)))
    parser.add_argument("--timeout", type=float, default=float(cfg.get("timeout_seconds", 25)))
    parser.add_argument("--user-agent", default=cfg.get("user_agent", "AutoPriceRadarBot/0.1"))
    parser.add_argument("--no-robots-check", action="store_true")
    args = parser.parse_args()

    init_db()

    items = scrape_chileautos(
        sitemap_url=args.sitemap,
        max_listings=args.max_listings,
        delay_seconds=args.delay,
        timeout_seconds=args.timeout,
        user_agent=args.user_agent,
        respect_robots_txt=not args.no_robots_check and bool(cfg.get("respect_robots_txt", True)),
    )

    inserted = insert_many(items)
    print(f"[done] scraped={len(items)} inserted={inserted}")
    export_latest()


if __name__ == "__main__":
    main()
