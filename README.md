# Auto Price Radar

MVP para monitorear autos usados publicados en Chileautos y guardar solo:

- marca
- modelo
- versión
- año
- precio de venta
- URL
- fecha de captura

La primera versión usa el sitemap público de stock listings como punto de entrada, aplica rate limit, guarda en SQLite y exporta CSV/Excel.

> Importante: usa esto de forma responsable. No evade captchas, no usa proxies rotativos, no simula usuarios para saltarse bloqueos y permite respetar `robots.txt`.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate   # Mac/Linux
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

## Correr scraper

```bash
python -m scraper.run --max-listings 100
```

Opciones útiles:

```bash
python -m scraper.run --max-listings 50 --delay 2.0
python -m scraper.run --sitemap https://chileautos.cl/sitemaps/chileautos/stock-listings.xml
python -m scraper.run --no-robots-check
```

## Correr dashboard

```bash
streamlit run dashboard/app.py
```

## Archivos generados

```text
data/autos.db
exports/chileautos_listings_latest.csv
exports/chileautos_listings_latest.xlsx
```

## GitHub Actions

El workflow corre 2 veces al día:

```yaml
cron: "0 0,12 * * *"
```

Esto equivale aproximadamente a mañana y noche en Chile, dependiendo de horario de verano/invierno.
También puede ejecutarse manualmente desde `workflow_dispatch`.

## Modelo de datos

Tabla `listings`:

```sql
source TEXT
url TEXT
brand TEXT
model TEXT
version TEXT
year INTEGER
sale_price INTEGER
currency TEXT
captured_at TEXT
```

Se usa `UNIQUE(url, captured_at)` para permitir histórico por corrida.
