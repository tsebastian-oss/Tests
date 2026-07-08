import re
import unicodedata
from typing import Any


COMMON_BRANDS = [
    "Abarth", "Alfa Romeo", "Audi", "BAIC", "BMW", "BYD", "Changan", "Chery",
    "Chevrolet", "Citroen", "Citroën", "DFSK", "Dodge", "Dongfeng", "DS",
    "Exeed", "Fiat", "Ford", "Foton", "GAC", "Geely", "Great Wall", "Haval",
    "Honda", "Hyundai", "JAC", "Jaguar", "Jeep", "Jetour", "JMC", "Kia",
    "Land Rover", "Lexus", "Mahindra", "Mazda", "Mercedes-Benz", "MG",
    "Mini", "Mitsubishi", "Nissan", "Opel", "Peugeot", "Porsche", "RAM",
    "Renault", "Seat", "Skoda", "SsangYong", "Subaru", "Suzuki", "Tesla",
    "Toyota", "Volkswagen", "Volvo",
]


def strip_accents(value: str) -> str:
    value = unicodedata.normalize("NFD", str(value or ""))
    return "".join(c for c in value if unicodedata.category(c) != "Mn")


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def clean_price(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value > 0:
            return int(round(value))
        return None

    text = str(value)
    text = text.replace("\xa0", " ")
    # Chilean prices usually look like $10.490.000 or CLP 10490000.
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None

    price = int(digits)
    # Avoid capturing tiny numbers such as years or installments.
    if price < 100_000:
        return None
    return price


def clean_year(value: Any) -> int | None:
    if value is None:
        return None
    m = re.search(r"(19[8-9]\d|20[0-3]\d)", str(value))
    if not m:
        return None
    year = int(m.group(1))
    if 1980 <= year <= 2035:
        return year
    return None


def normalize_brand(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    cmp = strip_accents(text).lower()
    for brand in COMMON_BRANDS:
        if strip_accents(brand).lower() == cmp:
            return brand.replace("Citroen", "Citroën")
    return text.title()


def infer_from_title(title: str | None) -> dict:
    """Fallback parser for titles such as 'Peugeot 2008 1.2 Allure 2022'."""
    title = clean_text(title)
    if not title:
        return {"brand": None, "model": None, "version": None, "year": None}

    year = clean_year(title)
    without_year = re.sub(r"\b(19[8-9]\d|20[0-3]\d)\b", "", title).strip()

    brand = None
    rest = without_year
    for b in sorted(COMMON_BRANDS, key=len, reverse=True):
        if strip_accents(without_year).lower().startswith(strip_accents(b).lower()):
            brand = b.replace("Citroen", "Citroën")
            rest = without_year[len(b):].strip(" -|/")
            break

    if not brand:
        parts = without_year.split()
        brand = parts[0].title() if parts else None
        rest = " ".join(parts[1:])

    parts = rest.split()
    model = parts[0] if parts else None
    version = " ".join(parts[1:]) if len(parts) > 1 else None

    return {
        "brand": normalize_brand(brand),
        "model": clean_text(model),
        "version": clean_text(version),
        "year": year,
    }


def pick_first(*values):
    for value in values:
        cleaned = clean_text(value)
        if cleaned:
            return cleaned
    return None
