import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable


DB_PATH = Path(__file__).resolve().parent.parent / "data" / "autos.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    brand TEXT,
    model TEXT,
    version TEXT,
    year INTEGER,
    sale_price INTEGER,
    currency TEXT DEFAULT 'CLP',
    captured_at TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(url, captured_at)
);

CREATE INDEX IF NOT EXISTS idx_listings_brand_model_year
ON listings(brand, model, year);

CREATE INDEX IF NOT EXISTS idx_listings_captured_at
ON listings(captured_at);
"""


@contextmanager
def connect(db_path: Path = DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def insert_listing(item: dict, db_path: Path = DB_PATH) -> bool:
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO listings
            (source, url, brand, model, version, year, sale_price, currency, captured_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("source"),
                item.get("url"),
                item.get("brand"),
                item.get("model"),
                item.get("version"),
                item.get("year"),
                item.get("sale_price"),
                item.get("currency", "CLP"),
                item.get("captured_at"),
            ),
        )
        return cur.rowcount > 0


def insert_many(items: Iterable[dict], db_path: Path = DB_PATH) -> int:
    inserted = 0
    for item in items:
        if insert_listing(item, db_path):
            inserted += 1
    return inserted
