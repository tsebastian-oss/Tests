from pathlib import Path
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st


DB_PATH = Path(__file__).resolve().parent.parent / "data" / "autos.db"

st.set_page_config(page_title="Auto Price Radar", page_icon="🚗", layout="wide")

st.title("Auto Price Radar")
st.caption("Chileautos · marca, modelo, versión, año y precio de venta")

if not DB_PATH.exists():
    st.info("Aún no existe `data/autos.db`. Corre: `python -m scraper.run --max-listings 100`.")
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

df["captured_at"] = pd.to_datetime(df["captured_at"])
df["date"] = df["captured_at"].dt.date

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
latest = dff[dff["date"] == latest_date]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Registros", f"{len(dff):,}")
c2.metric("Última captura", str(latest_date))
c3.metric("Precio promedio", f"${latest['sale_price'].mean():,.0f}".replace(",", "."))
c4.metric("Precio mediana", f"${latest['sale_price'].median():,.0f}".replace(",", "."))

tab1, tab2, tab3, tab4 = st.tabs(["Resumen", "Mercado", "Histórico", "Exportar"])

with tab1:
    st.subheader("Última captura")
    show = latest[["brand", "model", "version", "year", "sale_price", "url", "captured_at"]].copy()
    show.columns = ["Marca", "Modelo", "Versión", "Año", "Precio venta", "URL", "Captura"]
    st.dataframe(
        show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Precio venta": st.column_config.NumberColumn(format="$%d"),
            "URL": st.column_config.LinkColumn("URL"),
        },
        height=520,
    )

with tab2:
    st.subheader("Precio promedio por marca/modelo/año")
    market = (
        latest.groupby(["brand", "model", "year"], dropna=False)
        .agg(
            unidades=("url", "nunique"),
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

    if len(latest) > 1:
        fig = px.box(latest, x="brand", y="sale_price", points="all", title="Distribución de precios por marca")
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader("Evolución de precio promedio")
    hist = dff.groupby(["date", "brand", "model"], dropna=False)["sale_price"].mean().reset_index()
    if not hist.empty:
        fig = px.line(hist, x="date", y="sale_price", color="model", line_group="brand")
        st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.subheader("Exportar")
    csv = dff.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Descargar CSV", data=csv, file_name="auto_price_radar.csv", mime="text/csv")
