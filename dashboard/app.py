from pathlib import Path
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st


DB_PATH = Path(__file__).resolve().parent.parent / "data" / "autos.db"

st.set_page_config(page_title="Bruno Fritsch Price Radar", page_icon="🚗", layout="wide")

st.title("Bruno Fritsch Price Radar")
st.caption("Precios publicados por marca, modelo, versión y año")

if not DB_PATH.exists():
    st.info("Aún no existe `data/autos.db`. Corre: `python -m scraper.run --source bruno_fritsch --max-listings 5000`.")
    st.stop()

conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query(
    """
    SELECT source, url, brand, model, version, year, sale_price, currency, captured_at
    FROM listings
    ORDER BY captured_at DESC
    """,
    conn,
)
conn.close()

if df.empty:
    st.info("La base existe, pero no tiene datos todavía.")
    st.stop()

# Focus on Bruno Fritsch when available, but keep legacy data visible if it is the only thing loaded.
if "bruno_fritsch" in set(df["source"].dropna()):
    df = df[df["source"] == "bruno_fritsch"].copy()

if df.empty:
    st.info("No hay registros de Bruno Fritsch todavía.")
    st.stop()

df["captured_at"] = pd.to_datetime(df["captured_at"], errors="coerce")
df = df.dropna(subset=["captured_at"])
df["date"] = df["captured_at"].dt.date
df["sale_price"] = pd.to_numeric(df["sale_price"], errors="coerce")

with st.sidebar:
    st.header("Filtros")
    brands = sorted(df["brand"].dropna().unique())
    brand = st.selectbox("Marca", ["Todas"] + brands)
    dff = df.copy()
    if brand != "Todas":
        dff = dff[dff["brand"] == brand]

    models = sorted(dff["model"].dropna().unique())
    model = st.selectbox("Modelo", ["Todos"] + models)
    if model != "Todos":
        dff = dff[dff["model"] == model]

    years = sorted(int(y) for y in dff["year"].dropna().unique())
    year = st.selectbox("Año", ["Todos"] + years)
    if year != "Todos":
        dff = dff[dff["year"] == year]

    q = st.text_input("Buscar versión")
    if q.strip():
        dff = dff[dff["version"].fillna("").str.contains(q, case=False, regex=False)]

latest_date = dff["date"].max()
latest = dff[dff["date"] == latest_date].copy()
priced_latest = latest.dropna(subset=["sale_price"])

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Registros", f"{len(dff):,}")
c2.metric("Última captura", str(latest_date))
c3.metric("Con precio", f"{len(priced_latest):,}")
c4.metric("Precio promedio", f"${priced_latest['sale_price'].mean():,.0f}".replace(",", ".") if not priced_latest.empty else "-")
c5.metric("Precio mediana", f"${priced_latest['sale_price'].median():,.0f}".replace(",", ".") if not priced_latest.empty else "-")

tab1, tab2, tab3, tab4 = st.tabs(["Resumen", "Mercado", "Histórico", "Exportar"])

with tab1:
    st.subheader("Última captura")
    show = latest[["brand", "model", "version", "year", "sale_price", "url", "captured_at"]].copy()
    show.columns = ["Marca", "Modelo", "Versión", "Año", "Precio publicado", "URL", "Captura"]
    st.dataframe(
        show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Precio publicado": st.column_config.NumberColumn(format="$%d"),
            "URL": st.column_config.LinkColumn("URL"),
        },
        height=560,
    )

with tab2:
    st.subheader("Precio promedio por marca/modelo/año")
    market = (
        latest.groupby(["brand", "model", "year"], dropna=False)
        .agg(
            versiones=("version", "nunique"),
            paginas=("url", "nunique"),
            precio_promedio=("sale_price", "mean"),
            precio_mediana=("sale_price", "median"),
            precio_min=("sale_price", "min"),
            precio_max=("sale_price", "max"),
        )
        .reset_index()
        .sort_values(["brand", "model", "year"])
    )
    st.dataframe(
        market,
        use_container_width=True,
        hide_index=True,
        column_config={
            "precio_promedio": st.column_config.NumberColumn(format="$%d"),
            "precio_mediana": st.column_config.NumberColumn(format="$%d"),
            "precio_min": st.column_config.NumberColumn(format="$%d"),
            "precio_max": st.column_config.NumberColumn(format="$%d"),
        },
    )

    if len(priced_latest) > 1:
        fig = px.box(priced_latest, x="brand", y="sale_price", points="all", title="Distribución de precios por marca")
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader("Evolución de precio promedio")
    hist = dff.dropna(subset=["sale_price"]).groupby(["date", "brand", "model"], dropna=False)["sale_price"].mean().reset_index()
    if not hist.empty:
        fig = px.line(hist, x="date", y="sale_price", color="model", line_group="brand")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Aún no hay suficientes registros con precio para graficar histórico.")

with tab4:
    st.subheader("Exportar")
    csv = dff.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Descargar CSV", data=csv, file_name="bruno_fritsch_price_radar.csv", mime="text/csv")
