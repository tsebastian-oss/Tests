# Bruno Fritsch Price Radar

MVP para monitorear precios publicados en Bruno Fritsch Chile y guardar una base de autos/versiones con:

- marca
- modelo
- versión
- año
- precio publicado
- URL
- fecha de captura

El scraper usa una estrategia de descubrimiento responsable:

1. intenta leer sitemaps públicos;
2. prueba páginas candidatas de catálogo, stock, autos nuevos y usados;
3. recorre links internos relacionados a autos/versiones;
4. extrae datos desde JSON embebido, metatags y texto visible;
5. guarda resultados en SQLite y exporta CSV/Excel.

> Importante: usa esto de forma responsable. No evade captchas, no usa proxies rotativos y no simula usuarios para saltarse bloqueos. Si el sitio responde 403/429, el scraper reduce velocidad con backoff.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate   # Mac/Linux
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

## Correr scraper Bruno Fritsch

```bash
python -m scraper.run --source bruno_fritsch --max-listings 5000 --delay 0.5 --timeout 10
```

Opciones útiles:

```bash
python -m scraper.run --source bruno_fritsch --max-listings 1000
python -m scraper.run --source bruno_fritsch --max-listings 5000 --delay 1.0
python -m scraper.run --source bruno_fritsch --no-robots-check
```

## Correr dashboard

```bash
streamlit run dashboard/app.py
```

## Archivos generados

```text
data/autos.db
exports/bruno_fritsch_listings_latest.csv
exports/bruno_fritsch_listings_latest.xlsx
```

## GitHub Actions

El workflow corre 2 veces por semana:

```yaml
cron: "0 12 * * 1,4"
```

Esto equivale aproximadamente a lunes y jueves en la mañana de Chile.
También puede ejecutarse manualmente desde `workflow_dispatch` con:

```text
max_listings: 5000
delay_seconds: 0.5
timeout_seconds: 10
```

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

## Nota técnica

El sitio puede cambiar rutas, nombres de campos o bloquear tráfico automatizado. Por eso el scraper está armado como crawler de descubrimiento y no depende de una sola URL fija. Si Bruno Fritsch expone un endpoint/API interno estable, el siguiente paso es reemplazar la extracción genérica por un conector específico.
